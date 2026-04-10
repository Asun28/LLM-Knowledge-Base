"""Tests for v0.9.6 tier-2 audit fixes: context truncation, atomic writes,
empty query, entity limits, citation traversal, feedback loop."""

import json
import logging
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helper
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
# T2-1 — Query context skips whole pages instead of truncating mid-page
# ===========================================================================
class TestQueryContextWholePageSkip:
    """_build_query_context should never produce partial markdown sections."""

    def test_skips_oversized_page_entirely(self):
        """A page that doesn't fit is excluded entirely, no [..truncated]."""
        from kb.query.engine import _build_query_context

        pages = [
            {
                "id": "concepts/small",
                "type": "concept",
                "confidence": "stated",
                "title": "Small",
                "content": "Brief content.",
            },
            {
                "id": "concepts/huge",
                "type": "concept",
                "confidence": "stated",
                "title": "Huge",
                "content": "x" * 10000,
            },
        ]

        result = _build_query_context(pages, max_chars=500)
        context = result["context"]

        assert "concepts/small" in context
        assert "[...truncated]" not in context
        # Huge page should not appear at all
        assert "x" * 100 not in context

    def test_top_page_truncated_when_oversized(self):
        """Top-ranked page (i==0) is truncated to budget rather than skipped entirely.

        Updated in Phase 3.96 Task 4 (Fix 4.5): the old behavior skipped the top
        page entirely so smaller subsequent pages could fit. The new behavior truncates
        the top page to consume the available budget, ensuring the LLM always has
        content to work with rather than hallucinating on an empty context.
        """
        from kb.query.engine import _build_query_context

        pages = [
            {
                "id": "concepts/huge",
                "type": "concept",
                "confidence": "stated",
                "title": "Huge",
                "content": "x" * 10000,
            },
            {
                "id": "concepts/tiny",
                "type": "concept",
                "confidence": "stated",
                "title": "Tiny",
                "content": "Small page.",
            },
        ]

        result = _build_query_context(pages, max_chars=500)
        context = result["context"]

        # Huge is truncated (not skipped) — it should be included
        assert "concepts/huge" in result["context_pages"]
        # After truncation the budget is consumed; tiny won't fit
        assert len(context) <= 500

    def test_logs_skip_count(self, caplog):
        """When pages are skipped, an info log reports the count."""
        from kb.query.engine import _build_query_context

        pages = [
            {
                "id": f"concepts/page-{i}",
                "type": "concept",
                "confidence": "stated",
                "title": f"Page {i}",
                "content": "y" * 5000,
            }
            for i in range(3)
        ]

        with caplog.at_level(logging.INFO, logger="kb.query.engine"):
            _build_query_context(pages, max_chars=100)

        assert any("skipped" in r.message for r in caplog.records)


# ===========================================================================
# T2-2 — Atomic writes for feedback and verdict stores
# ===========================================================================
class TestAtomicWrites:
    """save_feedback and save_verdicts should use atomic write."""

    def test_feedback_atomic_write(self, tmp_path):
        """save_feedback writes via temp file (no partial writes)."""
        from kb.feedback.store import save_feedback

        path = tmp_path / "feedback.json"
        data = {"entries": [{"test": True}], "page_scores": {}}

        save_feedback(data, path=path)

        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded == data

    def test_feedback_no_temp_file_on_success(self, tmp_path):
        """After successful write, no .tmp files should remain."""
        from kb.feedback.store import save_feedback

        path = tmp_path / "feedback.json"
        save_feedback({"entries": [], "page_scores": {}}, path=path)

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_verdict_atomic_write(self, tmp_path):
        """save_verdicts writes via temp file."""
        from kb.lint.verdicts import save_verdicts

        path = tmp_path / "verdicts.json"
        data = [{"page_id": "test", "verdict": "pass"}]

        save_verdicts(data, path=path)

        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded == data

    def test_verdict_no_temp_file_on_success(self, tmp_path):
        """After successful write, no .tmp files remain."""
        from kb.lint.verdicts import save_verdicts

        path = tmp_path / "verdicts.json"
        save_verdicts([], path=path)

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0


