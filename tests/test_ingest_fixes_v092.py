"""Tests for v0.9.2 ingest fixes — regex, exception handling, pages_skipped surfacing."""

import logging
from pathlib import Path

from kb.ingest.pipeline import _update_existing_page
from kb.mcp.app import _format_ingest_result

# ---------------------------------------------------------------------------
# Fix 1 & 2: _update_existing_page — regex and exception handling
# ---------------------------------------------------------------------------


class TestUpdateExistingPageAppendsAfterLastSource:
    """Fix 1: New source is inserted after the last source line, not in the middle."""

    def test_appends_after_last_source(self, tmp_path: Path):
        page = tmp_path / "entity.md"
        page.write_text(
            '---\ntitle: "Test"\nsource:\n'
            '  - "raw/articles/first.md"\n'
            '  - "raw/articles/second.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\n"
            "type: entity\nconfidence: stated\n---\n\n"
            "# Test\n\n## References\n\n- Mentioned in raw/articles/first.md\n",
            encoding="utf-8",
        )

        _update_existing_page(page, "raw/articles/third.md")

        content = page.read_text(encoding="utf-8")
        # The new source should appear after the second source, not between first and second
        lines = content.splitlines()
        source_lines = [line for line in lines if line.strip().startswith('- "raw/')]
        assert len(source_lines) == 3
        assert source_lines[0] == '  - "raw/articles/first.md"'
        assert source_lines[1] == '  - "raw/articles/second.md"'
        assert source_lines[2] == '  - "raw/articles/third.md"'

    def test_appends_with_three_existing_sources(self, tmp_path: Path):
        """Ensure the fix works with 3+ existing sources (the old regex was flaky here)."""
        page = tmp_path / "entity.md"
        page.write_text(
            '---\ntitle: "Test"\nsource:\n'
            '  - "raw/articles/a.md"\n'
            '  - "raw/articles/b.md"\n'
            '  - "raw/articles/c.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\n"
            "type: entity\nconfidence: stated\n---\n\n# Test\n",
            encoding="utf-8",
        )

        _update_existing_page(page, "raw/articles/d.md")

        content = page.read_text(encoding="utf-8")
        lines = content.splitlines()
        source_lines = [line for line in lines if line.strip().startswith('- "raw/')]
        assert len(source_lines) == 4
        assert source_lines[-1] == '  - "raw/articles/d.md"'


class TestUpdateExistingPageSkipsExistingSource:
    """Fix 2: Returns early when source is already in frontmatter."""

    def test_skips_existing_source(self, tmp_path: Path):
        page = tmp_path / "entity.md"
        original = (
            '---\ntitle: "Test"\nsource:\n'
            '  - "raw/articles/first.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\n"
            "type: entity\nconfidence: stated\n---\n\n# Test\n"
        )
        page.write_text(original, encoding="utf-8")

        _update_existing_page(page, "raw/articles/first.md")

        # Content should be unchanged — no duplicate source, no updated date
        assert page.read_text(encoding="utf-8") == original


class TestUpdateExistingPageCorruptedFrontmatter:
    """Fix 2: Handles corrupted frontmatter without crashing."""

    def test_handles_corrupted_frontmatter(self, tmp_path: Path, caplog):
        page = tmp_path / "entity.md"
        # Invalid YAML: unmatched quote and bad indentation
        page.write_text(
            '---\ntitle: "Broken\nsource:\n'
            '  - "raw/articles/first.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\n"
            "type: entity\nconfidence: stated\n---\n\n# Test\n",
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
            _update_existing_page(page, "raw/articles/new.md")

        content = page.read_text(encoding="utf-8")
        # Q_C fix: on frontmatter parse error, the function returns early to prevent
        # duplicate source injection. The file should be unchanged (no new source added).
        assert '"raw/articles/new.md"' not in content
        # Should have logged a warning about the parse failure
        assert any("Failed to parse frontmatter" in r.message for r in caplog.records)

    def test_handles_completely_invalid_yaml(self, tmp_path: Path, caplog):
        """Page with no valid YAML at all — should not crash."""
        page = tmp_path / "entity.md"
        page.write_text(
            "This is not YAML at all\nJust plain text\nsource:\n",
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
            # Should not raise
            _update_existing_page(page, "raw/articles/new.md")


# ---------------------------------------------------------------------------
# Fix 3: _format_ingest_result — pages_skipped surfacing
# ---------------------------------------------------------------------------


class TestFormatIngestResultSkipped:
    """Fix 3: _format_ingest_result includes pages_skipped when present."""

    def test_includes_skipped_pages(self):
        result = {
            "pages_created": ["summaries/test"],
            "pages_updated": ["entities/foo"],
            "pages_skipped": [
                "entities/bar (collision: 'Bar')",
                "concepts/baz (collision: 'Baz')",
            ],
        }
        output = _format_ingest_result("raw/articles/test.md", "article", "abc123", result)

        assert "Pages skipped (2):" in output
        assert "  ! entities/bar (collision: 'Bar')" in output
        assert "  ! concepts/baz (collision: 'Baz')" in output

    def test_no_skipped_section_when_empty(self):
        result = {
            "pages_created": ["summaries/test"],
            "pages_updated": [],
            "pages_skipped": [],
        }
        output = _format_ingest_result("raw/articles/test.md", "article", "abc123", result)

        assert "skipped" not in output.lower()

    def test_no_skipped_section_when_missing_key(self):
        result = {
            "pages_created": ["summaries/test"],
            "pages_updated": [],
        }
        output = _format_ingest_result("raw/articles/test.md", "article", "abc123", result)

        assert "skipped" not in output.lower()
