"""Query-side text helpers.

Two related but distinct concerns:

* **Rewriting for retrieval** (:func:`rewrite_query`) — expand pronouns /
  references using prior conversation context so BM25/vector retrieval
  has the entity name to match against.
* **Rephrasing for the user** (:func:`_suggest_rephrasings`, cycle 16
  AC7-AC9) — when retrieval coverage is low, propose alternative phrasings
  that match different page titles so the operator can re-issue the query.

Both are LLM scan-tier calls; both live here to share the same error-
swallow + length-cap discipline.
"""

import logging
import re as _re
import unicodedata

from kb.config import MAX_CONVERSATION_CONTEXT_CHARS, MAX_REWRITE_CHARS, QUERY_REPHRASING_MAX
from kb.utils.llm import LLMError, call_llm
from kb.utils.text import yaml_escape

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


# ── Cycle 16 AC7-AC9 — low-coverage rephrasing suggestions ─────────
# Moved from kb.query.engine in cycle 42 AC4 — rephrasing-for-UI is a
# query-side text concern, not a search-engine one. engine.py re-exports
# the public names so existing test monkeypatches (`engine._suggest_rephrasings`)
# still work.
_BULLET_PREFIX_RE = _re.compile(r"^\s*(?:\d+[.)]|[-*•])\s*")


def _build_rephrasing_prompt(question: str, titles_block: str, max_suggestions: int) -> str:
    """Compose the scan-tier rephrasing prompt without str.format() risk.

    Built via plain string concatenation rather than ``str.format(named_kwargs)``
    so there is zero interaction between user-supplied question content and
    Python's formatting machinery.
    """
    return (
        'The user asked: "' + question + '"\n'
        "Known wiki pages (titles only):\n"
        + titles_block
        + "\nSuggest up to "
        + str(max_suggestions)
        + " alternative phrasings that would match different\n"
        "page titles. Return one phrasing per line. Do not repeat the original question.\n"
    )


def _normalise_for_echo(s: str) -> str:
    """Collapse punctuation + case + whitespace to a canonical form for echo-filter."""
    return _re.sub(r"[\W_]+", " ", s).strip().lower()


def _suggest_rephrasings(
    question: str,
    context_pages: list[dict],
    *,
    max_suggestions: int = QUERY_REPHRASING_MAX,
) -> list[str]:
    """Return up to ``max_suggestions`` alternative phrasings grounded in ``context_pages``.

    Cycle 16 AC7-AC9 contract:
      - Empty ``context_pages`` → return ``[]`` without LLM call.
      - Any :class:`LLMError` or :class:`OSError` → return ``[]`` (never raises).
      - Per-line hardening (Q5/C5): strip bullet/number prefix, drop empty /
        > 300-char / embedded-newline lines, drop echoes via
        :func:`_normalise_for_echo` (case + whitespace + punctuation insensitive).
      - Logs only ``question[:80]`` — never the full question (T11).
      - Titles in the prompt are truncated to 200 chars each and wrapped in
        ``<page_title>…</page_title>`` fences to prevent instruction injection (T4).
    """
    if not context_pages:
        return []
    logger.info("rephrasings request for q=%r", question[:80])

    titles: list[str] = []
    for page in context_pages[: max_suggestions * 3]:
        raw_title = str(page.get("title") or page.get("id") or "")
        if not raw_title:
            continue
        safe = yaml_escape(raw_title)[:200]
        titles.append(f"<page_title>{safe}</page_title>")
    titles_block = "\n".join(titles) if titles else "<page_title></page_title>"

    prompt = _build_rephrasing_prompt(
        question=question[:80],
        titles_block=titles_block,
        max_suggestions=max_suggestions,
    )
    try:
        raw = call_llm(prompt, tier="scan")
    except (LLMError, OSError) as exc:
        logger.debug("rephrasings failed: %s", exc)
        return []

    normalised_question = _normalise_for_echo(question)
    out: list[str] = []
    for line in raw.splitlines():
        candidate = _BULLET_PREFIX_RE.sub("", line.strip()).strip()
        if not candidate:
            continue
        if len(candidate) > 300:
            continue
        if "\n" in candidate:
            continue
        if _normalise_for_echo(candidate) == normalised_question:
            continue
        out.append(candidate)
        if len(out) >= max_suggestions:
            break
    return out
