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
            src for src in graph.predecessors(page_id)
            if not src.startswith(AUTOGEN_PREFIXES)
        ]
        if not non_summary_inbound:
            continue

        eligible.append({
            "page_id": page_id,
            "title": title,
            "page_type": post.metadata.get("type", page_id.split("/")[0].rstrip("s")),
            "frontmatter": dict(post.metadata),
            "body": post.content,
            "inbound_count": len(non_summary_inbound),
            "inbound_pages": non_summary_inbound,
        })

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
    target.write_text("\n".join(fm_lines), encoding="utf-8")
    return target


def run_augment(
    *,
    wiki_dir: Path | None = None,
    raw_dir: Path | None = None,
    mode: Mode = "propose",
    max_gaps: int = 5,
    dry_run: bool = False,
    resume: str | None = None,
) -> dict[str, Any]:
    """Three-gate augment orchestrator. See module docstring.

    Phase A (always): eligibility → propose URLs (with Wikipedia fallback for
    abstained entity/concept stubs). Phase B (execute/auto_ingest): fetch +
    relevance gate + save raw + manifest advance. Phase C (auto_ingest):
    pre-extract + ingest_source + augmented-page marker + quality verdict.
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

    if max_gaps > AUGMENT_FETCH_MAX_CALLS_PER_RUN:
        raise ValueError(
            f"max_gaps={max_gaps} exceeds "
            f"AUGMENT_FETCH_MAX_CALLS_PER_RUN={AUGMENT_FETCH_MAX_CALLS_PER_RUN}"
        )

    eligible = _collect_eligible_stubs(wiki_dir=wiki_dir)[:max_gaps]
    purpose_text = _load_purpose_text(wiki_dir)

    run_id = str(uuid.uuid4())
    proposals: list[dict[str, Any]] = []
    fetches: list[dict[str, Any]] | None = None
    ingests: list[dict[str, Any]] | None = None
    verdicts: list[dict[str, Any]] | None = None
    manifest_path: str | None = None
    manifest: Manifest | None = None

    # Phase A: propose (always runs)
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
                    "rationale": f"wikipedia fallback (proposer abstained: {prop.get('reason')})",
                }
        proposals.append(entry)

    # Phase B: execute (mode in {execute, auto_ingest})
    if mode in ("execute", "auto_ingest") and proposals:
        if dry_run:
            fetches = [
                {"stub_id": p["stub_id"], "status": "dry_run_skipped"} for p in proposals
            ]
        else:
            manifest = Manifest.start(
                run_id=run_id,
                mode=mode,
                max_gaps=max_gaps,
                stubs=[
                    {"page_id": p["stub_id"], "title": p["title"]} for p in proposals
                ],
            )
            manifest_path = str(manifest.path)
            limiter = RateLimiter()
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
                        host = urlparse(url).netloc
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
                                        f"relevance {score:.2f} < "
                                        f"{AUGMENT_RELEVANCE_THRESHOLD}"
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
                        manifest.advance(
                            stub_id, "saved", payload={"raw_path": str(raw_path)}
                        )
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

                    if not fetched_ok and not any(
                        f["stub_id"] == stub_id for f in fetches
                    ):
                        manifest.advance(
                            stub_id, "failed", payload={"reason": "all URLs failed"}
                        )

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
                manifest.advance(
                    stub_id, "extracted", payload={"keys": list(extraction.keys())}
                )

            # Ingest
            try:
                ingest_result = ingest_source(
                    raw_path,
                    source_type="article",
                    extraction=extraction,
                    wiki_dir=wiki_dir,
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
            verdict, reason = _post_ingest_quality(
                page_path=stub_path, wiki_dir=wiki_dir
            )
            add_verdict(
                page_id=stub_id,
                verdict_type="augment",
                verdict=verdict,
                notes=(
                    f"{reason} | augmented from {f['url']} "
                    f"(relevance {f.get('relevance', 0):.2f})"
                ),
                issues=[],
            )
            verdicts.append(
                {"stub_id": stub_id, "verdict": verdict, "reason": reason}
            )

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
                    stub_path.write_text(
                        frontmatter.dumps(post), encoding="utf-8"
                    )

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
        ingests = [
            {"stub_id": p["stub_id"], "status": "dry_run_skipped"} for p in proposals
        ]

    summary_lines = [f"## Augment Summary (run {run_id[:8]}, mode={mode})"]
    summary_lines.append(f"- Stubs examined: {len(eligible)}")
    summary_lines.append(
        f"- Proposals: {sum(1 for p in proposals if p['action'] == 'propose')}"
    )
    if fetches is not None:
        saved = sum(1 for f in fetches if f["status"] == "saved")
        skipped = sum(1 for f in fetches if f["status"] == "skipped")
        failed = sum(
            1
            for f in fetches
            if f["status"] not in {"saved", "skipped", "dry_run_skipped"}
        )
        summary_lines.append(f"- Saved: {saved}, Skipped: {skipped}, Failed: {failed}")
    if manifest_path:
        summary_lines.append(f"- Manifest: {manifest_path}")

    if mode == "propose" and not dry_run and proposals:
        proposals_path = wiki_dir / "_augment_proposals.md"
        atomic_text_write(_format_proposals_md(proposals, run_id), proposals_path)
        summary_lines.append(f"- Proposals file: {proposals_path}")

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
    page_path.write_text(frontmatter.dumps(post), encoding="utf-8")


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
