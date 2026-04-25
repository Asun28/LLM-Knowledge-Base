"""Phase 3.97 Task 09 — CLI fixes + version bump."""

from unittest.mock import patch

from click.testing import CliRunner


class TestCompileExitCode:
    """kb compile must exit 1 when errors occur."""

    def test_compile_errors_exit_code_1(self):
        from kb.cli import cli

        runner = CliRunner()
        mock_result = {
            "mode": "incremental",
            "sources_processed": 1,
            "pages_created": [],
            "pages_updated": [],
            "pages_skipped": [],
            "wikilinks_injected": [],
            "affected_pages": [],
            "duplicates": 0,
            "errors": [{"source": "raw/articles/bad.md", "error": "parse failed"}],
        }
        with patch("kb.compile.compiler.compile_wiki", return_value=mock_result):
            result = runner.invoke(cli, ["compile"])
            assert result.exit_code == 1


class TestCliSourceTypeList:
    """CLI ingest --type choices must match SOURCE_TYPE_DIRS."""

    def test_all_source_types_available(self):
        from kb.cli import cli

        # Get the ingest command's --type parameter choices
        ingest_cmd = cli.commands["ingest"]
        type_param = next(p for p in ingest_cmd.params if p.name == "source_type")
        choices = type_param.type.choices

        from kb.config import SOURCE_TYPE_DIRS

        for key in SOURCE_TYPE_DIRS:
            assert key in choices, f"Source type '{key}' missing from CLI choices"


class TestVersionBump:
    """Version must be bumped to current minor (cycle 34: 0.11.0)."""

    def test_version_is_0_9_16(self):
        # Test name preserves historical context (originally validated 0.9.16);
        # cycle 34 bumped to 0.11.0 per NEW-Q11. The cycle-34 regression
        # test_pyproject_version_is_0_11_0 + test_kb_init_version_matches_pyproject
        # provide the new cross-file lockstep guard.
        from kb import __version__

        assert __version__ == "0.11.0"
