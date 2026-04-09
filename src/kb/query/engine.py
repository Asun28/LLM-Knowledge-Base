"""Query engine — BM25 search + LLM synthesis with citations."""

import logging
from pathlib import Path

from kb.config import (
    BM25_B,
    BM25_K1,
    MAX_SEARCH_RESULTS,
    PAGERANK_SEARCH_WEIGHT,
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
    max_results = max(1, min(max_results, MAX_SEARCH_RESULTS))
    pages = load_all_pages(wiki_dir)
    if not pages:
        return []

    # Tokenize query; return empty if all tokens are stopwords (correct behavior)
    query_tokens = tokenize(question)
    if not query_tokens:
        return []

    # Build document corpus: title tokens (boosted) + content tokens
    documents = []
    for page in pages:
        title_tokens = tokenize(page["title"]) * SEARCH_TITLE_WEIGHT
        content_tokens = tokenize(page["content_lower"])
        documents.append(title_tokens + content_tokens)

    # Score with BM25
    index = BM25Index(documents)
    scores = index.score(query_tokens, k1=BM25_K1, b=BM25_B)

    # Blend PageRank into BM25 scores if weight > 0
    pagerank_scores: dict[str, float] = {}
    if PAGERANK_SEARCH_WEIGHT > 0:
        pagerank_scores = _compute_pagerank_scores(wiki_dir)

    # Pair scores with pages, filter zero scores
    scored = []
    for i, score in enumerate(scores):
        if score > 0:
            # Blend: final = bm25 * (1 + weight * normalized_pagerank)
            pr = pagerank_scores.get(pages[i]["id"], 0.0)
            blended = score * (1 + PAGERANK_SEARCH_WEIGHT * pr)
            scored.append({**pages[i], "score": round(blended, 4)})

    scored.sort(key=lambda p: p["score"], reverse=True)
    return scored[:max_results]


def _compute_pagerank_scores(wiki_dir: Path | None = None) -> dict[str, float]:
    """Compute normalized PageRank scores for all wiki pages.

    Returns a dict mapping page_id to normalized PageRank (0.0 to 1.0).
    Normalized so the maximum PageRank in the graph maps to 1.0.
    """
    try:
        import networkx as nx

        from kb.graph.builder import build_graph

        graph = build_graph(wiki_dir)
        if graph.number_of_nodes() == 0:
            return {}
        pr = nx.pagerank(graph)
        max_pr = max(pr.values()) if pr else 1.0
        if max_pr == 0:
            return {}
        return {node: score / max_pr for node, score in pr.items()}
    except Exception as e:
        logger.debug("Failed to compute PageRank for search blending: %s", e)
        return {}


def _build_query_context(pages: list[dict], max_chars: int = QUERY_CONTEXT_MAX_CHARS) -> dict:
    """Build context string from matching wiki pages for the LLM.

    Returns:
        dict with keys:
            context: The formatted context string.
            context_pages: List of page IDs actually included in context.
    """
    if not pages:
        return {"context": "No relevant wiki pages found.", "context_pages": []}
    sections = []
    context_pages = []
    total = 0
    skipped = 0
    for i, page in enumerate(pages):
        section = (
            f"--- Page: {page['id']} (type: {page['type']}, "
            f"confidence: {page['confidence']}) ---\n"
            f"Title: {page['title']}\n\n{page['content']}\n"
        )
        if total + len(section) > max_chars:
            if i == 0:
                logger.warning(
                    "Top-ranked page %s (%d chars) exceeds context limit (%d); skipping it",
                    page["id"],
                    len(section),
                    max_chars,
                )
            else:
                logger.debug("Page excluded from query context due to limit: %s", page["id"])
            skipped += 1
            continue
        sections.append(section)
        context_pages.append(page["id"])
        total += len(section)
    if skipped:
        logger.info(
            "Query context: included %d pages, skipped %d (limit: %d chars)",
            len(sections),
            skipped,
            max_chars,
        )
    # Fallback: if all pages exceeded the limit, truncate the top page rather than
    # returning an empty string (which would cause the LLM to hallucinate answers).
    if not sections and pages:
        top = pages[0]
        header = (
            f"--- Page: {top['id']} (type: {top['type']}, "
            f"confidence: {top['confidence']}) ---\n"
            f"Title: {top['title']}\n\n"
        )
        if max_chars <= len(header):
            return {
                "context": "No relevant wiki pages found.",
                "context_pages": [],
            }
        section = header + top["content"]
        logger.warning(
            "All pages exceeded context limit (%d chars); truncating top page %s",
            max_chars,
            top["id"],
        )
        sections.append(section[:max_chars])
        context_pages.append(top["id"])
    return {"context": "\n".join(sections), "context_pages": context_pages}


def query_wiki(question: str, wiki_dir: Path | None = None, max_results: int = 10) -> dict:
    """Query the knowledge base and synthesize an answer.

    Args:
        question: The user's question.
        wiki_dir: Path to wiki directory (uses config default if None).
        max_results: Maximum number of pages to retrieve for context.

    Returns:
        dict with keys: question, answer, citations, source_pages.
    """
    # 1. Search for relevant pages
    matching_pages = search_pages(question, wiki_dir, max_results=max_results)

    if not matching_pages:
        return {
            "question": question,
            "answer": "No relevant pages found in the knowledge base for this question.",
            "citations": [],
            "source_pages": [],
        }

    # 2. Build context from matching pages
    ctx = _build_query_context(matching_pages)
    context = ctx["context"]

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
        "context_pages": ctx["context_pages"],
    }
