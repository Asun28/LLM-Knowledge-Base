"""Tests for the CLI commands."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from kb.cli import cli

runner = CliRunner()


def test_cli_version():
    """CLI --version prints version (cycle 34 bumped 0.10.0 → 0.11.0)."""
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.11.0" in result.output


def test_cli_help():
    """CLI --help lists all commands."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "ingest" in result.output
    assert "compile" in result.output
    assert "query" in result.output
    assert "lint" in result.output
    assert "evolve" in result.output


@patch("kb.ingest.pipeline.extract_from_source")
def test_cli_ingest(mock_extract, tmp_path):
    """CLI ingest command processes a source file."""
    mock_extract.return_value = {
        "title": "Test",
        "entities_mentioned": [],
        "concepts_mentioned": [],
    }

    # Set up temp dirs
    raw_dir = tmp_path / "raw" / "articles"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "test.md"
    source.write_text("# Test Article\n\nContent here.")

    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True)
    (wiki_dir / "index.md").write_text(
        "---\ntitle: Wiki Index\nupdated: 2026-04-06\n---\n\n"
        "## Entities\n\n*No pages yet.*\n\n## Concepts\n\n*No pages yet.*\n\n"
        "## Comparisons\n\n*No pages yet.*\n\n## Summaries\n\n*No pages yet.*\n\n"
        "## Synthesis\n\n*No pages yet.*\n"
    )
    (wiki_dir / "_sources.md").write_text("---\ntitle: Sources\nupdated: 2026-04-06\n---\n\n")
    (wiki_dir / "log.md").write_text("---\ntitle: Log\nupdated: 2026-04-06\n---\n\n")

    with (
        patch("kb.ingest.pipeline.RAW_DIR", tmp_path / "raw"),
        patch("kb.utils.paths.RAW_DIR", tmp_path / "raw"),
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
    ):
        result = runner.invoke(cli, ["ingest", str(source), "--type", "article"])

    assert result.exit_code == 0
    assert "Ingesting" in result.output
    assert "Done" in result.output


def test_cli_lint(tmp_path):
    """CLI lint command runs checks."""
    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    with (
        patch("kb.lint.runner.WIKI_DIR", wiki_dir),
        patch("kb.lint.runner.RAW_DIR", raw_dir),
        patch("kb.lint.checks.WIKI_DIR", wiki_dir),
        patch("kb.lint.checks.RAW_DIR", raw_dir),
    ):
        result = runner.invoke(cli, ["lint"])

    assert result.exit_code == 0
    assert "Lint Report" in result.output


def test_cli_evolve(tmp_path):
    """CLI evolve command runs analysis."""
    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True)

    with patch("kb.evolve.analyzer.WIKI_DIR", wiki_dir):
        result = runner.invoke(cli, ["evolve"])

    assert result.exit_code == 0
    assert "Evolution Report" in result.output


# ── Cycle 11 CLI import smoke tests (folded from test_cycle11_cli_imports.py) ─


def _assert_ok(result) -> None:
    assert result.exit_code == 0, f"output:\n{result.output}\nexception:\n{result.exception!r}"


def test_ingest_cli_runner_smoke(monkeypatch, tmp_path):
    from kb.ingest import pipeline

    source = tmp_path / "source.md"
    source.write_text("# Source\n", encoding="utf-8")

    def fake_ingest_source(source_path, source_type):
        return {
            "source_type": source_type or "article",
            "content_hash": "abc123",
            "pages_created": [],
            "pages_updated": [],
            "pages_skipped": [],
            "affected_pages": [],
            "wikilinks_injected": 0,
        }

    monkeypatch.setattr(pipeline, "ingest_source", fake_ingest_source)
    result = CliRunner().invoke(cli, ["ingest", str(source)])
    _assert_ok(result)


