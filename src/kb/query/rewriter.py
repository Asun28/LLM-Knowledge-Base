"""Multi-turn query rewriting — expand pronouns/references using conversation context."""

import logging
import re as _re
import unicodedata

from kb.config import MAX_CONVERSATION_CONTEXT_CHARS, MAX_REWRITE_CHARS
from kb.utils.llm import LLMError, call_llm

logger = logging.getLogger(__name__)

_REFERENCE_WORDS = _re.compile(r"\b(it|this|that|they|these|those|there|then)\b", _re.I)

# Phase 4.5 HIGH Q3: strip smart quotes, backticks, and single quotes from LLM output.
# Models frequently wrap rewrites in Unicode quotes that pass through as literal tokens.
_QUOTE_CHARS = "\"'\u201c\u201d\u2018\u2019`"

# J2 (Phase 4.5 R4 LOW): canonical standalone WH-question pattern. Matches
# "Who is Andrew Ng?" etc. but the proper-noun check must ignore the leading
# WH word itself (otherwise "How" trips the match and every how-question
# skips rewrite even when it references "it").
_WH_QUESTION_RE = _re.compile(r"^(who|what|where|when|why|how)\b.*\?$", _re.IGNORECASE)
_WH_LEADING_WORD = _re.compile(r"^(who|what|where|when|why|how)\s+", _re.IGNORECASE)
# Matches proper nouns (Andrew) AND acronyms (RAG, LLM, API).
_PROPER_NOUN_RE = _re.compile(r"\b(?:[A-Z][a-z]+|[A-Z]{2,})")

# Cycle 4 item #15 — CJK-safe short-query gate.
#
# The prior heuristic `len(long_words) < 5` used `question.split()`, which
# returns `[question]` for CJK input because there are no whitespace
# separators. Result: every CJK question ALWAYS triggered the scan-tier
# LLM rewrite, wasting a call per query. Universal short-query signal
# `len(question.strip()) < 15` catches the realistic CJK case (short
# follow-ups like "什么是RAG" or "它是什么") while leaving English
# follow-ups unaffected (15 chars is below almost any meaningful English
# follow-up that would need rewriting).


def _is_cjk_dominant(question: str) -> bool:
    """True when the question is dominated by CJK ideographic characters.

    Uses unicodedata script tags rather than a handcrafted range: any char
    whose Unicode block name starts with CJK, HIRAGANA, KATAKANA, or HANGUL
    counts. Dominance threshold: >=50% of stripped chars are CJK.
    """
    stripped = question.strip()
    if not stripped:
        return False
    cjk_chars = 0
    for ch in stripped:
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        if (
            name.startswith("CJK ")
            or name.startswith("HIRAGANA ")
            or name.startswith("KATAKANA ")
            or name.startswith("HANGUL ")
        ):
            cjk_chars += 1
    return cjk_chars / max(len(stripped), 1) >= 0.5


def _should_rewrite(question: str) -> bool:
    """Return True if this question likely needs rewriting (has deictic/pronoun refs).

    J2 (Phase 4.5 R4 LOW): skip rewriting when the question is a canonical
    standalone WH-question ending in '?' AND contains a proper-noun-like
    token AFTER the leading WH word (e.g. "Who is Andrew Ng?" → skip;
    "How does it work?" → still rewrite because "it" is deictic).

    Cycle 4 item #15: universal short-query gate — when CJK-dominant AND
    shorter than 15 chars, skip rewrite. Prevents wasteful scan-tier LLM
    calls on short CJK follow-ups that `question.split()` misclassifies
    as needing expansion.
    """
    if _WH_QUESTION_RE.match(question):
        # Strip the leading WH word before scanning for a proper noun so
        # the WH word itself doesn't satisfy the check.
        body = _WH_LEADING_WORD.sub("", question, count=1)
        if _PROPER_NOUN_RE.search(body):
            return False
    # Cycle 4 item #15 — CJK short-query skip.
    if _is_cjk_dominant(question) and len(question.strip()) < 15:
        return False
    if _REFERENCE_WORDS.search(question):
        return True
    words = question.split()
    long_words = [w for w in words if len(w) > 3]
    return len(long_words) < 5


def rewrite_query(
    question: str,
    conversation_context: str | None = None,
) -> str:
    """Rewrite a follow-up query into a standalone query using conversation context.

    If no conversation context is provided or the question appears standalone,
    returns the original question unchanged. Uses a scan-tier LLM call to
    expand pronouns and references.

    Args:
        question: The user's current question.
        conversation_context: Recent conversation history (Q&A pairs).

    Returns:
        The rewritten standalone query, or the original if no rewriting needed.
    """
    if not question:
        return question

    if not conversation_context or not conversation_context.strip():
        return question

    # Truncate context to budget
    context = conversation_context[:MAX_CONVERSATION_CONTEXT_CHARS]

    # Heuristic skip: if question is already standalone (no deictic refs, enough content words)
    if not _should_rewrite(question):
        return question

    try:
        prompt = (
            "Rewrite the following follow-up question into a standalone question "
            "that can be understood without prior conversation context. "
            "Expand any pronouns (it, they, this) and references to be specific. "
            "If the question is already standalone, return it unchanged. "
            "Reply with ONLY the rewritten question, no explanation.\n\n"
            f"CONVERSATION CONTEXT:\n{context}\n\n"
            f"FOLLOW-UP QUESTION: {question}\n\n"
            "STANDALONE QUESTION:"
        )
        rewritten = call_llm(prompt, tier="scan", max_tokens=200)
        rewritten = rewritten.strip().strip(_QUOTE_CHARS)
        # Cycle 6 AC3: reject LLM-preamble-leaked rewrites ("Sure! Here's…",
        # "The standalone question is:", etc.) by reusing the battle-hardened
        # _LEAK_KEYWORD_RE from engine.py (two rounds of false-positive
        # hardening behind it — see engine.py:287-307). Without this gate,
        # preamble text gets tokenized into BM25, embedded for vector search,
        # AND threaded into the synthesis prompt — silently polluting every
        # downstream stage.
        from kb.query.engine import _LEAK_KEYWORD_RE

        if _LEAK_KEYWORD_RE.match(rewritten):
            logger.warning(
                "rewrite_query output rejected as preamble-leak; reverting to original: %r",
                rewritten[:80],
            )
            return question
        # J1 (Phase 4.5 MEDIUM): absolute cap + floor. Previous bound
        # `3 * len(question)` was too tight for short reference questions
        # ("what about it?" → 46-char expansion exceeded 3×) and too loose
        # for long LLM rambles. Floor at max(3*len, 120) preserves legitimate
        # short expansions; hard ceiling MAX_REWRITE_CHARS (500) catches
        # runaway output.
        upper = min(MAX_REWRITE_CHARS, max(3 * len(question), 120))
        if len(rewritten) > upper:
            logger.debug(
                "Rewrite too long (%d chars, cap=%d); falling back",
                len(rewritten),
                upper,
            )
            return question
        if rewritten:
            return rewritten
    except LLMError as e:
        logger.warning("Query rewriting failed for %r (non-fatal): %s", question[:80], e)

    return question
