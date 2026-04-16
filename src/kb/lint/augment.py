"""Augment orchestrator for kb_lint --augment.

Three-gate execution model (see docs/superpowers/specs/2026-04-15-kb-lint-augment-design.md):
  1. propose       — analyze stubs, write proposals to wiki/_augment_proposals.md
  2. --execute     — fetch URLs, save raw files (no ingest)
  3. --auto-ingest — pre-extract at scan tier, ingest, write quality verdict
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import frontmatter

from kb.config import (
    AUGMENT_ALLOWED_DOMAINS,
    AUGMENT_COOLDOWN_HOURS,
    AUTOGEN_PREFIXES,
    RAW_DIR,
    WIKI_DIR,
)
from kb.graph.builder import build_graph
from kb.lint.checks import check_stub_pages
from kb.lint.fetcher import _registered_domain, _url_is_allowed
from kb.utils.io import atomic_text_write
from kb.utils.llm import call_llm_json

logger = logging.getLogger(__name__)

Mode = Literal["propose", "execute", "auto_ingest"]

# Placeholder-title regex: rejects entity-N, placeholder-foo, etc.
_PLACEHOLDER_TITLE_RE = re.compile(
    r"^(entity-\d+|concept-\d+|placeholder|untitled|tbd|todo)\b",
    re.IGNORECASE,
)


def _collect_eligible_stubs(*, wiki_dir: Path | None = None) -> list[dict[str, Any]]:
    """Apply admission gates G1-G7 to stub_pages results.

    Returns list of {page_id, title, page_type, frontmatter, body, inbound_count,
    inbound_pages} for eligible stubs.
    """
    wiki_dir = wiki_dir or WIKI_DIR

    stub_issues = check_stub_pages(wiki_dir=wiki_dir)
    if not stub_issues:
        return []

    graph = build_graph(wiki_dir)
    eligible: list[dict[str, Any]] = []

    for issue in stub_issues:
        page_id = issue["page"]

        # G7 autogen prefix
        if page_id.startswith(AUTOGEN_PREFIXES):
            continue

        page_path = wiki_dir / f"{page_id}.md"
        if not page_path.exists():
            continue

        try:
            post = frontmatter.load(str(page_path))
        except (OSError, ValueError, UnicodeDecodeError) as e:
            logger.warning("Skipping unparseable stub %s: %s", page_id, e)
            continue

        title = str(post.metadata.get("title", "") or "")

        # G1 placeholder title
        if not title or _PLACEHOLDER_TITLE_RE.match(title.strip()):
            continue

        # G3 confidence ≠ speculative
        if post.metadata.get("confidence") == "speculative":
            continue

        # G4 per-page opt-out
        if post.metadata.get("augment") is False:
            continue

        # G6 cooldown
        last_attempt = post.metadata.get("last_augment_attempted")
        if last_attempt:
            try:
                if isinstance(last_attempt, datetime):
                    last_dt = last_attempt
                else:
                    last_dt = datetime.fromisoformat(str(last_attempt).replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=UTC)
                if datetime.now(UTC) - last_dt < timedelta(hours=AUGMENT_COOLDOWN_HOURS):
                    continue
            except (ValueError, TypeError) as e:
                logger.debug("Could not parse last_augment_attempted for %s: %s", page_id, e)

        # G2 inbound link from non-summary/non-autogen page
        # graph predecessors are page IDs of pages that link TO this page
        if not graph.has_node(page_id):
            continue
        non_summary_inbound = [
            src for src in graph.predecessors(page_id) if not src.startswith(AUTOGEN_PREFIXES)
        ]
        if not non_summary_inbound:
            continue

        eligible.append(
            {
                "page_id": page_id,
                "title": title,
                "page_type": post.metadata.get("type", page_id.split("/")[0].rstrip("s")),
                "frontmatter": dict(post.metadata),
                "body": post.content,
                "inbound_count": len(non_summary_inbound),
                "inbound_pages": non_summary_inbound,
            }
        )

    return eligible


# ── URL proposer (Task 11) ────────────────────────────────────────

_PROPOSER_PROMPT_TEMPLATE = """\
You are proposing candidate URLs to enrich a stub wiki page.

Page title: {title}
Page type: {page_type}
Existing sources (avoid duplicates): {existing_sources}
Allowed domains (STRICT — URLs outside this list will be rejected): {allowed_domains}

KB purpose / scope (reject URLs outside this scope; abstain if topic is out of scope):
{purpose}

