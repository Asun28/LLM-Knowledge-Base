"""Query engine — BM25 search + LLM synthesis with citations."""

import logging
from pathlib import Path

from kb.config import (
    BM25_B,
    BM25_K1,
    QUERY_CONTEXT_MAX_CHARS,
    SEARCH_TITLE_WEIGHT,
)
from kb.query.bm25 import BM25Index, tokenize
from kb.query.citations import extract_citations
from kb.utils.llm import call_llm
from kb.utils.pages import load_all_pages

logger = logging.getLogger(__name__)


def search_pages(question: str, wiki_dir: Path | None = None, max_results: int = 10) -> list[dict]:
    """Search wiki pages using BM25 ranking.

    Builds a BM25 index over all wiki pages, with title tokens boosted by
    SEARCH_TITLE_WEIGHT. Returns pages ranked by BM25 relevance score.

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

    # Tokenize query
    query_tokens = tokenize(question)
    if not query_tokens:
        # All words were stopwords — use raw lowercased terms as fallback
        logger.debug("All query tokens were stopwords, falling back to raw terms")
        query_tokens = [w.lower().strip("?.,!") for w in question.split() if len(w) > 1]
    if not query_tokens:
        return []

    # Build document corpus: title tokens (boosted) + content tokens
    documents = []
    for page in pages:
        title_tokens = tokenize(page["title"]) * SEARCH_TITLE_WEIGHT
        content_tokens = tokenize(page["raw_content"])
        documents.append(title_tokens + content_tokens)

    # Score with BM25
    index = BM25Index(documents)
    scores = index.score(query_tokens, k1=BM25_K1, b=BM25_B)

    # Pair scores with pages, filter zero scores
    scored = []
    for i, score in enumerate(scores):
        if score > 0:
            pages[i]["score"] = round(score, 4)
            scored.append(pages[i])

    scored.sort(key=lambda p: p["score"], reverse=True)
    return scored[:max_results]


def _build_query_context(pages: list[dict], max_chars: int = QUERY_CONTEXT_MAX_CHARS) -> str:
    """Build context string from matching wiki pages for the LLM.

    Truncates to max_chars to avoid exceeding the model's context window.
    Pages are included in relevance order; partially-fitting pages are trimmed.
    """
    if not pages:
        return "No relevant wiki pages found."
    sections = []
    total = 0
    skipped = 0
    for page in pages:
        section = (
            f"--- Page: {page['id']} (type: {page['type']}, "
            f"confidence: {page['confidence']}) ---\n"
            f"Title: {page['title']}\n\n{page['content']}\n"
        )
        if total + len(section) > max_chars:
            skipped += 1
            logger.debug("Page excluded from query context due to limit: %s", page["id"])
            continue  # Try remaining pages (smaller ones may fit)
        sections.append(section)
        total += len(section)
    if skipped:
        logger.info(
            "Query context: included %d pages, skipped %d (limit: %d chars)",
            len(sections),
            skipped,
            max_chars,
        )
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
