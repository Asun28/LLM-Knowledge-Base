"""Auto-contradiction detection — flag conflicts between new claims and existing wiki."""

import logging
import re

from kb.config import CONTRADICTION_MAX_CLAIMS_TO_CHECK
from kb.utils.text import STOPWORDS as _STOPWORDS


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

    if len(new_claims) > max_claims:
        # Phase 4.5 HIGH D5: promote to WARNING — silent claim truncation hid
        # the fact that the last N claims were never checked for contradictions.
        logger.warning(
            "Checking first %d of %d claims for contradictions (truncated — %d unchecked)",
            max_claims,
            len(new_claims),
            len(new_claims) - max_claims,
        )
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


def _extract_significant_tokens(text: str) -> set[str]:
    """Extract significant lowercase tokens (no stopwords, length >= 3).

    E1 (Phase 4.5 R4 HIGH): preserve short language-name tokens that the
    general length>=3 filter drops. `C`, `R`, `Go`, `C++`, `F#`, `C#`,
    `.NET` carry identity we don't want to lose — a claim about "R is
    outdated" vs existing page mentioning "R" could not participate in
    overlap detection before this fix.

    Two passes: (1) match language-name patterns case-sensitively on the
    original text (so `C` matches but not `c` in "can"); (2) general word
    tokens with >=3 length floor on the lowercased text. Union, stopword
    filter, return. Both passes preserve `+`/`#`/`.` where they're part of
    the language name.
    """
    # Pass 1: language-name tokens — match on ORIGINAL case so `C` / `R` /
    # `Go` only match when capitalized (avoids "can" → "c"). Preserves
    # C++, F#, C#, .NET by including `+`/`#`/`.` in the character class
    # after the anchor letter.
    lang_tokens: set[str] = set()
    for m in re.finditer(r"(?:\.NET|[A-Z][+#a-z]*)", text):
        tok = m.group(0).lower()
        # Only keep if short (>=3 passes through normal filter below) AND
        # the token shape looks like a language name, not a proper noun.
        if len(tok) < 3 and (len(tok) == 1 or tok in {"go", "r"}) or any(
            ch in tok for ch in "+#."
        ):
            lang_tokens.add(tok)
    # Pass 2: general words
    words = re.findall(r"\b\w[\w-]*\w\b", text.lower())
    general = {w for w in words if w not in _STOPWORDS and len(w) >= 3}
    return (lang_tokens | general) - _STOPWORDS


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
    """Check if claim and existing sentence have contradictory signals.

    Returns True when exactly one of the two texts contains a negation or
    contradiction keyword (asymmetric negation heuristic).

    Known limitation: when BOTH sides contain negation words (e.g., "X is not fast"
    vs "X is not slow"), the symmetric check returns False and no contradiction is
    flagged, even though they make different claims. Extending this would require
    semantic parsing beyond the current keyword heuristic.
    """
    # Both must share entities but one must contain a negation/contradiction word
    claim_has_signal = bool(_CONTRADICTION_SIGNALS.search(claim))
    existing_has_signal = bool(_CONTRADICTION_SIGNALS.search(existing_sentence))
    # Contradiction if exactly one side has the signal (asymmetric negation)
    return claim_has_signal != existing_has_signal
