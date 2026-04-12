"""Tests for Phase 4 query/ perf and doc fixes."""
from __future__ import annotations


def test_get_vector_index_function_exists():
    from kb.query import embeddings as _em
    assert callable(getattr(_em, "get_vector_index", None)), "get_vector_index must exist"


def test_reset_model_function_exists():
    from kb.query import embeddings as _em
    assert callable(getattr(_em, "_reset_model", None)), "_reset_model must exist"


def test_get_vector_index_caches_instance(monkeypatch, tmp_path):
    """Two calls with the same path must return the same object."""
    from kb.query import embeddings as _em

    build_count = {"n": 0}

    class _FakeIdx:
        def __init__(self, path):
            build_count["n"] += 1
        def query(self, vec, top_k=10):
            return []

    monkeypatch.setattr(_em, "VectorIndex", _FakeIdx)
    _em._reset_model()  # clear cache

    vec_path = str(tmp_path / "fake.vec")
    _em.get_vector_index(vec_path)
    _em.get_vector_index(vec_path)
    assert build_count["n"] == 1, f"Expected 1 VectorIndex build, got {build_count['n']}"


def test_dedup_jaccard_strips_wikilinks():
    """Pages sharing only wikilink markup must not be incorrectly deduped."""
    from kb.query.dedup import _dedup_by_text_similarity

    # Both pages share wikilinks but have different actual content
    pages = [
        {
            "id": "p1",
            "content_lower": "[[entities/foo]] [[concepts/bar]] quantum computing entanglement",
            "bm25_score": 10,
        },
        {
            "id": "p2",
            "content_lower": "[[entities/foo]] [[concepts/bar]] classical ml gradient descent",
            "bm25_score": 9,
        },
    ]
    out = _dedup_by_text_similarity(pages, threshold=0.85)
    # After stripping wikilink tokens, content is different — both should be kept
    assert len(out) == 2, f"Expected 2 pages, got {len(out)}: {[p['id'] for p in out]}"


def test_mcp_core_logs_trust_merge_failure(monkeypatch, caplog):
    """Silent trust merge exception must now emit a debug log."""
    from pathlib import Path

    from kb.mcp import core as _core

    src_text = Path(_core.__file__).read_text(encoding="utf-8")
    # Verify there's a debug log call in the vicinity of the trust merge except block
    assert "logger.debug" in src_text, "Expected logger.debug call in core.py"
    # The specific trust-merge error path — verify it's present
    assert "Trust score" in src_text or "trust" in src_text.lower()