def test_compile_cli_runner_smoke(monkeypatch):
    from kb.compile import compiler

    def fake_compile_wiki(*, incremental=True):
        return {
            "sources_processed": 0,
            "pages_created": [],
            "pages_updated": [],
            "pages_skipped": [],
            "errors": [],
        }

    monkeypatch.setattr(compiler, "compile_wiki", fake_compile_wiki)
    result = CliRunner().invoke(cli, ["compile"])
    _assert_ok(result)


def test_query_cli_runner_smoke(monkeypatch):
    from kb.query import engine

    def fake_query_wiki(question, *, output_format=None):
        return {
            "answer": "ok",
            "citations": [],
            "source_pages": [],
            "context_pages": [],
        }

    monkeypatch.setattr(engine, "query_wiki", fake_query_wiki)
    result = CliRunner().invoke(cli, ["query", "what is tested?"])
    _assert_ok(result)


def test_lint_cli_runner_smoke(monkeypatch):
    from kb.lint import runner as lint_runner

    def fake_run_all_checks(*, wiki_dir=None, fix=False):
        return {
            "issues": [],
            "summary": {"error": 0, "warning": 0, "info": 0},
            "fixes_applied": [],
        }

    monkeypatch.setattr(lint_runner, "run_all_checks", fake_run_all_checks)
    monkeypatch.setattr(lint_runner, "format_report", lambda report: "Lint Report")
    result = CliRunner().invoke(cli, ["lint"])
    _assert_ok(result)


def test_evolve_cli_runner_smoke(monkeypatch):
    from kb.evolve import analyzer

    def fake_generate_evolution_report():
        return {"suggestions": []}

    monkeypatch.setattr(analyzer, "generate_evolution_report", fake_generate_evolution_report)
    monkeypatch.setattr(analyzer, "format_evolution_report", lambda report: "Evolution Report")
    result = CliRunner().invoke(cli, ["evolve"])
    _assert_ok(result)


def test_mcp_cli_runner_smoke(monkeypatch):
    from kb import mcp_server

    monkeypatch.setattr(mcp_server, "main", lambda: None)
    result = CliRunner().invoke(cli, ["mcp"])
    _assert_ok(result)


def _version_short_circuit_env() -> dict[str, str]:
    """Build a minimal env for the short-circuit subprocess.

    R1 Sonnet fix — copying ``os.environ`` would let a polluted parent
    ``PYTHONPATH`` (e.g. a rogue ``kb/config.py`` on an existing entry) shadow
    our explicit ``<repo>/src`` entry. Build a minimal dict from scratch that
    contains only the keys required to launch Python on this platform.
    """
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": src_path,
    }
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    return env


def _run_version_short_circuit(flag: str) -> subprocess.CompletedProcess[str]:
    code = f"""
import sys
sys.argv = ["kb.cli", "{flag}"]
try:
    import kb.cli
except SystemExit as exc:
    assert exc.code == 0
    assert "kb.config" not in sys.modules
    raise
raise AssertionError("kb.cli import did not short-circuit")
"""
    return subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env=_version_short_circuit_env(),
        cwd=Path(__file__).resolve().parents[1],
    )


def test_version_short_circuit_long():
    result = _run_version_short_circuit("--version")
    assert result.returncode == 0, result.stderr
    assert "kb, version" in result.stdout


def test_version_short_circuit_short():
    result = _run_version_short_circuit("-V")
    assert result.returncode == 0, result.stderr
    assert "kb, version" in result.stdout


# ── CLI boot sweep_orphan_tmp wiring (cycle 43 AC12 fold from test_cycle13_sweep_wiring.py) ─

import time  # noqa: E402  — imported here to keep the canonical-home import block above untouched

from kb import cli as cli_mod  # noqa: E402


