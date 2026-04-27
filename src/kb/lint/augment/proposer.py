"""URL proposal, fallback, and relevance scoring helpers."""

from __future__ import annotations

import logging
import sys
from typing import Any

from kb import config
from kb.lint.fetcher import _registered_domain, _url_is_allowed
from kb.utils.llm import call_llm_json
from kb.utils.text import wrap_purpose

logger = logging.getLogger(__name__)

_ORIGINAL_CALL_LLM_JSON = call_llm_json

_PROPOSER_PROMPT_TEMPLATE = """\
You are proposing candidate URLs to enrich a stub wiki page.

Page title: {title}
Page type: {page_type}
Existing sources (avoid duplicates): {existing_sources}
Allowed domains (STRICT - URLs outside this list will be rejected): {allowed_domains}

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


def _call_llm_json(*args: Any, **kwargs: Any) -> Any:
    """Resolve LLM binding through either canonical or legacy patch target."""
    package = sys.modules.get("kb.lint.augment")
    package_call = (
        getattr(package, "call_llm_json", _ORIGINAL_CALL_LLM_JSON)
        if package is not None
        else _ORIGINAL_CALL_LLM_JSON
    )
    if package_call is not _ORIGINAL_CALL_LLM_JSON:
        return package_call(*args, **kwargs)
    return call_llm_json(*args, **kwargs)


def _build_proposer_prompt(stub: dict[str, Any], purpose_text: str) -> str:
    """Build proposer prompt with title repr-escaped + truncated to 100 chars."""
    title = repr(str(stub.get("title", ""))[:100])
    existing = stub.get("frontmatter", {}).get("source") or []
    if isinstance(existing, str):
        existing = [existing]
    existing_repr = [repr(str(s)[:200]) for s in existing[:10]]
    return _PROPOSER_PROMPT_TEMPLATE.format(
        title=title,
        page_type=stub.get("page_type", "concept"),
        existing_sources="[" + ", ".join(existing_repr) + "]",
        allowed_domains=list(config.AUGMENT_ALLOWED_DOMAINS),
        purpose=(
            wrap_purpose(purpose_text, max_chars=1000)
            if purpose_text
            else "(no purpose.md provided)"
        ),
    )


def _propose_urls(*, stub: dict[str, Any], purpose_text: str) -> dict[str, Any]:
    """Call scan-tier LLM proposer with eligibility-filtered stub."""
    prompt = _build_proposer_prompt(stub, purpose_text)
    try:
        response = _call_llm_json(prompt, tier="scan", schema=_PROPOSER_SCHEMA)
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
        if _url_is_allowed(u, config.AUGMENT_ALLOWED_DOMAINS):
            filtered.append(u)
        else:
            rd = _registered_domain(u)
            logger.info("Dropping off-allowlist proposed URL: %s (domain=%s)", u, rd)

    if not filtered:
        return {"action": "abstain", "reason": "no allowlisted URLs in proposer response"}

    return {"action": "propose", "urls": filtered, "rationale": response.get("rationale", "")}


def _wikipedia_fallback(*, page_id: str, title: str) -> str | None:
    """Derive a Wikipedia URL from an entity/concept page slug."""
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
    """Scan-tier relevance score (0.0-1.0) for extracted text vs stub topic."""
    prompt = (
        f"Score how relevant the following extracted text is to the topic "
        f"{stub_title!r}.\n"
        f'Return JSON: {{"score": <0.0-1.0>}}.\n\n'
        f"Extracted text (first 2000 chars):\n{extracted_text[:2000]}"
    )
    try:
        response = _call_llm_json(prompt, tier="scan", schema=_RELEVANCE_SCHEMA)
    except Exception as e:
        logger.warning("Relevance score LLM call failed: %s", e)
        return 0.0
    score = response.get("score")
    try:
        return float(score)
    except (TypeError, ValueError):
        return 0.0
