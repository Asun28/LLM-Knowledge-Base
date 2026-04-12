"""Tests for embedding wrapper and vector index (Phase 4)."""

import pytest

from kb.query.embeddings import embed_texts, VectorIndex


class TestEmbedTexts:
    def test_returns_array_for_single_text(self):
        vecs = embed_texts(["hello world"])
        assert len(vecs) == 1
        assert len(vecs[0]) > 0

    def test_returns_consistent_dims(self):
        vecs = embed_texts(["first text", "second text", "third text"])
        assert len(vecs) == 3
        dims = {len(v) for v in vecs}
        assert len(dims) == 1  # All same dimension

    def test_empty_input(self):
        vecs = embed_texts([])
        assert vecs == []


class TestVectorIndex:
    def test_build_and_query(self, tmp_path):
        db_path = tmp_path / "test_vec.db"
        idx = VectorIndex(db_path)
        idx.build([
            ("concepts/a", [1.0, 0.0, 0.0]),
            ("concepts/b", [0.0, 1.0, 0.0]),
            ("concepts/c", [0.9, 0.1, 0.0]),
        ])
        results = idx.query([1.0, 0.0, 0.0], limit=2)
        assert len(results) == 2
        # Closest match first
        assert results[0][0] == "concepts/a"
        # Second should be concepts/c (most similar to [1,0,0])
        assert results[1][0] == "concepts/c"

    def test_query_returns_page_id_and_distance(self, tmp_path):
        db_path = tmp_path / "test_vec.db"
        idx = VectorIndex(db_path)
        idx.build([("concepts/a", [1.0, 0.0])])
        results = idx.query([1.0, 0.0], limit=1)
        assert len(results) == 1
        page_id, distance = results[0]
        assert isinstance(page_id, str)
        assert isinstance(distance, float)

    def test_empty_index(self, tmp_path):
        db_path = tmp_path / "test_vec.db"
        idx = VectorIndex(db_path)
        idx.build([])
        results = idx.query([1.0, 0.0], limit=5)
        assert results == []