class TestCliBootSweep:
    """AC14 — CLI boot sweep wiring.

    The kb.cli:cli group callback sweeps PROJECT_ROOT/.data and WIKI_DIR for
    orphan atomic-write .tmp siblings on every CLI invocation (after the AC30
    --version short-circuit and Click's eager --version/--help callbacks).

    Sub-tests:
    - spy on kb.cli.sweep_orphan_tmp asserts it's called with both deduped
      resolved paths
    - pre-aged .tmp files older than 1h are removed; fresh ones survive
    """

    def test_sweep_called_with_both_dirs(self, tmp_kb_env, monkeypatch):
        """Spy proves sweep_orphan_tmp is called with .data and WIKI_DIR."""
        calls: list[Path] = []
        real = cli_mod.sweep_orphan_tmp

        def _spy(target):
            calls.append(target)
            return real(target)

        monkeypatch.setattr(cli_mod, "sweep_orphan_tmp", _spy)

        runner = CliRunner()
        result = runner.invoke(cli_mod.cli, ["lint", "--help"])
        assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"

        # Spy MUST receive both the .data and the wiki paths (resolved + deduped).
        expected_data = (tmp_kb_env / ".data").resolve()
        expected_wiki = (tmp_kb_env / "wiki").resolve()
        # On Windows tmp paths the resolved value may be the same shape — assert
        # by membership in the set of call args.
        call_set = {p.resolve() if isinstance(p, Path) else Path(p).resolve() for p in calls}
        assert expected_data in call_set, f"Expected {expected_data} in spy calls; got {call_set}"
        assert expected_wiki in call_set, f"Expected {expected_wiki} in spy calls; got {call_set}"

    def test_stale_tmp_actually_removed(self, tmp_kb_env):
        """Pre-aged .tmp files (mtime > 1 h) are reaped; fresh ones survive."""
        data_dir = tmp_kb_env / ".data"
        data_dir.mkdir(exist_ok=True)
        wiki_dir = tmp_kb_env / "wiki"
        wiki_dir.mkdir(exist_ok=True)

        old_data = data_dir / "old.tmp"
        old_data.write_text("stale", encoding="utf-8")
        old_wiki = wiki_dir / "old.tmp"
        old_wiki.write_text("stale", encoding="utf-8")
        fresh_data = data_dir / "fresh.tmp"
        fresh_data.write_text("hot", encoding="utf-8")

        # Backdate the two old files by 2 hours.
        two_hours_ago = time.time() - 7200
        os.utime(old_data, (two_hours_ago, two_hours_ago))
        os.utime(old_wiki, (two_hours_ago, two_hours_ago))

        runner = CliRunner()
        result = runner.invoke(cli_mod.cli, ["lint", "--help"])
        assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"

        assert not old_data.exists(), f"stale {old_data} should have been removed"
        assert not old_wiki.exists(), f"stale {old_wiki} should have been removed"
        assert fresh_data.exists(), f"fresh {fresh_data} must NOT be removed"

    def test_sweep_dedup_pathological_alias(self, tmp_kb_env, monkeypatch):
        """When PROJECT_ROOT/.data and WIKI_DIR resolve to the same path,
        the sweep runs ONCE on that path (not twice).
        """
        # Force a pathological alias by patching WIKI_DIR to PROJECT_ROOT/.data
        import kb.config as config

        aliased = (tmp_kb_env / ".data").resolve()
        aliased.mkdir(exist_ok=True)
        monkeypatch.setattr(config, "WIKI_DIR", aliased)

        calls: list[Path] = []
        real = cli_mod.sweep_orphan_tmp

        def _spy(target):
            calls.append(Path(target).resolve())
            return real(target)

        monkeypatch.setattr(cli_mod, "sweep_orphan_tmp", _spy)

        runner = CliRunner()
        result = runner.invoke(cli_mod.cli, ["lint", "--help"])
        assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"

        # Dedup means the aliased path appears at most once in the calls.
        unique_calls = set(calls)
        assert aliased in unique_calls
        assert calls.count(aliased) == 1, (
            f"Expected dedup to call {aliased} once; got {calls.count(aliased)} times "
            f"(all calls: {calls})"
        )
