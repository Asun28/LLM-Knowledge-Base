"""4-layer search result dedup pipeline.

Layers:
1. By source — highest-scoring result per page
2. By text similarity — Jaccard > threshold drops near-duplicates
3. By type diversity — no page type exceeds max ratio
4. Per-page cap — max N results per page
"""

import math

from kb.config import DEDUP_JACCARD_THRESHOLD, DEDUP_MAX_PER_PAGE, DEDUP_MAX_TYPE_RATIO


def dedup_results(
    results: list[dict],
    *,
    jaccard_threshold: float = DEDUP_JACCARD_THRESHOLD,
    max_type_ratio: float = DEDUP_MAX_TYPE_RATIO,
    max_per_page: int = DEDUP_MAX_PER_PAGE,
) -> list[dict]:
    """Apply 4-layer dedup to search results. Returns filtered list."""
    if not results:
        return []
    deduped = _dedup_by_source(results)
    deduped = _dedup_by_text_similarity(deduped, jaccard_threshold)
    deduped = _enforce_type_diversity(deduped, max_type_ratio)
    deduped = _cap_per_page(deduped, max_per_page)
    return deduped


def _dedup_by_source(results: list[dict]) -> list[dict]:
    """Layer 1: Keep highest-scoring result per page."""
    by_page: dict[str, dict] = {}
    for r in results:
        pid = r["id"]
        existing = by_page.get(pid)
        if existing is None or r["score"] > existing["score"]:
            by_page[pid] = r
    return sorted(by_page.values(), key=lambda r: r["score"], reverse=True)


def _dedup_by_text_similarity(results: list[dict], threshold: float) -> list[dict]:
    """Layer 2: Remove results with Jaccard similarity > threshold to kept results."""
    kept: list[dict] = []
    for r in results:
        r_words = set(r.get("content_lower", "").split())
        too_similar = False
        for k in kept:
            k_words = set(k.get("content_lower", "").split())
            intersection = r_words & k_words
            union = r_words | k_words
            jaccard = len(intersection) / len(union) if union else 0.0
            if jaccard > threshold:
                too_similar = True
                break
        if not too_similar:
            kept.append(r)
    return kept


def _enforce_type_diversity(results: list[dict], max_ratio: float) -> list[dict]:
    """Layer 3: No page type exceeds max_ratio of total results."""
    max_per_type = max(1, math.ceil(len(results) * max_ratio))
    type_counts: dict[str, int] = {}
    kept: list[dict] = []
    for r in results:
        t = r.get("type", "unknown")
        count = type_counts.get(t, 0)
        if count < max_per_type:
            kept.append(r)
            type_counts[t] = count + 1
    return kept


def _cap_per_page(results: list[dict], max_per_page: int) -> list[dict]:
    """Layer 4: Cap results per page."""
    page_counts: dict[str, int] = {}
    kept: list[dict] = []
    for r in results:
        pid = r["id"]
        count = page_counts.get(pid, 0)
        if count < max_per_page:
            kept.append(r)
            page_counts[pid] = count + 1
    return kept
