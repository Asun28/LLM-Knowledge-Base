"""Augment orchestrator for kb_lint --augment.

Three-gate execution model (see docs/superpowers/specs/2026-04-15-kb-lint-augment-design.md):
  1. propose       — analyze stubs, write proposals to wiki/_augment_proposals.md
  2. --execute     — fetch URLs, save raw files (no ingest)
  3. --auto-ingest — pre-extract at scan tier, ingest, write quality verdict
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import frontmatter

from kb.config import (
    AUGMENT_ALLOWED_DOMAINS,
    AUGMENT_COOLDOWN_HOURS,
    AUTOGEN_PREFIXES,
    WIKI_DIR,
)
from kb.graph.builder import build_graph
from kb.lint.checks import check_stub_pages
from kb.lint.fetcher import _registered_domain
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
  {{"action": "abstain", "reason": "no authoritative source in allowlist | out of scope | ambiguous title"}}

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
        if _url_is_allowed(u):
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


def _url_is_allowed(url: str) -> bool:
    """Return True if URL's host matches AUGMENT_ALLOWED_DOMAINS.

    Match rule: either the registered domain (eTLD+1) OR the full netloc must
    equal an allowlist entry, OR the netloc must be a subdomain of an allowlist
    entry (e.g., "en.wikipedia.org" allows "xx.en.wikipedia.org"). This lets
    the allowlist use narrow entries like "en.wikipedia.org" without requiring
    eTLD+1 matching, and still accepts "arxiv.org" directly.
    """
    try:
        netloc = urlparse(url).netloc.lower()
    except (ValueError, AttributeError):
        return False
    if not netloc:
        return False
    # Strip userinfo/port
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    if ":" in netloc:
        netloc = netloc.rsplit(":", 1)[0]
    rd = _registered_domain(url)
    rd_lower = rd.lower() if rd else None
    for d in AUGMENT_ALLOWED_DOMAINS:
        dl = d.lower()
        if netloc == dl or netloc.endswith("." + dl):
            return True
        if rd_lower and rd_lower == dl:
            return True
    return False


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
