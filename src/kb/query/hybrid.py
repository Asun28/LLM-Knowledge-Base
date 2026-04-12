"""Hybrid search — RRF fusion of BM25 + vector search with multi-query expansion."""

import logging

from kb.config import BM25_SEARCH_LIMIT_MULTIPLIER, RRF_K, VECTOR_SEARCH_LIMIT_MULTIPLIER

logger = logging.getLogger(__name__)


def rrf_fusion(lists: list[list[dict]], k: int = RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion: merge multiple ranked lists.

    Each result gets score = sum(1 / (k + rank)) across all lists it appears in.
    Results are identified by their 'id' key.
    """
    if not lists:
        return []

    scores: dict[str, dict] = {}
    for result_list in lists:
        for rank, result in enumerate(result_list):
            pid = result["id"]
            rrf_score = 1.0 / (k + rank)
            if pid in scores:
                scores[pid]["score"] += rrf_score
            else:
                scores[pid] = {**result, "score": rrf_score}

    return sorted(scores.values(), key=lambda r: r["score"], reverse=True)


def hybrid_search(
    question: str,
    bm25_fn,
    vector_fn,
    expand_fn=None,
    *,
    limit: int = 10,
) -> list[dict]:
    """Run hybrid BM25 + vector search with optional multi-query expansion.

    Args:
        question: The user query.
        bm25_fn: Callable(query, limit) -> list[dict] — BM25 search.
        vector_fn: Callable(query, limit) -> list[dict] — vector search.
        expand_fn: Optional callable(query) -> list[str] — returns alternative phrasings.
        limit: Maximum results to return.
    """
    vector_limit = limit * VECTOR_SEARCH_LIMIT_MULTIPLIER

    # Determine query variants
    queries = [question]
    if expand_fn:
        try:
            expanded = expand_fn(question)
            queries = [question, *expanded][:3]
        except Exception as e:
            logger.debug("Query expansion failed (non-fatal): %s", e)

    # Collect all result lists
    all_lists: list[list[dict]] = []

    # Intentional asymmetry: BM25 scores the ORIGINAL query only. Vector search uses
    # original + semantically expanded variants. BM25 is sensitive to exact-token drift
    # from expansion; cosine similarity handles semantic equivalence naturally, so
    # expanded queries are safe for vector search but degrade BM25 precision.
    bm25_limit = limit * BM25_SEARCH_LIMIT_MULTIPLIER
    bm25_results = bm25_fn(question, bm25_limit)
    if bm25_results:
        all_lists.append(bm25_results)

    # Vector search on all query variants
    for q in queries:
        vec_results = vector_fn(q, vector_limit)
        if vec_results:
            all_lists.append(vec_results)

    if not all_lists:
        return []

    return rrf_fusion(all_lists)[:limit]