# ===========================================================================
# T2-4 — Bare except in kb_refine_page logs debug
# ===========================================================================
class TestRefinePageBacklinksLogging:
    """kb_refine_page should log when backlinks computation fails."""

    def test_logs_debug_on_backlinks_failure(self, tmp_wiki, caplog):
        """When build_backlinks fails, debug log emitted."""
        from kb.mcp.quality import kb_refine_page

        _create_page(tmp_wiki / "entities" / "test.md", title="Test", content="Content.")

        with (
            patch("kb.mcp.quality.WIKI_DIR", tmp_wiki),
            patch("kb.mcp.app.WIKI_DIR", tmp_wiki),
            patch("kb.review.refiner.WIKI_DIR", tmp_wiki),
            patch(
                "kb.compile.linker.build_backlinks",
                side_effect=RuntimeError("test"),
            ),
            caplog.at_level(logging.DEBUG),
        ):
            result = kb_refine_page("entities/test", "Updated content.", "Test notes")

        assert "Refined" in result
        assert "Failed to compute backlinks" in caplog.text


# ===========================================================================
# T2-5 — kb_search rejects empty queries
# ===========================================================================
class TestKbSearchEmptyQuery:
    """kb_search should return error for empty/whitespace queries."""

    def test_empty_string(self):
        """Empty string query returns error."""
        from kb.mcp.browse import kb_search

        result = kb_search(query="")
        assert "Error" in result
        assert "empty" in result.lower()

    def test_whitespace_only(self):
        """Whitespace-only query returns error."""
        from kb.mcp.browse import kb_search

        result = kb_search(query="   ")
        assert "Error" in result


# ===========================================================================
# T2-6 — Entity/concept count limit per ingest
# ===========================================================================
class TestIngestEntityLimit:
    """Ingest should truncate entities/concepts beyond the configured limit."""

    def test_entities_truncated_at_limit(self, tmp_project, caplog):
        """More than MAX_ENTITIES_PER_INGEST entities are truncated."""
        from kb.ingest.pipeline import ingest_source

        raw = tmp_project / "raw" / "articles" / "test.md"
        raw.write_text("Content.", encoding="utf-8")

        entities = [f"Entity-{i}" for i in range(60)]
        extraction = {
            "title": "Big Article",
            "summary": "Summary.",
            "entities_mentioned": entities,
            "concepts_mentioned": [],
        }

        with (
            patch("kb.ingest.pipeline.WIKI_DIR", tmp_project / "wiki"),
            patch("kb.ingest.pipeline.RAW_DIR", tmp_project / "raw"),
            patch("kb.utils.paths.RAW_DIR", tmp_project / "raw"),
        ):
            result = ingest_source(raw, source_type="article", extraction=extraction)

        # Should have been truncated to 50
        entity_pages = [p for p in result["pages_created"] if p.startswith("entities/")]
        assert len(entity_pages) == 50
        assert "truncating to 50" in caplog.text

    def test_concepts_truncated_at_limit(self, tmp_project, caplog):
        """More than MAX_CONCEPTS_PER_INGEST concepts are truncated."""
        from kb.ingest.pipeline import ingest_source

        raw = tmp_project / "raw" / "articles" / "test2.md"
        raw.write_text("Content.", encoding="utf-8")

        concepts = [f"Concept-{i}" for i in range(60)]
        extraction = {
            "title": "Big Article 2",
            "summary": "Summary.",
            "entities_mentioned": [],
            "concepts_mentioned": concepts,
        }

        with (
            patch("kb.ingest.pipeline.WIKI_DIR", tmp_project / "wiki"),
            patch("kb.ingest.pipeline.RAW_DIR", tmp_project / "raw"),
            patch("kb.utils.paths.RAW_DIR", tmp_project / "raw"),
        ):
            result = ingest_source(raw, source_type="article", extraction=extraction)

        concept_pages = [p for p in result["pages_created"] if p.startswith("concepts/")]
        assert len(concept_pages) == 50
        assert "truncating to 50" in caplog.text

    def test_within_limit_not_truncated(self, tmp_project, caplog):
        """Lists within the limit are not truncated."""
        from kb.ingest.pipeline import ingest_source

        raw = tmp_project / "raw" / "articles" / "test3.md"
        raw.write_text("Content.", encoding="utf-8")

        extraction = {
            "title": "Normal Article",
            "summary": "Summary.",
            "entities_mentioned": ["E1", "E2", "E3"],
            "concepts_mentioned": ["C1", "C2"],
        }

        with (
            patch("kb.ingest.pipeline.WIKI_DIR", tmp_project / "wiki"),
            patch("kb.ingest.pipeline.RAW_DIR", tmp_project / "raw"),
            patch("kb.utils.paths.RAW_DIR", tmp_project / "raw"),
        ):
            result = ingest_source(raw, source_type="article", extraction=extraction)

        entity_pages = [p for p in result["pages_created"] if p.startswith("entities/")]
        concept_pages = [p for p in result["pages_created"] if p.startswith("concepts/")]
        assert len(entity_pages) == 3
        assert len(concept_pages) == 2
        assert "truncating" not in caplog.text


