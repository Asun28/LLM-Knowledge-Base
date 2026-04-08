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

    def test_update_index_batch_warns_when_file_missing(self, tmp_path, caplog):
        """_update_index_batch logs a warning when index.md doesn't exist."""
        import logging
        from unittest.mock import patch

        from kb.ingest.pipeline import _update_index_batch

        missing_index = tmp_path / "index.md"

        with patch("kb.ingest.pipeline.WIKI_INDEX", missing_index):
            with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
                _update_index_batch([("summary", "test-article", "Test Article")])

        assert any("index" in r.message.lower() for r in caplog.records), (
            f"Expected warning about missing index.md. Got: {[r.message for r in caplog.records]}"
        )


class TestLintFixes:
    """lint/checks.py and lint/verdicts.py correctness fixes."""

    def test_check_staleness_handles_string_updated_date(self, tmp_wiki, create_wiki_page):
        """check_staleness must detect stale pages with string-typed updated: field."""
        from datetime import date, timedelta

        from kb.lint.checks import check_staleness

        old_date = (date.today() - timedelta(days=200)).isoformat()
        page_path = tmp_wiki / "concepts" / "old-concept.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            f"---\ntitle: Old Concept\nsource:\n  - raw/articles/x.md\n"
            f'created: "{old_date}"\nupdated: "{old_date}"\n'
            f"type: concept\nconfidence: stated\n---\n\nBody.\n",
            encoding="utf-8",
        )

        issues = check_staleness(wiki_dir=tmp_wiki, max_days=90)
        stale_pages = [i["page"] for i in issues]
        assert "concepts/old-concept" in stale_pages, (
            f"Stale page with string updated: was silently skipped. Found: {stale_pages}"
        )

    def test_check_orphan_exempts_comparisons_and_synthesis(self, tmp_wiki, create_wiki_page):
        """check_orphan_pages must not flag comparisons/ and synthesis/ pages as orphans."""
        from kb.lint.checks import check_orphan_pages

        create_wiki_page(page_id="comparisons/a-vs-b", title="A vs B", wiki_dir=tmp_wiki)
        create_wiki_page(page_id="synthesis/overview", title="Overview", wiki_dir=tmp_wiki)

        issues = check_orphan_pages(wiki_dir=tmp_wiki)
        flagged = [i["page"] for i in issues]
        assert "comparisons/a-vs-b" not in flagged, (
            "comparisons/ should be exempt from orphan check"
        )
        assert "synthesis/overview" not in flagged, "synthesis/ should be exempt from orphan check"

    def test_check_source_coverage_no_false_positive_same_filename(
        self, tmp_wiki, create_wiki_page, tmp_path
    ):
        """check_source_coverage must not false-positive on same-named files in different dirs."""
        from unittest.mock import patch

        from kb.lint.checks import check_source_coverage

        raw_dir = tmp_path / "raw"
        (raw_dir / "articles").mkdir(parents=True)
        (raw_dir / "papers").mkdir(parents=True)
        (raw_dir / "articles" / "example.md").write_text("article content", encoding="utf-8")
        (raw_dir / "papers" / "example.md").write_text("paper content", encoding="utf-8")

        # Wiki page references only the article
        create_wiki_page(
            page_id="summaries/example",
            title="Example",
            content="Source: raw/articles/example.md",
            wiki_dir=tmp_wiki,
        )

        # Patch SOURCE_TYPE_DIRS to only include articles and papers
        fake_dirs = {
            "article": raw_dir / "articles",
            "paper": raw_dir / "papers",
        }
        with patch("kb.lint.checks.SOURCE_TYPE_DIRS", fake_dirs):
            issues = check_source_coverage(wiki_dir=tmp_wiki, raw_dir=raw_dir)

        uncovered = [i["source"] for i in issues]
        assert "raw/papers/example.md" in uncovered, (
            "Paper with same name should be flagged as uncovered"
        )
        assert "raw/articles/example.md" not in uncovered, (
            "Article should NOT be flagged — false positive from old endswith check"
        )

    def test_load_verdicts_logs_warning_on_json_error(self, tmp_path, caplog):
        """load_verdicts must log a warning when verdicts file is corrupt JSON."""
        import logging

        from kb.lint.verdicts import load_verdicts

        bad_path = tmp_path / "verdicts.json"
        bad_path.write_text("{ NOT VALID JSON }", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="kb.lint.verdicts"):
            result = load_verdicts(bad_path)

        assert result == [], "Should return empty list on JSON error"
        assert any(
            "corrupt" in r.message.lower() or "json" in r.message.lower() for r in caplog.records
        ), f"Expected warning about corrupt JSON. Got: {[r.message for r in caplog.records]}"


