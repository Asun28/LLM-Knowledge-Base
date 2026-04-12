"""Tests for 4-layer search dedup pipeline (Phase 4)."""

from kb.query.dedup import dedup_results


def _result(page_id, score, page_type="concept", text="some content here"):
    return {"id": page_id, "score": score, "type": page_type, "content_lower": text}


class TestDedupBySource:
    def test_keeps_highest_score_per_page(self):
        results = [
            _result("concepts/a", 5.0),
            _result("concepts/a", 3.0),
            _result("concepts/b", 4.0),
        ]
        deduped = dedup_results(results)
        ids = [r["id"] for r in deduped]
        assert ids.count("concepts/a") == 1
        assert deduped[0]["score"] == 5.0

    def test_preserves_order_by_score(self):
        results = [
            _result("concepts/a", 5.0),
            _result("concepts/b", 3.0),
            _result("concepts/c", 1.0),
        ]
        deduped = dedup_results(results)
        scores = [r["score"] for r in deduped]
        assert scores == sorted(scores, reverse=True)


class TestDedupByTextSimilarity:
    def test_removes_near_duplicate_text(self):
        results = [
            _result("concepts/a", 5.0, text="the transformer architecture uses attention"),
            _result("concepts/b", 4.0, text="the transformer architecture uses attention mechanisms"),
        ]
        deduped = dedup_results(results, jaccard_threshold=0.7)
        assert len(deduped) == 1
        assert deduped[0]["id"] == "concepts/a"  # Higher score kept

    def test_keeps_different_content(self):
        results = [
            _result("concepts/a", 5.0, text="transformers use self-attention mechanisms"),
            _result("concepts/b", 4.0, text="recurrent neural networks process sequences"),
        ]
        deduped = dedup_results(results)
        assert len(deduped) == 2


class TestDedupByTypeDiversity:
    def test_caps_single_type(self):
        results = [_result(f"entities/e{i}", 10 - i, "entity") for i in range(10)]
        results.append(_result("concepts/c1", 0.5, "concept"))
        deduped = dedup_results(results, max_type_ratio=0.6)
        entity_count = sum(1 for r in deduped if r["type"] == "entity")
        total = len(deduped)
        assert entity_count <= int(total * 0.6) + 1  # Allow rounding


class TestDedupPerPageCap:
    def test_caps_results_per_page(self):
        results = [
            _result("concepts/a", 5.0, text="first chunk about topic"),
            _result("concepts/a", 4.5, text="second chunk about topic"),
            _result("concepts/a", 4.0, text="third chunk about topic"),
        ]
        deduped = dedup_results(results, max_per_page=2)
        a_count = sum(1 for r in deduped if r["id"] == "concepts/a")
        assert a_count <= 2


class TestDedupEndToEnd:
    def test_empty_input(self):
        assert dedup_results([]) == []

    def test_single_result(self):
        results = [_result("concepts/a", 5.0)]
        assert len(dedup_results(results)) == 1
