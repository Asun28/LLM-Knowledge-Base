"""Tests for v0.9.5 tier-1 audit fixes: type validation, graph encoding, MCP validation, logging."""

import logging
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helper: create a wiki page with proper frontmatter
# ---------------------------------------------------------------------------
def _create_page(path, title="Test", content="# Test\n\nContent"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'---\ntitle: "{title}"\nsource:\n  - "raw/articles/a.md"\n'
        f"created: 2026-01-01\nupdated: 2026-01-01\n"
        f"type: entity\nconfidence: stated\n---\n\n{content}\n",
        encoding="utf-8",
    )


# ===========================================================================
# Fix 1 — Extraction data type validation in ingest pipeline
# ===========================================================================
class TestExtractionTypeValidation:
    """entities_mentioned / concepts_mentioned must be lists, not strings/dicts."""

    def test_string_entities_treated_as_empty(self, tmp_project, caplog):
        """If entities_mentioned is a string, skip entities and log warning."""
        from kb.ingest.pipeline import ingest_source

        raw = tmp_project / "raw" / "articles" / "test.md"
        raw.write_text("Test article content for extraction.", encoding="utf-8")

        extraction = {
            "title": "Test Article",
            "summary": "A test summary.",
            "entities_mentioned": "not a list",  # <-- wrong type
            "concepts_mentioned": ["valid-concept"],
        }

        with (
            patch("kb.ingest.pipeline.WIKI_DIR", tmp_project / "wiki"),
            patch("kb.ingest.pipeline.RAW_DIR", tmp_project / "raw"),
            patch("kb.utils.paths.RAW_DIR", tmp_project / "raw"),
        ):
            result = ingest_source(raw, source_type="article", extraction=extraction)

        assert "entities_mentioned is not a list" in caplog.text
        entity_pages = [p for p in result["pages_created"] if p.startswith("entities/")]
        assert len(entity_pages) == 0

    def test_dict_concepts_treated_as_empty(self, tmp_project, caplog):
        """If concepts_mentioned is a dict, skip concepts and log warning."""
        from kb.ingest.pipeline import ingest_source

        raw = tmp_project / "raw" / "articles" / "test2.md"
        raw.write_text("Test article content.", encoding="utf-8")

        extraction = {
            "title": "Test Article 2",
            "summary": "A test summary.",
            "entities_mentioned": ["valid-entity"],
            "concepts_mentioned": {"wrong": "type"},  # <-- wrong type
        }

        with (
            patch("kb.ingest.pipeline.WIKI_DIR", tmp_project / "wiki"),
            patch("kb.ingest.pipeline.RAW_DIR", tmp_project / "raw"),
            patch("kb.utils.paths.RAW_DIR", tmp_project / "raw"),
        ):
            result = ingest_source(raw, source_type="article", extraction=extraction)

        assert "concepts_mentioned is not a list" in caplog.text
        concept_pages = [p for p in result["pages_created"] if p.startswith("concepts/")]
        assert len(concept_pages) == 0

    def test_valid_list_still_works(self, tmp_project):
        """Normal list values for entities/concepts still work correctly."""
        from kb.ingest.pipeline import ingest_source

        raw = tmp_project / "raw" / "articles" / "test3.md"
        raw.write_text("Valid test article.", encoding="utf-8")

        extraction = {
            "title": "Valid Article",
            "summary": "Summary.",
            "entities_mentioned": ["OpenAI"],
            "concepts_mentioned": ["RAG"],
        }

        with (
            patch("kb.ingest.pipeline.WIKI_DIR", tmp_project / "wiki"),
            patch("kb.ingest.pipeline.RAW_DIR", tmp_project / "raw"),
            patch("kb.utils.paths.RAW_DIR", tmp_project / "raw"),
        ):
            result = ingest_source(raw, source_type="article", extraction=extraction)

        entity_pages = [p for p in result["pages_created"] if p.startswith("entities/")]
        concept_pages = [p for p in result["pages_created"] if p.startswith("concepts/")]
        assert len(entity_pages) == 1
        assert len(concept_pages) == 1

    def test_int_entities_treated_as_empty(self, tmp_project, caplog):
        """If entities_mentioned is an integer, skip and log."""
        from kb.ingest.pipeline import ingest_source

        raw = tmp_project / "raw" / "articles" / "test4.md"
        raw.write_text("Content.", encoding="utf-8")

        extraction = {
            "title": "Article",
            "summary": "Summary.",
            "entities_mentioned": 42,  # <-- wrong type
            "concepts_mentioned": [],
        }

        with (
            patch("kb.ingest.pipeline.WIKI_DIR", tmp_project / "wiki"),
            patch("kb.ingest.pipeline.RAW_DIR", tmp_project / "raw"),
            patch("kb.utils.paths.RAW_DIR", tmp_project / "raw"),
        ):
            result = ingest_source(raw, source_type="article", extraction=extraction)

        assert "entities_mentioned is not a list" in caplog.text
        entity_pages = [p for p in result["pages_created"] if p.startswith("entities/")]
        assert len(entity_pages) == 0


