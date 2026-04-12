"""Auto-contradiction detection — flag conflicts between new claims and existing wiki."""

import logging
import re

from kb.config import CONTRADICTION_MAX_CLAIMS_TO_CHECK


def _strip_markdown_structure(content: str) -> str:
    """Remove wikilinks and section headers before tokenizing for contradiction detection."""
    # Wikilinks: [[entities/foo|Display]] → Display (or foo if no display text)
    content = re.sub(
        r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]",
        lambda m: m.group(2) or m.group(1),
        content,
    )
    # Section headers: ## Evidence Trail → (removed)
    content = re.sub(r"^##+ .+$", "", content, flags=re.MULTILINE)
    return content

logger = logging.getLogger(__name__)


def detect_contradictions(
    new_claims: list[str],
    existing_pages: list[dict],
    max_claims: int = CONTRADICTION_MAX_CLAIMS_TO_CHECK,
) -> list[dict]:
    """Detect potential contradictions between new claims and existing wiki pages.

    Uses keyword overlap heuristic to find candidate conflicts:
    1. Extract significant tokens from each new claim
    2. Find existing pages with high token overlap
    3. Flag pairs where overlapping content contains contradictory signals

    Returns list of dicts with keys: new_claim, existing_page, existing_text, reason.
    """
    if not new_claims or not existing_pages:
        return []

    claims_to_check = new_claims[:max_claims]
    contradictions = []

    for claim in claims_to_check:
        claim_tokens = _extract_significant_tokens(claim)
        if len(claim_tokens) < 2:
            continue

        for page in existing_pages:
            page_content = _strip_markdown_structure(page.get("content", ""))
            page_tokens = _extract_significant_tokens(page_content)

            # Need substantial overlap to even consider checking
            overlap = claim_tokens & page_tokens
            if len(overlap) < 2:
                continue

            # Look for contradictory signal patterns in overlapping content
            matching_sentences = _find_overlapping_sentences(
                claim, page_content, overlap
            )
            for sentence in matching_sentences:
                if _has_contradiction_signal(claim, sentence):
                    contradictions.append({
                        "new_claim": claim,
                        "existing_page": page["id"],
                        "existing_text": sentence[:200],
                        "reason": "Potential factual conflict detected via keyword overlap",
                    })
                    break  # One contradiction per page per claim is enough

    return contradictions


# Contradiction signal words — suggest disagreement when co-occurring with shared entities
_CONTRADICTION_SIGNALS = re.compile(
    r"\b(not|never|no longer|instead|rather than|unlike|contrary|wrong|incorrect|"
    r"false|replaced|deprecated|obsolete|outdated)\b",
    re.IGNORECASE,
)

_STOPWORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would shall should may might can could of in to for with on at by from "
    "and or but if then else this that these those it its".split()
)


def _extract_significant_tokens(text: str) -> set[str]:
    """Extract significant lowercase tokens (no stopwords, length >= 3)."""
    words = re.findall(r"\b\w[\w-]*\w\b", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) >= 3}


def _find_overlapping_sentences(
    claim: str, page_content: str, overlap_tokens: set[str]
) -> list[str]:
    """Find sentences in page_content that share tokens with the claim."""
    sentences = re.split(r"(?<=[.!?])\s+", page_content)
    matching = []
    for s in sentences:
        s_tokens = _extract_significant_tokens(s)
        if len(s_tokens & overlap_tokens) >= 2:
            matching.append(s)
    return matching[:5]  # Cap to avoid excessive checking


def _has_contradiction_signal(claim: str, existing_sentence: str) -> bool:
    """Check if claim and existing sentence have contradictory signals."""
    # Both must share entities but one must contain a negation/contradiction word
    claim_has_signal = bool(_CONTRADICTION_SIGNALS.search(claim))
    existing_has_signal = bool(_CONTRADICTION_SIGNALS.search(existing_sentence))
    # Contradiction if exactly one side has the signal (asymmetric negation)
    return claim_has_signal != existing_has_signal