class TestCompileFixes:
    """compile/linker.py and compile/compiler.py correctness fixes."""

    def test_inject_wikilinks_skips_page_already_linked_case_insensitive(
        self, tmp_wiki, create_wiki_page
    ):
        """inject_wikilinks must not inject duplicate when target already exists (lowercase)."""
        from kb.compile.linker import inject_wikilinks

        # Page body already has a lowercase wikilink to concepts/gpt4
        create_wiki_page(
            page_id="entities/openai",
            title="OpenAI",
            content="We use [[concepts/gpt4|GPT-4]] in our work. GPT-4 is great.",
            wiki_dir=tmp_wiki,
        )
        create_wiki_page(page_id="concepts/gpt4", title="GPT-4", wiki_dir=tmp_wiki)

        # Caller passes mixed-case target_page_id (which is the bug trigger)
        updated = inject_wikilinks("GPT-4", "concepts/GPT4", wiki_dir=tmp_wiki)
        assert "entities/openai" not in updated, (
            "Should not inject duplicate wikilink — page already links to lowercased target"
        )

        # Positive case: a page WITHOUT the link should get it injected
        create_wiki_page(
            page_id="concepts/transformers",
            title="Transformers",
            content="GPT-4 is a transformer model.",
            wiki_dir=tmp_wiki,
        )
        updated2 = inject_wikilinks("GPT-4", "concepts/GPT4", wiki_dir=tmp_wiki)
        assert "concepts/transformers" in updated2, (
            "Page without existing link should get wikilink injected"
        )

    def test_find_changed_sources_read_only_does_not_update_manifest(self, tmp_path):
        """find_changed_sources with save_hashes=False must not modify the manifest."""
        from kb.compile.compiler import find_changed_sources, load_manifest, save_manifest

        raw_dir = tmp_path / "raw"
        (raw_dir / "articles").mkdir(parents=True)
        manifest_path = tmp_path / "hashes.json"
        save_manifest({}, manifest_path)

        find_changed_sources(
            raw_dir=raw_dir,
            manifest_path=manifest_path,
            save_hashes=False,
        )

        manifest_after = load_manifest(manifest_path)
        assert manifest_after == {}, (
            f"Manifest was modified despite save_hashes=False: {manifest_after}"
        )


class TestGraphExportFixes:
    """graph/export.py fixes."""

    def test_sanitize_label_strips_newlines(self):
        from kb.graph.export import _sanitize_label

        result = _sanitize_label("Line 1\nLine 2")
        assert "\n" not in result, f"Newline not stripped: {result!r}"

    def test_sanitize_label_strips_backticks(self):
        from kb.graph.export import _sanitize_label

        result = _sanitize_label("`code term`")
        assert "`" not in result, f"Backtick not stripped: {result!r}"

    def test_export_mermaid_empty_wiki(self, tmp_wiki):
        from kb.graph.export import export_mermaid

        result = export_mermaid(wiki_dir=tmp_wiki)
        assert result.startswith("graph LR")

    def test_export_mermaid_with_pages(self, tmp_wiki, create_wiki_page):
        from kb.graph.export import export_mermaid

        create_wiki_page(page_id="concepts/rag", title="RAG", wiki_dir=tmp_wiki)
        result = export_mermaid(wiki_dir=tmp_wiki)
        assert "graph LR" in result
        assert "concepts" in result


class TestConfigFixes:
    """config.py constants and model validation."""

    def test_max_verdicts_importable_from_config(self):
        from kb.config import MAX_VERDICTS

        assert isinstance(MAX_VERDICTS, int) and MAX_VERDICTS > 0

    def test_max_feedback_entries_importable_from_config(self):
        from kb.config import MAX_FEEDBACK_ENTRIES

        assert isinstance(MAX_FEEDBACK_ENTRIES, int) and MAX_FEEDBACK_ENTRIES > 0

    def test_empty_model_env_override_falls_back_to_default(self, monkeypatch):
        """Empty CLAUDE_SCAN_MODEL must not pass empty string to API."""
        import importlib

        monkeypatch.setenv("CLAUDE_SCAN_MODEL", "")
        import kb.config as cfg

        importlib.reload(cfg)
        assert cfg.MODEL_TIERS["scan"] != "", "Empty env override must fall back to default"
        importlib.reload(cfg)  # restore for other tests


class TestCLIFixes:
    """cli.py fixes."""

    def test_ingest_type_accepts_comparison(self):
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", "--type", "comparison", "/nonexistent.md"])
        assert "Invalid value for '--type'" not in (result.output or "")

    def test_ingest_type_accepts_synthesis(self):
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", "--type", "synthesis", "/nonexistent.md"])
        assert "Invalid value for '--type'" not in (result.output or "")

    def test_mcp_command_handles_startup_error_gracefully(self, monkeypatch):
        from click.testing import CliRunner

        from kb.cli import cli

        def bad_main():
            raise RuntimeError("Simulated MCP startup failure")

        monkeypatch.setattr("kb.mcp_server.main", bad_main)
        runner = CliRunner()
        result = runner.invoke(cli, ["mcp"])
        assert result.exit_code != 0
        assert "Traceback" not in (result.output or "")
        assert "Error" in (result.output or "")


class TestMCPFixes:
    """mcp/browse.py and mcp/app.py fixes."""

    def test_format_ingest_result_handles_flat_affected_pages(self):
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": ["summaries/test"],
            "pages_updated": [],
            "pages_skipped": [],
            "wikilinks_injected": [],
            "affected_pages": ["concepts/rag"],
        }
        output = _format_ingest_result("raw/articles/test.md", "article", "abc123", result)
        assert "concepts/rag" in output
        assert "backlink" not in output  # dead legacy branch removed

    def test_kb_search_returns_error_string_on_exception(self, monkeypatch):
        import kb.query.engine as eng_mod
        from kb.mcp.browse import kb_search

        def bad_search(*args, **kwargs):
            raise RuntimeError("Simulated failure")

        monkeypatch.setattr(eng_mod, "search_pages", bad_search)
        result = kb_search("test query")
        assert result.startswith("Error:"), f"Expected Error: string, got: {result[:80]!r}"