# ===========================================================================
# T2-7 — Citation path traversal validation
# ===========================================================================
class TestCitationPathTraversal:
    """extract_citations should reject paths with traversal patterns."""

    def test_rejects_dotdot_in_path(self):
        """Citations with '..' are filtered out."""
        from kb.query.citations import extract_citations

        text = "Answer from [source: ../../../etc/passwd] and [source: concepts/rag]"
        citations = extract_citations(text)

        paths = [c["path"] for c in citations]
        assert "concepts/rag" in paths
        assert "../../../etc/passwd" not in paths

    def test_rejects_leading_slash(self):
        """Citations with leading '/' are filtered out."""
        from kb.query.citations import extract_citations

        text = "See [source: /etc/passwd] and [ref: raw/articles/good.md]"
        citations = extract_citations(text)

        paths = [c["path"] for c in citations]
        assert "raw/articles/good.md" in paths
        assert "/etc/passwd" not in paths

    def test_valid_citations_still_work(self):
        """Normal citations are extracted correctly."""
        from kb.query.citations import extract_citations

        text = (
            "Based on [source: concepts/rag] and [ref: raw/articles/test.md], "
            "also see [source: entities/openai]."
        )
        citations = extract_citations(text)

        assert len(citations) == 3
        assert citations[0]["path"] == "concepts/rag"
        assert citations[1]["path"] == "raw/articles/test.md"
        assert citations[2]["path"] == "entities/openai"


# ===========================================================================
# T2-8 — Evolve surfaces low-trust pages from feedback
# ===========================================================================
class TestEvolveFeedbackLoop:
    """generate_evolution_report should surface low-trust pages."""

    def test_flagged_pages_in_recommendations(self, tmp_wiki):
        """Low-trust pages appear in evolve recommendations."""
        from kb.evolve.analyzer import generate_evolution_report

        with patch(
            "kb.feedback.reliability.get_flagged_pages",
            return_value=["concepts/bad-page", "entities/wrong-entity"],
        ):
            report = generate_evolution_report(tmp_wiki)

        assert "flagged_pages" in report
        assert len(report["flagged_pages"]) == 2
        recs = "\n".join(report["recommendations"])
        assert "low-trust" in recs
        assert "concepts/bad-page" in recs

    def test_no_flagged_pages_when_no_feedback(self, tmp_wiki):
        """When no feedback exists, no flagged pages recommendation."""
        from kb.evolve.analyzer import generate_evolution_report

        report = generate_evolution_report(tmp_wiki)

        assert report["flagged_pages"] == []
        recs = "\n".join(report["recommendations"])
        assert "low-trust" not in recs
