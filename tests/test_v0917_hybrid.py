"""Tests for RRF fusion and hybrid search (Phase 4)."""

from kb.query.hybrid import rrf_fusion


class TestRRFFusion:
    def test_single_list(self):
        results = [
            {"id": "a", "score": 10.0},
            {"id": "b", "score": 5.0},
        ]
        fused = rrf_fusion([results])
        assert len(fused) == 2
        assert fused[0]["id"] == "a"  # Rank 0 → 1/(60+0) > 1/(60+1)

    def test_two_lists_same_order(self):
        list1 = [{"id": "a", "score": 10.0}, {"id": "b", "score": 5.0}]
        list2 = [{"id": "a", "score": 0.9}, {"id": "b", "score": 0.5}]
        fused = rrf_fusion([list1, list2])
        assert fused[0]["id"] == "a"  # Appears rank 0 in both lists

    def test_two_lists_disjoint(self):
        list1 = [{"id": "a", "score": 10.0}]
        list2 = [{"id": "b", "score": 0.9}]
        fused = rrf_fusion([list1, list2])
        assert len(fused) == 2
        # Both at rank 0 in their list, so equal RRF score — either order OK
        ids = {r["id"] for r in fused}
        assert ids == {"a", "b"}

    def test_boosted_by_multiple_lists(self):
        list1 = [{"id": "a", "score": 10.0}, {"id": "b", "score": 5.0}]
        list2 = [{"id": "b", "score": 0.9}, {"id": "c", "score": 0.5}]
        fused = rrf_fusion([list1, list2])
        # b appears in both lists (rank 1 + rank 0) so gets boosted
        b_score = next(r["score"] for r in fused if r["id"] == "b")
        c_score = next(r["score"] for r in fused if r["id"] == "c")
        assert b_score > c_score

    def test_empty_lists(self):
        assert rrf_fusion([]) == []
        assert rrf_fusion([[], []]) == []

    def test_rrf_scores_are_positive(self):
        results = [{"id": "a", "score": 1.0}]
        fused = rrf_fusion([results])
        assert all(r["score"] > 0 for r in fused)