# ===========================================================================
# Fix 2 — Graph builder handles UnicodeDecodeError
# ===========================================================================
class TestGraphBuilderEncodingError:
    """build_graph should skip files with encoding errors, not crash."""

    def test_skips_unreadable_page(self, tmp_wiki, caplog):
        """A page with invalid UTF-8 is skipped; graph still builds."""
        from kb.graph.builder import build_graph

        _create_page(tmp_wiki / "entities" / "good.md", title="Good", content="Normal content.")

        # Write a file with invalid UTF-8 bytes
        bad_path = tmp_wiki / "entities" / "bad.md"
        bad_path.parent.mkdir(parents=True, exist_ok=True)
        bad_path.write_bytes(
            b'---\ntitle: "Bad"\nsource:\n  - "raw/articles/a.md"\n'
            b"created: 2026-01-01\nupdated: 2026-01-01\n"
            b"type: entity\nconfidence: stated\n---\n\n"
            b"Content with invalid bytes: \xff\xfe\n"
        )

        with caplog.at_level(logging.WARNING):
            graph = build_graph(tmp_wiki)

        # Both nodes exist (from scan_wiki_pages) but bad page's edges skipped
        assert "entities/good" in graph.nodes()
        assert "entities/bad" in graph.nodes()
        assert "Failed to read" in caplog.text

    def test_valid_pages_still_build_edges(self, tmp_wiki):
        """Normal pages still get edges in the graph."""
        from kb.graph.builder import build_graph

        _create_page(
            tmp_wiki / "entities" / "alpha.md",
            title="Alpha",
            content="Links to [[entities/beta]].",
        )
        _create_page(
            tmp_wiki / "entities" / "beta.md",
            title="Beta",
            content="Content.",
        )

        graph = build_graph(tmp_wiki)
        assert graph.has_edge("entities/alpha", "entities/beta")


# ===========================================================================
# Fix 3 — kb_create_page rejects empty title
# ===========================================================================
class TestKbCreatePageEmptyTitle:
    """kb_create_page should reject empty or whitespace-only titles."""

    def test_empty_title_returns_error(self, tmp_wiki):
        """Empty string title returns error."""
        from kb.mcp.quality import kb_create_page

        with patch("kb.mcp.quality.WIKI_DIR", tmp_wiki):
            result = kb_create_page(
                page_id="concepts/test",
                title="",
                content="Some content.",
            )

        assert "Error" in result
        assert "Title cannot be empty" in result

    def test_whitespace_title_returns_error(self, tmp_wiki):
        """Whitespace-only title returns error."""
        from kb.mcp.quality import kb_create_page

        with patch("kb.mcp.quality.WIKI_DIR", tmp_wiki):
            result = kb_create_page(
                page_id="concepts/test",
                title="   ",
                content="Some content.",
            )

        assert "Error" in result
        assert "Title cannot be empty" in result

    def test_valid_title_succeeds(self, tmp_wiki):
        """A normal title works fine."""
        from kb.mcp.quality import kb_create_page

        with (
            patch("kb.mcp.quality.WIKI_DIR", tmp_wiki),
            patch("kb.mcp.app.WIKI_DIR", tmp_wiki),
        ):
            result = kb_create_page(
                page_id="concepts/test-page",
                title="Test Page",
                content="Some content.",
            )

        assert "Created" in result
        assert (tmp_wiki / "concepts" / "test-page.md").exists()


