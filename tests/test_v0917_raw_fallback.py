"""Tests for raw-source fallback retrieval (Phase 4)."""

from kb.query.engine import search_raw_sources


class TestSearchRawSources:
    def test_finds_matching_raw_file(self, tmp_project, create_raw_source):
        create_raw_source("raw/articles/attention.md", "The attention mechanism computes...", tmp_project)
        results = search_raw_sources("attention mechanism", raw_dir=tmp_project / "raw", max_results=5)
        assert len(results) >= 1
        assert any("attention" in r["id"] for r in results)

    def test_returns_empty_for_no_match(self, tmp_project, create_raw_source):
        create_raw_source("raw/articles/unrelated.md", "Nothing relevant.", tmp_project)
        results = search_raw_sources("quantum computing entanglement", raw_dir=tmp_project / "raw", max_results=5)
        assert len(results) == 0

    def test_result_has_expected_keys(self, tmp_project, create_raw_source):
        create_raw_source("raw/articles/test.md", "Test content about transformers.", tmp_project)
        results = search_raw_sources("transformers", raw_dir=tmp_project / "raw", max_results=5)
        if results:
            r = results[0]
            assert "id" in r
            assert "content" in r
            assert "score" in r
            assert r["id"].startswith("raw/")