Return JSON with EXACTLY this shape:
  {{"action": "propose", "urls": [up to 3 URLs from allowed domains], "rationale": "1-line"}}
  OR
  {{"action": "abstain", "reason": "no authoritative source | out of scope | ambiguous title"}}

Constraints:
- Each URL must be a complete absolute URL (https://...).
- Each URL's registered domain must be in the allowed list.
- Do NOT invent URLs you are not confident exist.
- If you cannot find a high-authority allowlisted source, ABSTAIN. Do not pad the list.
"""


_PROPOSER_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["propose", "abstain"]},
        "urls": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "rationale": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["action"],
    "additionalProperties": True,
}


def _build_proposer_prompt(stub: dict[str, Any], purpose_text: str) -> str:
    """Build proposer prompt with title repr-escaped + truncated to 100 chars."""
    title = repr(str(stub.get("title", ""))[:100])  # truncate + escape
    existing = stub.get("frontmatter", {}).get("source") or []
    if isinstance(existing, str):
        existing = [existing]
    existing_repr = [repr(str(s)[:200]) for s in existing[:10]]
    return _PROPOSER_PROMPT_TEMPLATE.format(
        title=title,
        page_type=stub.get("page_type", "concept"),
        existing_sources="[" + ", ".join(existing_repr) + "]",
        allowed_domains=list(AUGMENT_ALLOWED_DOMAINS),
        purpose=(purpose_text[:1000] if purpose_text else "(no purpose.md provided)"),
    )


def _propose_urls(*, stub: dict[str, Any], purpose_text: str) -> dict[str, Any]:
    """Call scan-tier LLM proposer with eligibility-filtered stub.

    Returns {"action": "propose", "urls": [...], "rationale": "..."}
    OR     {"action": "abstain", "reason": "..."}
    """
    prompt = _build_proposer_prompt(stub, purpose_text)
    try:
        response = call_llm_json(prompt, tier="scan", schema=_PROPOSER_SCHEMA)
    except Exception as e:
        logger.warning("Proposer LLM call failed for %s: %s", stub.get("page_id"), e)
        return {"action": "abstain", "reason": f"proposer LLM error: {type(e).__name__}"}

    action = response.get("action")
    if action == "abstain":
        return {"action": "abstain", "reason": response.get("reason", "abstained")}
    if action != "propose":
        return {"action": "abstain", "reason": f"unexpected action: {action!r}"}

    raw_urls = response.get("urls") or []
    filtered: list[str] = []
    for u in raw_urls:
        if _url_is_allowed(u, AUGMENT_ALLOWED_DOMAINS):
            filtered.append(u)
        else:
            rd = _registered_domain(u)
            logger.info("Dropping off-allowlist proposed URL: %s (domain=%s)", u, rd)

    if not filtered:
        return {"action": "abstain", "reason": "no allowlisted URLs in proposer response"}

    return {
        "action": "propose",
        "urls": filtered,
        "rationale": response.get("rationale", ""),
    }


# ── Wikipedia fallback + relevance score (Task 12) ───────────────


def _wikipedia_fallback(*, page_id: str, title: str) -> str | None:
    """Derive a Wikipedia URL from an entity/concept page slug.

    Only produces a URL for entity/concept pages (skips comparisons/synthesis/
    summaries). Normalizes the title using Wikipedia's article-slug convention:
    spaces become underscores, the first character is uppercased, the remaining
    characters are lowercased (so "Mixture of Experts" → "Mixture_of_experts").

    Caller is responsible for fetching the URL and applying fuzzy + disambig
    guards.
    """
    if not page_id.startswith(("entities/", "concepts/")):
        return None
    if not title or not title.strip():
        return None
    slug = title.strip().lower().replace(" ", "_")
    if slug:
        slug = slug[0].upper() + slug[1:]
    return f"https://en.wikipedia.org/wiki/{slug}"


_RELEVANCE_SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "number", "minimum": 0.0, "maximum": 1.0}},
    "required": ["score"],
}


def _relevance_score(*, stub_title: str, extracted_text: str) -> float:
    """Scan-tier relevance score (0.0-1.0) for extracted text vs stub topic.

    Returns 0.0 on any LLM error or invalid response shape.
    """
    prompt = (
        f"Score how relevant the following extracted text is to the topic "
        f"{stub_title!r}.\n"
        f'Return JSON: {{"score": <0.0-1.0>}}.\n\n'
        f"Extracted text (first 2000 chars):\n{extracted_text[:2000]}"
    )
    try:
        response = call_llm_json(prompt, tier="scan", schema=_RELEVANCE_SCHEMA)
    except Exception as e:
        logger.warning("Relevance score LLM call failed: %s", e)
        return 0.0
    score = response.get("score")
    try:
        return float(score)
    except (TypeError, ValueError):
        return 0.0


# ── Task 13: propose-mode orchestrator ────────────────────────────


def _load_purpose_text(wiki_dir: Path) -> str:
    """Load wiki/purpose.md (first 5000 chars) or empty string on any error."""
    purpose_path = wiki_dir / "purpose.md"
    if not purpose_path.exists():
        return ""
    try:
        return purpose_path.read_text(encoding="utf-8")[:5000]
    except OSError:
        return ""


def _format_proposals_md(proposals: list[dict[str, Any]], run_id: str) -> str:
    """Render the proposals list as markdown for wiki/_augment_proposals.md."""
    lines = [
        f"# Augment Proposals - run `{run_id[:8]}`",
        f"Generated: {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        "Review each proposal below; run `kb lint --augment --execute` to fetch + save to `raw/`.",
        "",
    ]
    for i, p in enumerate(proposals, 1):
        lines.append(f"## {i}. {p['stub_id']}")
        lines.append(f"- **Title:** {p['title']}")
        lines.append(f"- **Action:** {p['action']}")
        if p["action"] == "propose":
            lines.append("- **URLs:**")
            for u in p["urls"]:
                lines.append(f"  - {u}")
            lines.append(f"- **Rationale:** {p.get('rationale', '')}")
        else:
            lines.append(f"- **Reason:** {p.get('reason', '')}")
        lines.append("")
    return "\n".join(lines)


# Regex for parsing _format_proposals_md output back into proposal dicts.
# Used by run_augment(mode="execute"|"auto_ingest") to consume reviewed
# proposals from wiki/_augment_proposals.md — round-trip must be reliable.
_PROPOSAL_HEADER_RE = re.compile(r"^##\s+\d+\.\s+(?P<stub_id>.+?)\s*$")
_PROPOSAL_TITLE_RE = re.compile(r"^-\s+\*\*Title:\*\*\s+(?P<title>.+?)\s*$")
_PROPOSAL_ACTION_RE = re.compile(r"^-\s+\*\*Action:\*\*\s+(?P<action>.+?)\s*$")
_PROPOSAL_URL_ITEM_RE = re.compile(r"^\s{2}-\s+(?P<url>\S+)\s*$")
_PROPOSAL_RATIONALE_RE = re.compile(r"^-\s+\*\*Rationale:\*\*\s*(?P<rationale>.*?)\s*$")
_PROPOSAL_REASON_RE = re.compile(r"^-\s+\*\*Reason:\*\*\s*(?P<reason>.*?)\s*$")


def _parse_proposals_md(proposals_path: Path) -> list[dict[str, Any]] | None:
    """Inverse of _format_proposals_md: parse markdown back into proposal dicts.

    Returns a list of proposal dicts with the same shape run_augment produces
    (keys: stub_id, title, action, urls?, rationale?, reason?), or None if
    the file is missing or unparseable.

    Tolerant to whitespace / trailing newlines but rejects clearly malformed
    sections (e.g., a ``## N. stub_id`` header missing a Title/Action pair).
    """
    if not proposals_path.exists():
        return None
    try:
        text = proposals_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Could not read proposals file %s: %s", proposals_path, e)
        return None

    proposals: list[dict[str, Any]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m_hdr = _PROPOSAL_HEADER_RE.match(lines[i])
        if not m_hdr:
            i += 1
            continue
        stub_id = m_hdr.group("stub_id").strip()
        entry: dict[str, Any] = {"stub_id": stub_id}
        i += 1
        in_urls_block = False
        while i < len(lines):
            line = lines[i]
            # Next section header ends current block
            if _PROPOSAL_HEADER_RE.match(line):
                break
            m_title = _PROPOSAL_TITLE_RE.match(line)
            if m_title:
                entry["title"] = m_title.group("title").strip()
                in_urls_block = False
                i += 1
                continue
            m_action = _PROPOSAL_ACTION_RE.match(line)
            if m_action:
                entry["action"] = m_action.group("action").strip()
                in_urls_block = False
                i += 1
                continue
            if line.strip() == "- **URLs:**":
                entry.setdefault("urls", [])
                in_urls_block = True
                i += 1
                continue
            if in_urls_block:
                m_url = _PROPOSAL_URL_ITEM_RE.match(line)
                if m_url:
                    entry["urls"].append(m_url.group("url").strip())
                    i += 1
                    continue
                # Blank line or unrelated — exit urls block
                in_urls_block = False
            m_rat = _PROPOSAL_RATIONALE_RE.match(line)
            if m_rat:
                entry["rationale"] = m_rat.group("rationale").strip()
                i += 1
                continue
            m_reason = _PROPOSAL_REASON_RE.match(line)
            if m_reason:
                entry["reason"] = m_reason.group("reason").strip()
                i += 1
                continue
            i += 1

        # Validate minimum shape; if unparseable, skip this block
        if "title" in entry and "action" in entry:
            if entry["action"] == "propose" and not entry.get("urls"):
                # A propose entry without URLs is malformed
                logger.warning(
                    "Skipping proposal for %s: action=propose but no URLs parsed",
                    stub_id,
                )
                continue
            proposals.append(entry)
        else:
            logger.warning(
                "Skipping malformed proposal block for stub_id=%s (missing title or action)",
                stub_id,
            )

    return proposals if proposals else None


def _save_raw_file(
    *,
    raw_dir: Path,
    stub_id: str,
    title: str,
    url: str,
    run_id: str,
    content: str,
    proposer: str,
) -> Path:
    """Save fetched content to raw/articles/<slug>-<run_id[:8]>[-<n>].md.

    Collision-fallback: if the base name already exists, append ``-2``, ``-3``,
    etc. Embeds augment provenance in frontmatter and prepends an
    ``[!untrusted_source]`` callout so downstream readers see the provenance.
    """
    from kb.utils.hashing import hash_bytes
    from kb.utils.text import slugify

    article_dir = raw_dir / "articles"
    article_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(title) or stub_id.split("/")[-1]
    base_name = f"{slug}-{run_id[:8]}.md"
    target = article_dir / base_name
    counter = 2
    while target.exists():
        target = article_dir / f"{slug}-{run_id[:8]}-{counter}.md"
        counter += 1

    sha = hash_bytes(content.encode("utf-8"))
    fm_lines = [
        "---",
        f"title: {title!r}",
        "source_type: article",
        f"fetched_from: {url}",
        f"fetched_at: {datetime.now(UTC).isoformat(timespec='seconds')}",
        "augment: true",
        f"augment_for: {stub_id}",
        f"augment_run_id: {run_id}",
        f"augment_proposer: {proposer}",
        f"sha256: '{sha}'",
        "---",
        "",
        "> [!untrusted_source]",
        f"> Auto-fetched from {url} during `kb lint --augment`. Not human-reviewed.",
        "",
        content,
    ]
    atomic_text_write("\n".join(fm_lines), target)
    return target


def run_augment(
    *,
    wiki_dir: Path | None = None,
    raw_dir: Path | None = None,
    data_dir: Path | None = None,
    mode: Mode = "propose",
    max_gaps: int = 5,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Three-gate augment orchestrator. See module docstring.

    Gate contract:
      - mode="propose" (gate 1): run eligibility + LLM proposer (with
        Wikipedia fallback for abstained entity/concept stubs), write
        ``wiki/_augment_proposals.md`` for human review. The proposals file
        is overwritten on each propose run.
      - mode="execute" (gate 2): READ the proposals file (no re-proposing!),
        fetch URLs + relevance gate + save raw files, then rename the
        proposals file to ``_augment_proposals.md.consumed-<run_id[:8]>`` for
        audit. Errors if no proposals file is present — human must run
        gate 1 first.
      - mode="auto_ingest" (gate 3): same consumption of proposals file as
        gate 2, plus pre-extract + ingest_source + augmented-page marker +
        post-ingest quality verdict.

    The read-the-proposals-file contract (not re-proposing) is load-bearing:
    it forces every side-effect-having run to go through a human-reviewable
    artifact first, honoring CLAUDE.md's "Human curates sources" principle.

    Note: Manifest.resume() is implemented but not yet wired through the
    CLI/MCP surface. Crash-resume support is tracked in BACKLOG Phase 5.
    """
    from urllib.parse import urlparse

    import kb
    from kb.config import (
        AUGMENT_FETCH_MAX_CALLS_PER_RUN,
        AUGMENT_RELEVANCE_THRESHOLD,
    )
    from kb.lint._augment_manifest import Manifest
    from kb.lint._augment_rate import RateLimiter
    from kb.lint.fetcher import AugmentFetcher

    wiki_dir = wiki_dir or WIKI_DIR
    raw_dir = raw_dir or RAW_DIR

    # B2/B3 (Phase 5 three-round MEDIUM): when caller supplies a custom wiki
    # but no explicit data_dir, derive `wiki_dir.parent / ".data"` so manifest
    # and rate-limit state stay with the custom project. Standard runs fall
    # through to the repo-global defaults (None → Manifest/RateLimiter pick
    # their module-level MANIFEST_DIR / RATE_PATH).
    effective_data_dir: Path | None
    if data_dir is not None:
        effective_data_dir = Path(data_dir)
    elif wiki_dir != WIKI_DIR:
        effective_data_dir = wiki_dir.parent / ".data"
    else:
        effective_data_dir = None

    # B4 (Phase 5 three-round MEDIUM): reject max_gaps<1 up front. Negative
    # values silently fell through Python slicing (proposals[:-1] drops the
    # last item) and could consume reviewed proposals while skipping work.
    if not isinstance(max_gaps, int) or max_gaps < 1:
        raise ValueError(f"max_gaps={max_gaps!r} must be a positive integer")
    if max_gaps > AUGMENT_FETCH_MAX_CALLS_PER_RUN:
        raise ValueError(
            f"max_gaps={max_gaps} exceeds "
            f"AUGMENT_FETCH_MAX_CALLS_PER_RUN={AUGMENT_FETCH_MAX_CALLS_PER_RUN}"
        )

    run_id = str(uuid.uuid4())
    proposals: list[dict[str, Any]] = []
    fetches: list[dict[str, Any]] | None = None
    ingests: list[dict[str, Any]] | None = None
    verdicts: list[dict[str, Any]] | None = None
    manifest_path: str | None = None
    manifest: Manifest | None = None
    proposals_path = wiki_dir / "_augment_proposals.md"

    # Gate 2/3: execute / auto_ingest MUST consume a prior human-reviewed
    # proposals file. We refuse to re-propose silently, because that bypasses
    # the review checkpoint the three-gate contract exists for.
    if mode in ("execute", "auto_ingest"):
        parsed_proposals = _parse_proposals_md(proposals_path)
        if parsed_proposals is None:
            early_summary = (
                f"## Augment Summary (run {run_id[:8]}, mode={mode})\n"
                f"- No proposals file found at `{proposals_path}`.\n"
                "- Run `kb lint --augment` first to generate proposals "
                "(gate 1), review them, then re-run with --execute."
            )
            return {
                "run_id": run_id,
                "mode": mode,
                "gaps_examined": 0,
                "gaps_eligible": 0,
                "proposals": [],
                "fetches": None,
                "ingests": None,
                "verdicts": None,
                "manifest_path": None,
                "summary": early_summary,
            }
        proposals = parsed_proposals[:max_gaps]
        # In execute/auto_ingest we do NOT re-run eligibility or call the
        # LLM proposer — the reviewed file is the source of truth. We still
        # want the G6 cooldown writeback to cover the stubs we touched.
        eligible = [{"page_id": p["stub_id"], "title": p.get("title", "")} for p in proposals]
    else:
        # Gate 1: propose. Full eligibility pass + LLM proposer.
        eligible = _collect_eligible_stubs(wiki_dir=wiki_dir)[:max_gaps]
        purpose_text = _load_purpose_text(wiki_dir)

        for stub in eligible:
            prop = _propose_urls(stub=stub, purpose_text=purpose_text)
            entry: dict[str, Any] = {
                "stub_id": stub["page_id"],
                "title": stub["title"],
                **prop,
            }
            if prop["action"] == "abstain":
                wiki_url = _wikipedia_fallback(page_id=stub["page_id"], title=stub["title"])
                if wiki_url is not None:
                    entry = {
                        "stub_id": stub["page_id"],
                        "title": stub["title"],
                        "action": "propose",
                        "urls": [wiki_url],
                        "rationale": (
                            f"wikipedia fallback (proposer abstained: {prop.get('reason')})"
                        ),
                    }
            proposals.append(entry)

    # Phase B: execute (mode in {execute, auto_ingest})
    if mode in ("execute", "auto_ingest") and proposals:
        if dry_run:
            fetches = [{"stub_id": p["stub_id"], "status": "dry_run_skipped"} for p in proposals]
        else:
            manifest = Manifest.start(
                run_id=run_id,
                mode=mode,
                max_gaps=max_gaps,
                stubs=[{"page_id": p["stub_id"], "title": p["title"]} for p in proposals],
                data_dir=effective_data_dir,
            )
            manifest_path = str(manifest.path)
            limiter = RateLimiter(data_dir=effective_data_dir)
            fetches = []
            with AugmentFetcher(
                allowed_domains=AUGMENT_ALLOWED_DOMAINS,
                version=kb.__version__,
            ) as fetcher:
                for prop in proposals:
                    stub_id = prop["stub_id"]
                    if prop["action"] != "propose":
                        manifest.advance(
                            stub_id, "abstained", payload={"reason": prop.get("reason")}
                        )
                        fetches.append(
                            {
                                "stub_id": stub_id,
                                "status": "abstained",
                                "reason": prop.get("reason"),
                            }
                        )
                        continue

                    fetched_ok = False
                    for url in prop["urls"]:
                        # B5 (Phase 5 three-round MEDIUM): re-run the allowlist
                        # check on each reviewed URL BEFORE acquiring rate-limit
                        # quota. A hand-edited proposals file can carry off-
                        # allowlist or malformed URLs; fetcher.fetch() rejects
                        # them after network I/O, but RateLimiter.acquire()
                        # already burned a slot — so a bad reviewed URL poisons
                        # the hourly cap for good URLs. Reject first, record,
                        # and continue without touching the limiter.
                        if not _url_is_allowed(url, AUGMENT_ALLOWED_DOMAINS):
                            manifest.advance(
                                stub_id,
                                "failed",
                                payload={"reason": f"blocked_by_allowlist: {url}"},
                            )
                            fetches.append(
                                {
                                    "stub_id": stub_id,
                                    "status": "blocked_by_allowlist",
                                    "url": url,
                                }
                            )
                            continue
                        # Normalize to bare hostname (lowercase, no port, no
                        # userinfo). netloc would treat example.com and
                        # example.com:443 as separate buckets, weakening the
                        # per-host cap.
                        parsed_url = urlparse(url)
                        host = (parsed_url.hostname or "").lower()
                        allowed, retry = limiter.acquire(host)
                        if not allowed:
                            manifest.advance(
                                stub_id,
                                "failed",
                                payload={"reason": f"rate limited (retry {retry}s)"},
                            )
                            fetches.append(
                                {
                                    "stub_id": stub_id,
                                    "status": "rate_limited",
                                    "url": url,
                                    "retry": retry,
                                }
                            )
                            break
                        manifest.advance(stub_id, "proposed", payload={"url": url})
                        result = fetcher.fetch(url)
                        if result.status != "ok":
                            fetches.append(
                                {
                                    "stub_id": stub_id,
                                    "status": "failed",
                                    "url": url,
                                    "reason": result.reason,
                                }
                            )
                            continue
                        manifest.advance(
                            stub_id,
                            "fetched",
                            payload={"url": url, "bytes": result.bytes},
                        )

                        # Relevance gate
                        score = _relevance_score(
                            stub_title=prop["title"],
                            extracted_text=result.extracted_markdown or "",
                        )
                        if score < AUGMENT_RELEVANCE_THRESHOLD:
                            manifest.advance(
                                stub_id,
                                "failed",
                                payload={
                                    "reason": (
                                        f"relevance {score:.2f} < {AUGMENT_RELEVANCE_THRESHOLD}"
                                    )
                                },
                            )
                            fetches.append(
                                {
                                    "stub_id": stub_id,
                                    "status": "skipped",
                                    "url": url,
                                    "reason": f"relevance {score:.2f} < threshold",
                                }
                            )
                            continue

                        # Save raw
                        raw_path = _save_raw_file(
                            raw_dir=raw_dir,
                            stub_id=stub_id,
                            title=prop["title"],
                            url=result.url,
                            run_id=run_id,
                            content=result.extracted_markdown or "",
                            proposer=(
                                "wikipedia-fallback"
                                if "wikipedia fallback" in prop.get("rationale", "")
                                else "llm-scan"
                            ),
                        )
                        manifest.advance(stub_id, "saved", payload={"raw_path": str(raw_path)})
                        fetches.append(
                            {
                                "stub_id": stub_id,
                                "status": "saved",
                                "url": url,
                                "raw_path": str(raw_path),
                                "relevance": score,
                            }
                        )
                        fetched_ok = True
                        break

                    if not fetched_ok and not any(f["stub_id"] == stub_id for f in fetches):
                        manifest.advance(stub_id, "failed", payload={"reason": "all URLs failed"})

            if mode == "execute":
                # Mark saved gaps as terminal "done" (no ingest in execute mode)
                for f in fetches:
                    if f["status"] == "saved":
                        manifest.advance(f["stub_id"], "done")
                manifest.close()

    # Phase C: auto-ingest (only if mode == "auto_ingest")
    if mode == "auto_ingest" and fetches is not None and not dry_run:
        from kb.ingest.extractors import _build_schema_cached
        from kb.ingest.pipeline import ingest_source
        from kb.lint.verdicts import add_verdict

        ingests = []
        verdicts = []

        for f in fetches:
            stub_id = f["stub_id"]
            if f["status"] != "saved":
                ingests.append(
                    {
                        "stub_id": stub_id,
                        "status": "skipped",
                        "reason": f"fetch not saved: {f['status']}",
                    }
                )
                continue
            raw_path = Path(f["raw_path"])

            # Pre-extract at scan tier (Claude Code or API-side)
            try:
                schema = _build_schema_cached("article")
                raw_content = raw_path.read_text(encoding="utf-8")
                extraction = call_llm_json(
                    (
                        "Extract structured data from this article per the schema.\n\n"
                        f"<untrusted_source>\n{raw_content}\n</untrusted_source>"
                    ),
                    tier="scan",
                    schema=schema,
                )
            except Exception as e:
                msg = f"pre-extract failed: {type(e).__name__}: {e}"
                if manifest is not None:
                    manifest.advance(stub_id, "failed", payload={"reason": msg})
                ingests.append({"stub_id": stub_id, "status": "failed", "reason": msg})
                continue

            if manifest is not None:
                manifest.advance(stub_id, "extracted", payload={"keys": list(extraction.keys())})

            # Ingest
            try:
                ingest_result = ingest_source(
                    raw_path,
                    source_type="article",
                    extraction=extraction,
                    wiki_dir=wiki_dir,
                    raw_dir=raw_dir,  # B1: honor caller's custom raw/
                )
            except Exception as e:
                msg = f"ingest_source failed: {type(e).__name__}: {e}"
                if manifest is not None:
                    manifest.advance(stub_id, "failed", payload={"reason": msg})
                ingests.append({"stub_id": stub_id, "status": "failed", "reason": msg})
                continue

            if manifest is not None:
                manifest.advance(
                    stub_id,
                    "ingested",
                    payload={
                        "pages_created": ingest_result.get("pages_created", []),
                        "pages_updated": ingest_result.get("pages_updated", []),
                    },
                )

            # Mark the stub page speculative + add [!augmented] callout
            stub_path = wiki_dir / f"{stub_id}.md"
            if stub_path.exists():
                _mark_page_augmented(stub_path, source_url=f["url"])

            ingests.append(
                {
                    "stub_id": stub_id,
                    "status": "ingested",
                    "pages_created": ingest_result.get("pages_created", []),
                    "pages_updated": ingest_result.get("pages_updated", []),
                }
            )

            # Targeted post-ingest quality check (Task 16)
            verdict, reason = _post_ingest_quality(page_path=stub_path, wiki_dir=wiki_dir)
            add_verdict(
                page_id=stub_id,
                verdict_type="augment",
                verdict=verdict,
                notes=(
                    f"{reason} | augmented from {f['url']} (relevance {f.get('relevance', 0):.2f})"
                ),
                issues=[],
            )
            verdicts.append({"stub_id": stub_id, "verdict": verdict, "reason": reason})

            if verdict == "fail" and stub_path.exists():
                # Add a [!gap] callout flagging the page for manual review
                post = frontmatter.load(str(stub_path))
                gap_callout = (
                    f"> [!gap]\n"
                    f"> Augment run {run_id[:8]} failed quality check: "
                    f"{reason}. Manual review needed.\n\n"
                )
                if "[!gap]" not in post.content:
                    post.content = gap_callout + post.content
                    atomic_text_write(frontmatter.dumps(post), stub_path)

            if manifest is not None:
                manifest.advance(
                    stub_id,
                    "verdict",
                    payload={"verdict": verdict, "reason": reason},
                )
                manifest.advance(stub_id, "done")

        if manifest is not None:
            manifest.close()

    if mode == "auto_ingest" and dry_run:
        ingests = [{"stub_id": p["stub_id"], "status": "dry_run_skipped"} for p in proposals]

    # G6 cooldown writeback — every stub we examined this run gets a
    # last_augment_attempted stamp so the next run's cooldown gate can
    # skip it until AUGMENT_COOLDOWN_HOURS elapses. Skipped on dry_run
    # (a preview should not alter pages).
    if not dry_run:
        for stub in eligible:
            _record_attempt(wiki_dir / f"{stub['page_id']}.md")

    summary_lines = [f"## Augment Summary (run {run_id[:8]}, mode={mode})"]
    summary_lines.append(f"- Stubs examined: {len(eligible)}")
    summary_lines.append(f"- Proposals: {sum(1 for p in proposals if p['action'] == 'propose')}")
    if fetches is not None:
        saved = sum(1 for f in fetches if f["status"] == "saved")
        skipped = sum(1 for f in fetches if f["status"] == "skipped")
        failed = sum(
            1 for f in fetches if f["status"] not in {"saved", "skipped", "dry_run_skipped"}
        )
        summary_lines.append(f"- Saved: {saved}, Skipped: {skipped}, Failed: {failed}")
    if manifest_path:
        summary_lines.append(f"- Manifest: {manifest_path}")

    if mode == "propose" and not dry_run and proposals:
        # Propose always overwrites the file — each gate 1 run is a fresh
        # opportunity to review. A stale consumed-file from a prior execute
        # run does not block this.
        atomic_text_write(_format_proposals_md(proposals, run_id), proposals_path)
        summary_lines.append(f"- Proposals file: {proposals_path}")

    if mode in ("execute", "auto_ingest") and not dry_run and proposals_path.exists():
        # Mark the consumed proposals file with the run_id so the same
        # proposals cannot be silently re-consumed by a subsequent execute
        # invocation without a fresh gate-1 review. Rename (not delete) for
        # audit trail.
        consumed_path = proposals_path.with_name(f"{proposals_path.name}.consumed-{run_id[:8]}")
        try:
            proposals_path.rename(consumed_path)
            summary_lines.append(f"- Proposals consumed: {consumed_path}")
        except OSError as e:
            logger.warning(
                "Failed to rename consumed proposals file %s -> %s: %s",
                proposals_path,
                consumed_path,
                e,
            )

    return {
        "run_id": run_id,
        "mode": mode,
        "gaps_examined": len(eligible),
        "gaps_eligible": len(eligible),
        "proposals": proposals,
        "fetches": fetches,
        "ingests": ingests,
        "verdicts": verdicts,
        "manifest_path": manifest_path,
        "summary": "\n".join(summary_lines),
    }


def _mark_page_augmented(page_path: Path, *, source_url: str) -> None:
    """Force ``confidence: speculative`` + prepend ``[!augmented]`` callout.

    Idempotent: if a ``[!augmented]`` callout is already present in the body,
    the callout is not re-inserted (but confidence is still forced to
    ``speculative`` on every call).
    """
    post = frontmatter.load(str(page_path))
    post.metadata["confidence"] = "speculative"
    callout = (
        "> [!augmented]\n"
        f"> Enriched from {source_url} on "
        f"{datetime.now(UTC).isoformat(timespec='seconds')}. "
        "Marked speculative until human review.\n\n"
    )
    if "[!augmented]" not in post.content:
        post.content = callout + post.content
    atomic_text_write(frontmatter.dumps(post), page_path)


def _record_attempt(stub_path: Path) -> None:
    """Stamp ``last_augment_attempted`` into the stub page's frontmatter.

    Called at the end of every per-stub iteration regardless of outcome
    (propose, abstain, fetch-fail, rate-limit, ingest-fail, success) so the
    G6 cooldown gate (_collect_eligible_stubs) can honour its
    AUGMENT_COOLDOWN_HOURS window on the next run.

    Errors are logged and swallowed — failing to record a cooldown stamp
    should never abort the overall augment run.
    """
    if not stub_path.exists():
        return
    try:
        post = frontmatter.load(str(stub_path))
        post.metadata["last_augment_attempted"] = (
            datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        )
        atomic_text_write(frontmatter.dumps(post), stub_path)
    except Exception as e:
        logger.warning("Failed to record last_augment_attempted for %s: %s", stub_path, e)


def _post_ingest_quality(*, page_path: Path, wiki_dir: Path) -> tuple[str, str]:
    """Targeted post-ingest quality regression: did the augment actually help?

    Checks the SPECIFIC page (not a full wiki scan) for two conditions:
      1. Body length still passes the stub threshold via ``check_stub_pages``
      2. ``source:`` frontmatter is non-empty

    Returns ``("pass" | "fail", reason)``.
    """
    if not page_path.exists():
        return "fail", "page not found post-ingest"

    stub_issues = check_stub_pages(wiki_dir=wiki_dir, pages=[page_path])
    if stub_issues:
        return (
            "fail",
            f"page still a stub after augment ({stub_issues[0]['content_length']} chars)",
        )

    try:
        post = frontmatter.load(str(page_path))
    except Exception as e:
        return "fail", f"frontmatter unparseable: {e}"

    sources = post.metadata.get("source") or []
    if isinstance(sources, str):
        sources = [sources]
    if not sources:
        return "fail", "augmented page has no source: in frontmatter"

    return "pass", f"body len ok, {len(sources)} source(s)"
