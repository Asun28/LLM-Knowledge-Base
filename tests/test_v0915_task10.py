"""
Phase 3.96 Task 10 — CLI fixes.

Tests for:
- Fix 10.1: Duplicate content indicator in CLI ingest output
- Fix 10.2: Remove comparison/synthesis from CLI ingest --type choices
- Fix 10.3: Lint error-count exit handling (verify current behavior)
"""

from click.testing import CliRunner

from kb.cli import ingest, lint


class TestCliDuplicateIndicator:
    """Fix 10.1: CLI ingest must show duplicate detection."""

    def test_duplicate_shown_in_output(self, tmp_path, monkeypatch):
        """When ingest_source returns duplicate=True, CLI must display it."""

        def mock_ingest_source(*args, **kwargs):
            return {
                "source_path": str(tmp_path / "test.md"),
                "source_type": "article",
                "content_hash": "abc123def456",
                "pages_created": [],
                "pages_updated": [],
                "pages_skipped": [],
                "duplicate": True,
            }

        monkeypatch.setattr("kb.ingest.pipeline.ingest_source", mock_ingest_source)

        src = tmp_path / "test.md"
        src.write_text("test content", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(ingest, [str(src)])

        # Should exit successfully (0) on duplicate
        assert result.exit_code == 0
        # Output must contain "Duplicate" (case-insensitive)
        assert "uplicate" in result.output or "Duplicate" in result.output

    def test_normal_ingest_without_duplicate_flag(self, tmp_path, monkeypatch):
        """Normal ingest (no duplicate) should not show duplicate message."""

        def mock_ingest_source(*args, **kwargs):
            return {
                "source_path": str(tmp_path / "test.md"),
                "source_type": "article",
                "content_hash": "xyz789",
                "pages_created": ["entities/my-entity"],
                "pages_updated": [],
                "pages_skipped": [],
                "duplicate": False,
            }

        monkeypatch.setattr("kb.ingest.pipeline.ingest_source", mock_ingest_source)

        src = tmp_path / "test.md"
        src.write_text("new content", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(ingest, [str(src)])

        assert result.exit_code == 0
        assert "Pages created: 1" in result.output
        # Should NOT show duplicate message
        assert "Duplicate" not in result.output


class TestCliSourceTypesChoice:
    """Fix 10.2: comparison/synthesis must be removed from --type choices."""

    def test_comparison_not_in_choices(self, tmp_path):
        """Verify --type choice does not include 'comparison'."""
        runner = CliRunner()
        src = tmp_path / "test.md"
        src.write_text("content", encoding="utf-8")

        # Try to use --type comparison; should fail with "Invalid value for '--type'"
        result = runner.invoke(ingest, [str(src), "--type", "comparison"])

        assert result.exit_code != 0
        assert "Invalid value for '--type'" in result.output

    def test_synthesis_not_in_choices(self, tmp_path):
        """Verify --type choice does not include 'synthesis'."""
        runner = CliRunner()
        src = tmp_path / "test.md"
        src.write_text("content", encoding="utf-8")

        # Try to use --type synthesis; should fail
        result = runner.invoke(ingest, [str(src), "--type", "synthesis"])

        assert result.exit_code != 0
        assert "Invalid value for '--type'" in result.output

    def test_valid_types_accepted(self, tmp_path, monkeypatch):
        """Valid types (article, paper, etc.) should still be accepted."""

        def mock_ingest_source(*args, **kwargs):
            return {
                "source_path": str(tmp_path / "test.md"),
                "source_type": "article",
                "content_hash": "hash1",
                "pages_created": [],
                "pages_updated": [],
                "pages_skipped": [],
            }

        monkeypatch.setattr("kb.ingest.pipeline.ingest_source", mock_ingest_source)

        src = tmp_path / "test.md"
        src.write_text("content", encoding="utf-8")

        runner = CliRunner()
        # Should accept valid types
        for valid_type in [
            "article",
            "paper",
            "repo",
            "video",
            "podcast",
            "book",
            "dataset",
            "conversation",
        ]:
            result = runner.invoke(ingest, [str(src), "--type", valid_type])
            assert result.exit_code == 0, f"Failed for type {valid_type}"


class TestCliLintExitHandling:
    """Fix 10.3: Verify lint exit handling for error-count checks."""

    def test_lint_exits_1_when_errors_present(self, monkeypatch):
        """Lint should exit with code 1 when report has errors."""

        def mock_run_all_checks(*args, **kwargs):
            return {
                "summary": {
                    "error": 3,  # Has errors
                    "warning": 1,
                },
                "fixes_applied": [],
            }

        def mock_format_report(report):
            return "Found 3 errors, 1 warning"

        monkeypatch.setattr("kb.lint.runner.run_all_checks", mock_run_all_checks)
        monkeypatch.setattr("kb.lint.runner.format_report", mock_format_report)

        runner = CliRunner()
        result = runner.invoke(lint, [])

        assert result.exit_code == 1

    def test_lint_exits_0_when_no_errors(self, monkeypatch):
        """Lint should exit with code 0 when no errors."""

        def mock_run_all_checks(*args, **kwargs):
            return {
                "summary": {
                    "error": 0,
                    "warning": 2,
                },
                "fixes_applied": [],
            }

        def mock_format_report(report):
            return "Found 0 errors, 2 warnings"

        monkeypatch.setattr("kb.lint.runner.run_all_checks", mock_run_all_checks)
        monkeypatch.setattr("kb.lint.runner.format_report", mock_format_report)

        runner = CliRunner()
        result = runner.invoke(lint, [])

        assert result.exit_code == 0

    def test_lint_handles_exception_exit_1(self, monkeypatch):
        """Lint should exit with code 1 on exception."""

        def mock_run_all_checks(*args, **kwargs):
            raise ValueError("Lint failed")

        monkeypatch.setattr("kb.lint.runner.run_all_checks", mock_run_all_checks)

        runner = CliRunner()
        result = runner.invoke(lint, [])

        assert result.exit_code == 1
        assert "Error:" in result.output
