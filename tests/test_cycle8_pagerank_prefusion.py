"""Cycle 8 PageRank pre-fusion search coverage."""

from __future__ import annotations

from pathlib import Path

from kb.query import engine
from kb.query.hybrid import rrf_fusion as real_rrf_fusion


def _page(page_id: str, title: str, content: str | None = None) -> dict:
    body = content or f"retrieval unique body for {page_id}"
    return {
        "id": page_id,
        "path": f"wiki/{page_id}.md",
        "title": title,
        "type": "concept",
        "confidence": "stated",
        "sources": [],
        "created": "2026-04-01",
        "updated": "2026-04-02",
        "content": body,
        "content_lower": body.lower(),
    }


def test_pagerank_enters_rrf_as_rank_list_with_pinned_top_five(monkeypatch):
    pages = [
        _page("concepts/alpha", "Alpha"),
        _page("concepts/bravo", "Bravo"),
        _page("concepts/charlie", "Charlie"),
        _page("concepts/delta", "Delta"),
        _page("concepts/echo", "Echo"),
        _page("concepts/foxtrot", "Foxtrot"),
    ]
    pagerank_scores = {
        "concepts/alpha": 0.10,
        "concepts/bravo": 0.90,
        "concepts/charlie": 0.40,
        "concepts/delta": 0.70,
        "concepts/echo": 0.20,
        "concepts/foxtrot": 0.99,
    }
    captured_lists: list[list[dict]] = []
    fused_top_five: list[str] = []
    original_exists = Path.exists

    monkeypatch.setattr(engine, "PAGERANK_SEARCH_WEIGHT", 1)
    monkeypatch.setattr(engine, "load_all_pages", lambda wiki_dir=None: pages)
    monkeypatch.setattr(engine, "_wiki_bm25_cache_key", lambda wiki_dir: None)
    monkeypatch.setattr(engine, "_compute_pagerank_scores", lambda *a, **k: pagerank_scores)
    monkeypatch.setattr(
        engine.Path,
        "exists",
        lambda self: True if str(self).endswith(".sqlite") else original_exists(self),
    )

    class FakeVectorIndex:
        def query(self, _vec, limit):
            return [
                ("concepts/delta", 0.1),
                ("concepts/echo", 0.2),
                ("concepts/foxtrot", 0.3),
            ][:limit]

    monkeypatch.setattr("kb.query.embeddings.embed_texts", lambda texts: [[0.1, 0.2]])
    monkeypatch.setattr("kb.query.embeddings.get_vector_index", lambda path: FakeVectorIndex())

    def spy_rrf(lists):
        captured_lists[:] = [[dict(item) for item in result_list] for result_list in lists]
        fused = real_rrf_fusion(lists)
        fused_top_five[:] = [item["id"] for item in fused[:5]]
        return fused

    monkeypatch.setattr(engine, "rrf_fusion", spy_rrf)

    engine.search_pages("retrieval", wiki_dir=Path("wiki"), max_results=5)

    assert len(captured_lists) == 3
    bm25_ids = [item["id"] for item in captured_lists[0]]
    vector_ids = [item["id"] for item in captured_lists[1]]
    pagerank_ids = [item["id"] for item in captured_lists[2]]
    candidates = []
    for page_id in bm25_ids + vector_ids:
        if page_id not in candidates:
            candidates.append(page_id)
    expected_pagerank_ids = sorted(
        candidates,
        key=lambda page_id: (-pagerank_scores[page_id], candidates.index(page_id)),
    )
    assert pagerank_ids == expected_pagerank_ids
    # RRF_K=60 constant used in scoring; update snapshot if RRF_K changes
    assert fused_top_five == [
        "concepts/delta",
        "concepts/foxtrot",
        "concepts/echo",
        "concepts/bravo",
        "concepts/alpha",
    ]


def test_weight_zero_skips_pagerank_rank_list(monkeypatch):
    pages = [_page("concepts/alpha", "Alpha"), _page("concepts/bravo", "Bravo")]
    captured_lengths: list[int] = []
    original_exists = Path.exists

    monkeypatch.setattr(engine, "PAGERANK_SEARCH_WEIGHT", 0)
    monkeypatch.setattr(engine, "load_all_pages", lambda wiki_dir=None: pages)
    monkeypatch.setattr(engine, "_wiki_bm25_cache_key", lambda wiki_dir: None)
    monkeypatch.setattr(engine, "_compute_pagerank_scores", lambda *a, **k: {"concepts/bravo": 1.0})
    monkeypatch.setattr(
        engine.Path,
        "exists",
        lambda self: False if str(self).endswith(".sqlite") else original_exists(self),
    )

    def spy_rrf(lists):
        captured_lengths.append(len(lists))
        return real_rrf_fusion(lists)

    monkeypatch.setattr(engine, "rrf_fusion", spy_rrf)

    engine.search_pages("retrieval", wiki_dir=Path("wiki"), max_results=2)

    assert captured_lengths == [1]
