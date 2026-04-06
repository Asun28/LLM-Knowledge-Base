"""Query engine — search wiki, synthesize answers with citations."""

import re
from pathlib import Path

from kb.config import QUERY_CONTEXT_MAX_CHARS, SEARCH_CONTENT_WEIGHT, SEARCH_TITLE_WEIGHT
from kb.query.citations import extract_citations
from kb.utils.llm import call_llm
from kb.utils.pages import load_all_pages


def search_pages(question: str, wiki_dir: Path | None = None, max_results: int = 10) -> list[dict]:
    """Search wiki pages by keyword matching.

    Simple keyword-based search: splits the question into words and scores pages
    by how many question words appear in their content.

    Args:
        question: The search query.
        wiki_dir: Path to wiki directory.
        max_results: Maximum number of results to return.

    Returns:
        List of matching page dicts sorted by relevance score (descending).
    """
    pages = load_all_pages(wiki_dir)
    if not pages:
        return []

    # Tokenize question into search terms
    stop_words = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "and",
        "or",
        "not",
        "with",
        "by",
        "from",
        "what",
        "how",
        "why",
        "when",
        "where",
        "which",
        "who",
        "does",
        "do",
        "can",
        "will",
        "should",
        "would",
        "it",
    }
    terms = [
        w.lower().strip("?.,!")
        for w in question.split()
        if w.lower().strip("?.,!") not in stop_words
    ]

    if not terms:
        # All words were stopwords — use the full question as a substring match
        # instead of individual common words that would match everything
        terms = [question.lower().strip("?.,!")]

    # Pre-compile word-boundary patterns for each term
    term_patterns = []
    for term in terms:
        escaped = re.escape(term)
        try:
            term_patterns.append(re.compile(rf"\b{escaped}\b"))
        except re.error:
            term_patterns.append(re.compile(re.escape(term)))

    scored = []
    for page in pages:
        score = 0
        content_lower = page["raw_content"]
        title_lower = page["title"].lower()
        for pattern in term_patterns:
            if pattern.search(title_lower):
                score += SEARCH_TITLE_WEIGHT
            if pattern.search(content_lower):
                score += SEARCH_CONTENT_WEIGHT
        if score > 0:
            page["score"] = score
            scored.append(page)

    scored.sort(key=lambda p: p["score"], reverse=True)
    return scored[:max_results]


def _build_query_context(
    pages: list[dict], max_chars: int = QUERY_CONTEXT_MAX_CHARS
) -> str:
    """Build context string from matching wiki pages for the LLM.

    Truncates to max_chars to avoid exceeding the model's context window.
    Pages are included in relevance order; partially-fitting pages are trimmed.
    """
    if not pages:
        return "No relevant wiki pages found."
    sections = []
    total = 0
    for page in pages:
        section = (
            f"--- Page: {page['id']} (type: {page['type']}, "
            f"confidence: {page['confidence']}) ---\n"
            f"Title: {page['title']}\n\n{page['content']}\n"
        )
        if total + len(section) > max_chars:
            remaining = max_chars - total
            if remaining > 200:
                sections.append(section[:remaining] + "\n[...truncated]")
            break
        sections.append(section)
        total += len(section)
    return "\n".join(sections)


def query_wiki(question: str, wiki_dir: Path | None = None) -> dict:
    """Query the knowledge base and synthesize an answer.

    Args:
        question: The user's question.
        wiki_dir: Path to wiki directory (uses config default if None).

    Returns:
        dict with keys: question, answer, citations, source_pages.
    """
    # 1. Search for relevant pages
    matching_pages = search_pages(question, wiki_dir)

    if not matching_pages:
        return {
            "question": question,
            "answer": "No relevant pages found in the knowledge base for this question.",
            "citations": [],
            "source_pages": [],
        }

    # 2. Build context from matching pages
    context = _build_query_context(matching_pages)

    # 3. Synthesize answer with LLM
    prompt = f"""You are answering a question using a knowledge wiki as your source.

QUESTION: {question}

WIKI CONTEXT:
{context}

INSTRUCTIONS:
- Answer the question based ONLY on the wiki context provided.
- Cite your sources using [source: page_id] format (e.g., [source: concepts/rag]).
- If the wiki doesn't contain enough information, say so clearly.
- Be concise but thorough.
- Distinguish between stated facts and inferences.
"""

    answer = call_llm(
        prompt,
        tier="orchestrate",
        system=(
            "You are a knowledge base assistant. "
            "Answer questions using wiki content with inline citations."
        ),
        max_tokens=2048,
    )

    # 4. Extract citations from the answer
    citations = extract_citations(answer)

    return {
        "question": question,
        "answer": answer,
        "citations": citations,
        "source_pages": [p["id"] for p in matching_pages],
    }