# ===========================================================================
# Fix 4 — MCP instructions include all 23 tools
# ===========================================================================
class TestMcpInstructionsCompleteness:
    """MCP instructions string should mention all tools."""

    def test_instructions_mention_all_key_tools(self):
        """All important tools should appear in the instructions string."""
        from kb.mcp.app import mcp

        instructions = mcp.instructions or ""

        for tool_name in [
            "kb_query",
            "kb_ingest",
            "kb_ingest_content",
            "kb_save_source",
            "kb_compile_scan",
            "kb_compile",
            "kb_search",
            "kb_read_page",
            "kb_list_pages",
            "kb_list_sources",
            "kb_lint",
            "kb_evolve",
            "kb_stats",
            "kb_detect_drift",
            "kb_review_page",
            "kb_refine_page",
            "kb_lint_deep",
            "kb_lint_consistency",
            "kb_query_feedback",
            "kb_reliability_map",
            "kb_affected_pages",
            "kb_save_lint_verdict",
            "kb_create_page",
        ]:
            assert tool_name in instructions, f"{tool_name} missing from MCP instructions"


# ===========================================================================
# Fix 5 — Evolve stub check logs on failure instead of silent pass
# ===========================================================================
class TestEvolveStubCheckLogging:
    """Evolve should log debug when stub check fails, not silently pass."""

    def test_stub_failure_logs_debug(self, tmp_wiki, caplog):
        """If check_stub_pages raises, a debug message is emitted."""
        from kb.evolve.analyzer import generate_evolution_report

        with (
            patch(
                "kb.lint.checks.check_stub_pages",
                side_effect=RuntimeError("test error"),
            ),
            caplog.at_level(logging.DEBUG),
        ):
            report = generate_evolution_report(tmp_wiki)

        assert "Stub check failed" in caplog.text
        assert "recommendations" in report


# ===========================================================================
# Fix 6 — fix_dead_links logs to wiki/log.md
# ===========================================================================
class TestFixDeadLinksAuditLog:
    """fix_dead_links should write to wiki/log.md when links are fixed."""

    def test_logs_fixes_to_wiki_log(self, tmp_wiki):
        """After fixing dead links, an entry should appear in wiki/log.md."""
        from kb.lint.checks import fix_dead_links

        _create_page(
            tmp_wiki / "entities" / "page-a.md",
            title="Page A",
            content="See [[concepts/nonexistent]] for details.",
        )

        wiki_log = tmp_wiki / "log.md"
        wiki_log.write_text("# Wiki Log\n\n", encoding="utf-8")

        with patch("kb.config.WIKI_LOG", wiki_log), patch("kb.utils.wiki_log.WIKI_LOG", wiki_log):
            fixes = fix_dead_links(tmp_wiki)

        assert len(fixes) > 0
        log_content = wiki_log.read_text(encoding="utf-8")
        assert "lint-fix" in log_content
        assert "broken wikilink" in log_content

    def test_no_log_when_no_fixes(self, tmp_wiki):
        """When there are no broken links, no log entry is written."""
        from kb.lint.checks import fix_dead_links

        _create_page(
            tmp_wiki / "entities" / "page-a.md",
            title="Page A",
            content="See [[entities/page-b]] for details.",
        )
        _create_page(
            tmp_wiki / "entities" / "page-b.md",
            title="Page B",
            content="Content.",
        )

        wiki_log = tmp_wiki / "log.md"
        wiki_log.write_text("# Wiki Log\n\n", encoding="utf-8")

        with patch("kb.config.WIKI_LOG", wiki_log), patch("kb.utils.wiki_log.WIKI_LOG", wiki_log):
            fixes = fix_dead_links(tmp_wiki)

        assert len(fixes) == 0
        log_content = wiki_log.read_text(encoding="utf-8")
        assert "lint-fix" not in log_content
