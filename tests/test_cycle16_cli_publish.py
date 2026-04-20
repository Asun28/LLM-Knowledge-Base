"""Cycle 16 AC23-AC24 — kb publish CLI grows --format=siblings|sitemap.

Uses CliRunner; monkeypatches builders at import-site.
"""

from pathlib import Path
from unittest.mock import MagicMock

from click.testing import CliRunner

from kb import cli as kb_cli


def _ensure_out_dir(tmp_project: Path) -> str:
    """Pre-create out_dir so --out-dir containment check (outside PROJECT_ROOT) passes."""
    out = tmp_project / "out"
    out.mkdir(parents=True, exist_ok=True)
    return str(out)


class TestPublishFormatChoice:
    def test_format_help_lists_siblings(self) -> None:
        runner = CliRunner()
        result = runner.invoke(kb_cli.cli, ["publish", "--help"])
        assert result.exit_code == 0
        assert "siblings" in result.output

    def test_format_help_lists_sitemap(self) -> None:
        runner = CliRunner()
        result = runner.invoke(kb_cli.cli, ["publish", "--help"])
        assert result.exit_code == 0
        assert "sitemap" in result.output

    def test_format_help_lists_all_six(self) -> None:
        runner = CliRunner()
        result = runner.invoke(kb_cli.cli, ["publish", "--help"])
        for choice in ["llms", "llms-full", "graph", "siblings", "sitemap", "all"]:
            assert choice in result.output, f"help missing choice {choice!r}"


