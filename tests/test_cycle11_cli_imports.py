"""Cycle 11 CLI import smoke tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from kb.cli import cli


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
    from kb.lint import runner

    def fake_run_all_checks(*, wiki_dir=None, fix=False):
        return {
            "issues": [],
            "summary": {"error": 0, "warning": 0, "info": 0},
            "fixes_applied": [],
        }

    monkeypatch.setattr(runner, "run_all_checks", fake_run_all_checks)
    monkeypatch.setattr(runner, "format_report", lambda report: "Lint Report")
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
