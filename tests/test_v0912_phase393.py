"""Tests for Phase 3.93 backlog fixes (v0.9.12)."""

import httpx
import pytest


def _make_rate_limit_error():
    import anthropic

    resp = httpx.Response(429, request=httpx.Request("POST", "https://api.anthropic.com"))
    return anthropic.RateLimitError(message="rate limited", response=resp, body=None)


class TestLLMRetrySemantics:
    """utils/llm.py retry count and last_error safety."""

    def test_max_retries_means_retries_not_attempts(self, monkeypatch):
        """MAX_RETRIES=2 should make 3 total calls (1 initial + 2 retries)."""
        from kb.utils import llm as llm_mod

        calls = []

        def fake_create(**kwargs):
            calls.append(1)
            raise _make_rate_limit_error()

        monkeypatch.setattr(llm_mod, "MAX_RETRIES", 2)
        monkeypatch.setattr(llm_mod, "RETRY_BASE_DELAY", 0)
        client = llm_mod.get_client()
        monkeypatch.setattr(client.messages, "create", fake_create)

        with pytest.raises(llm_mod.LLMError):
            llm_mod._make_api_call({"model": "x", "max_tokens": 10, "messages": []}, "x")

        assert len(calls) == 3, f"Expected 3 total calls (1+2 retries), got {len(calls)}"

    def test_max_retries_zero_makes_one_call_and_raises_llmerror(self, monkeypatch):
        """MAX_RETRIES=0 should make exactly 1 call (range(1)) then raise LLMError."""
        from kb.utils import llm as llm_mod

        monkeypatch.setattr(llm_mod, "MAX_RETRIES", 0)
        monkeypatch.setattr(llm_mod, "RETRY_BASE_DELAY", 0)
        client = llm_mod.get_client()

        def fake_create(**kwargs):
            raise _make_rate_limit_error()

        monkeypatch.setattr(client.messages, "create", fake_create)

        with pytest.raises(llm_mod.LLMError):
            llm_mod._make_api_call({"model": "x", "max_tokens": 10, "messages": []}, "x")


class TestQueryEngine:
    """query/engine.py correctness fixes."""

    def test_search_pages_clamps_negative_max_results(self, tmp_wiki, create_wiki_page):
        """search_pages with max_results=-1 must not use negative slice."""
        from kb.query.engine import search_pages

        create_wiki_page(page_id="concepts/rag", title="RAG", wiki_dir=tmp_wiki)
        create_wiki_page(page_id="concepts/llm", title="LLM", wiki_dir=tmp_wiki)

        # With -1 clamped to 1, we get at most 1 result (not all-but-last)
        results = search_pages("rag llm", wiki_dir=tmp_wiki, max_results=-1)
        assert len(results) <= 1, f"Expected ≤1 result with max_results=-1, got {len(results)}"

    def test_build_query_context_falls_back_to_truncated_top_page(self):
        """_build_query_context must not return empty string when all pages exceed limit."""
        from kb.query.engine import _build_query_context

        big_page = {
            "id": "concepts/big",
            "title": "Big Page",
            "type": "concept",
            "confidence": "stated",
            "content": "x" * 200,
        }
        # limit is 50 chars — smaller than the page section header alone
        result = _build_query_context([big_page], max_chars=50)
        assert result != "", "Must not return empty string when top page exceeds limit"
        assert "big" in result.lower(), "Truncated fallback should contain page content"

    def test_query_wiki_accepts_and_forwards_max_results(self, monkeypatch):
        """query_wiki must accept max_results and forward it to search_pages."""
        from kb.query import engine as eng

        searched_with = []

        def fake_search(question, wiki_dir=None, max_results=10):
            searched_with.append(max_results)
            return []

        monkeypatch.setattr(eng, "search_pages", fake_search)

        eng.query_wiki("test question", max_results=5)
        assert searched_with == [5], (
            f"Expected search called with max_results=5, got {searched_with}"
        )


class TestIngestPipeline:
    """ingest/pipeline.py correctness fixes."""

    def test_summary_page_preserves_created_date_on_reingest(self, tmp_path):
        """Re-ingesting same source must not overwrite created: date on summary page."""
        from datetime import date, timedelta
        from unittest.mock import patch

        from kb.ingest.pipeline import ingest_source

        # Create a raw source structure
        raw_dir = tmp_path / "raw"
        (raw_dir / "articles").mkdir(parents=True)
        raw_path = raw_dir / "articles" / "test-article.md"
        raw_path.write_text("# Test\nContent about stuff.", encoding="utf-8")

        wiki_dir = tmp_path / "wiki"
        for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
            (wiki_dir / subdir).mkdir(parents=True)

        old_date = (date.today() - timedelta(days=10)).isoformat()
        summary_path = wiki_dir / "summaries" / "test.md"
        summary_path.write_text(
            f"---\ntitle: Test\nsource:\n  - raw/articles/test-article.md\n"
            f"created: {old_date}\nupdated: {old_date}\n"
            f"type: summary\nconfidence: stated\n---\n\n# Test\n",
            encoding="utf-8",
        )

        extraction = {"title": "Test", "entities_mentioned": [], "concepts_mentioned": []}

        with (
            patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
            patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
            patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
            patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
            patch("kb.ingest.pipeline.append_wiki_log"),
            patch("kb.ingest.pipeline._is_duplicate_content", return_value=False),
            patch("kb.compile.compiler.load_manifest", return_value={}),
            patch("kb.compile.compiler.save_manifest"),
        ):
            result = ingest_source(raw_path, source_type="article", extraction=extraction)

        import frontmatter

        post = frontmatter.load(str(summary_path))
        created_val = str(post.metadata.get("created", ""))
        assert old_date in created_val, (
            f"Re-ingest overwrote created: date. Got: {created_val!r},"
            f" expected to contain: {old_date!r}"
        )
        assert "summaries/test" in result.get("pages_updated", []), (
            "Re-ingested summary should be in pages_updated, not pages_created"
        )

    def test_ingest_source_rejects_path_outside_raw_dir(self, tmp_path):
        """ingest_source must reject paths outside the raw/ directory."""
        from unittest.mock import patch

        from kb.ingest.pipeline import ingest_source

        outside_path = tmp_path / "outside.md"
        outside_path.write_text("# Outside\nContent.", encoding="utf-8")

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        with patch("kb.ingest.pipeline.RAW_DIR", raw_dir):
            with pytest.raises(ValueError, match="raw/"):
                ingest_source(
                    outside_path,
                    source_type="article",
                    extraction={"title": "X", "entities_mentioned": [], "concepts_mentioned": []},
                )

    def test_update_sources_mapping_warns_when_file_missing(self, tmp_path, caplog):
        """_update_sources_mapping logs a warning when _sources.md doesn't exist."""
        import logging
        from unittest.mock import patch

        from kb.ingest.pipeline import _update_sources_mapping

        missing_sources = tmp_path / "_sources.md"

        with patch("kb.ingest.pipeline.WIKI_SOURCES", missing_sources):
            with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
                _update_sources_mapping("raw/articles/test.md", ["summaries/test"])

        assert any("sources" in r.message.lower() for r in caplog.records), (
            f"Expected warning about missing _sources.md."
            f" Got: {[r.message for r in caplog.records]}"
        )
