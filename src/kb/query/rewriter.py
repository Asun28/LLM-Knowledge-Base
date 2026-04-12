"""Multi-turn query rewriting — expand pronouns/references using conversation context."""

import logging

from kb.config import MAX_CONVERSATION_CONTEXT_CHARS

logger = logging.getLogger(__name__)


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

    # Heuristic skip: if question has enough content words, likely standalone
    words = question.split()
    content_words = [w for w in words if len(w) > 3]
    if len(content_words) >= 5:
        return question

    try:
        from kb.utils.llm import call_llm

        prompt = (
            "Rewrite the following follow-up question into a standalone question "
            "that can be understood without prior conversation context. "
            "Expand any pronouns (it, they, this) and references to be specific. "
            "If the question is already standalone, return it unchanged.\n\n"
            f"CONVERSATION CONTEXT:\n{context}\n\n"
            f"FOLLOW-UP QUESTION: {question}\n\n"
            "STANDALONE QUESTION:"
        )
        rewritten = call_llm(prompt, tier="scan", max_tokens=200)
        rewritten = rewritten.strip().strip('"')
        if rewritten:
            return rewritten
    except Exception as e:
        logger.debug("Query rewriting failed (non-fatal): %s", e)

    return question