class TestPublishDispatch:
    def test_siblings_flag_dispatches_siblings_builder_only(self, tmp_project, monkeypatch) -> None:
        """AC23 — --format=siblings calls build_per_page_siblings only."""
        monkeypatch.setattr(kb_cli, "_setup_logging", lambda: None)
        # Mock all five builders at import site (cli.py does from kb.compile.publish import ...)
        mocks = {
            "build_llms_txt": MagicMock(return_value=tmp_project / "llms.txt"),
            "build_llms_full_txt": MagicMock(return_value=tmp_project / "llms-full.txt"),
            "build_graph_jsonld": MagicMock(return_value=tmp_project / "graph.jsonld"),
            "build_per_page_siblings": MagicMock(return_value=[tmp_project / "pages" / "a.txt"]),
            "build_sitemap_xml": MagicMock(return_value=tmp_project / "sitemap.xml"),
        }
        for name, m in mocks.items():
            monkeypatch.setattr(f"kb.compile.publish.{name}", m)

        runner = CliRunner()
        result = runner.invoke(
            kb_cli.cli,
            ["publish", "--format", "siblings", "--out-dir", _ensure_out_dir(tmp_project)],
        )
        assert result.exit_code == 0, result.output
        mocks["build_per_page_siblings"].assert_called_once()
        mocks["build_sitemap_xml"].assert_not_called()
        mocks["build_llms_txt"].assert_not_called()

    def test_sitemap_flag_dispatches_sitemap_only(self, tmp_project, monkeypatch) -> None:
        """AC23 — --format=sitemap calls build_sitemap_xml only."""
        monkeypatch.setattr(kb_cli, "_setup_logging", lambda: None)
        mocks = {
            "build_llms_txt": MagicMock(return_value=tmp_project / "llms.txt"),
            "build_llms_full_txt": MagicMock(return_value=tmp_project / "llms-full.txt"),
            "build_graph_jsonld": MagicMock(return_value=tmp_project / "graph.jsonld"),
            "build_per_page_siblings": MagicMock(return_value=[]),
            "build_sitemap_xml": MagicMock(return_value=tmp_project / "sitemap.xml"),
        }
        for name, m in mocks.items():
            monkeypatch.setattr(f"kb.compile.publish.{name}", m)

        runner = CliRunner()
        result = runner.invoke(
            kb_cli.cli,
            ["publish", "--format", "sitemap", "--out-dir", _ensure_out_dir(tmp_project)],
        )
        assert result.exit_code == 0, result.output
        mocks["build_sitemap_xml"].assert_called_once()
        mocks["build_per_page_siblings"].assert_not_called()

    def test_all_dispatches_all_five_builders(self, tmp_project, monkeypatch) -> None:
        """AC24 — --format=all calls all five builders."""
        monkeypatch.setattr(kb_cli, "_setup_logging", lambda: None)
        mocks = {
            "build_llms_txt": MagicMock(return_value=tmp_project / "llms.txt"),
            "build_llms_full_txt": MagicMock(return_value=tmp_project / "llms-full.txt"),
            "build_graph_jsonld": MagicMock(return_value=tmp_project / "graph.jsonld"),
            "build_per_page_siblings": MagicMock(return_value=[]),
            "build_sitemap_xml": MagicMock(return_value=tmp_project / "sitemap.xml"),
        }
        for name, m in mocks.items():
            monkeypatch.setattr(f"kb.compile.publish.{name}", m)

        runner = CliRunner()
        result = runner.invoke(
            kb_cli.cli,
            ["publish", "--format", "all", "--out-dir", _ensure_out_dir(tmp_project)],
        )
        assert result.exit_code == 0, result.output
        for name, m in mocks.items():
            m.assert_called_once(), name

    def test_incremental_true_threaded_to_siblings(self, tmp_project, monkeypatch) -> None:
        """AC24 — --incremental flag propagates to the siblings builder."""
        monkeypatch.setattr(kb_cli, "_setup_logging", lambda: None)
        spy = MagicMock(return_value=[])
        for name in (
            "build_llms_txt",
            "build_llms_full_txt",
            "build_graph_jsonld",
            "build_sitemap_xml",
        ):
            monkeypatch.setattr(f"kb.compile.publish.{name}", MagicMock(return_value=Path("x")))
        monkeypatch.setattr("kb.compile.publish.build_per_page_siblings", spy)

        runner = CliRunner()
        result = runner.invoke(
            kb_cli.cli,
            [
                "publish",
                "--format",
                "siblings",
                "--incremental",
                "--out-dir",
                _ensure_out_dir(tmp_project),
            ],
        )
        assert result.exit_code == 0, result.output
        # incremental=True passed as kwarg.
        _, kwargs = spy.call_args
        assert kwargs.get("incremental") is True

    def test_no_incremental_threaded_to_sitemap(self, tmp_project, monkeypatch) -> None:
        monkeypatch.setattr(kb_cli, "_setup_logging", lambda: None)
        spy = MagicMock(return_value=Path("x"))
        for name in (
            "build_llms_txt",
            "build_llms_full_txt",
            "build_graph_jsonld",
            "build_per_page_siblings",
        ):
            monkeypatch.setattr(f"kb.compile.publish.{name}", MagicMock(return_value=Path("x")))
        monkeypatch.setattr("kb.compile.publish.build_sitemap_xml", spy)

        runner = CliRunner()
        result = runner.invoke(
            kb_cli.cli,
            [
                "publish",
                "--format",
                "sitemap",
                "--no-incremental",
                "--out-dir",
                _ensure_out_dir(tmp_project),
            ],
        )
        assert result.exit_code == 0, result.output
        _, kwargs = spy.call_args
        assert kwargs.get("incremental") is False

    def test_invalid_format_rejected(self, tmp_project, monkeypatch) -> None:
        """click.Choice rejects unknown values."""
        monkeypatch.setattr(kb_cli, "_setup_logging", lambda: None)
        runner = CliRunner()
        result = runner.invoke(
            kb_cli.cli,
            ["publish", "--format", "bogus", "--out-dir", _ensure_out_dir(tmp_project)],
        )
        assert result.exit_code != 0
        assert "bogus" in result.output.lower() or "invalid" in result.output.lower()
