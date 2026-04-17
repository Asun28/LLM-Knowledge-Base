"""Tests for Phase 4 CLI error truncation."""

from __future__ import annotations

from click.testing import CliRunner


def test_ingest_error_truncates_long_message(monkeypatch):
    from kb import cli as _cli
    from kb.ingest import pipeline
    from kb.utils.llm import LLMError

    def _raise_long(*args, **kwargs):
        raise LLMError("x" * 2000)

    monkeypatch.setattr(pipeline, "ingest_source", _raise_long)
    runner = CliRunner()
    result = runner.invoke(_cli.cli, ["ingest", "raw/articles/nope.md"])
    output = result.output or ""
    assert "x" * 2000 not in output
    assert "..." in output


def test_compile_error_truncates_long_message(monkeypatch):
    from kb import cli as _cli
    from kb.compile import compiler
    from kb.utils.llm import LLMError

    def _raise_long(*args, **kwargs):
        raise LLMError("y" * 2000)

    monkeypatch.setattr(compiler, "compile_wiki", _raise_long)
    runner = CliRunner()
    result = runner.invoke(_cli.cli, ["compile"])
    output = result.output or ""
    assert "y" * 2000 not in output
    assert "..." in output


def test_query_error_truncates_long_message(monkeypatch):
    from kb import cli as _cli
    from kb.query import engine
    from kb.utils.llm import LLMError

    def _raise_long(*args, **kwargs):
        raise LLMError("z" * 2000)

    monkeypatch.setattr(engine, "query_wiki", _raise_long)
    runner = CliRunner()
    result = runner.invoke(_cli.cli, ["query", "test"])
    output = result.output or ""
    assert "z" * 2000 not in output
    assert "..." in output


def test_lint_error_truncates_long_message(monkeypatch):
    from kb import cli as _cli
    from kb.lint import runner
    from kb.utils.llm import LLMError

    def _raise_long(*args, **kwargs):
        raise LLMError("a" * 2000)

    monkeypatch.setattr(runner, "run_all_checks", _raise_long)
    runner_cli = CliRunner()
    result = runner_cli.invoke(_cli.cli, ["lint"])
    output = result.output or ""
    assert "a" * 2000 not in output
    assert "..." in output


def test_evolve_error_truncates_long_message(monkeypatch):
    from kb import cli as _cli
    from kb.evolve import analyzer
    from kb.utils.llm import LLMError

    def _raise_long(*args, **kwargs):
        raise LLMError("b" * 2000)

    monkeypatch.setattr(analyzer, "generate_evolution_report", _raise_long)
    runner = CliRunner()
    result = runner.invoke(_cli.cli, ["evolve"])
    output = result.output or ""
    assert "b" * 2000 not in output
    assert "..." in output


def test_truncate_preserves_short_messages():
    from kb.cli import _truncate

    short = "error"
    assert _truncate(short) == short


def test_truncate_cuts_long_messages():
    from kb.cli import _truncate

    long = "x" * 1000
    result = _truncate(long)
    assert len(result) == 503  # 500 + "..."
    assert result.endswith("...")
