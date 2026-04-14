"""Tests for kb query --format CLI flag."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from kb.cli import cli


@pytest.fixture
def mocked_query_wiki():
    with patch("kb.query.engine.query_wiki") as m:
        yield m


def test_cli_query_default_format_text(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "RAG is...",
        "citations": [],
        "source_pages": ["concepts/rag"],
    }
    runner = CliRunner()
    result = runner.invoke(cli, ["query", "What is RAG?"])
    assert result.exit_code == 0
    _, kwargs = mocked_query_wiki.call_args
    assert kwargs.get("output_format") in (None, "text")


def test_cli_query_markdown_format(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "RAG is...",
        "citations": [],
        "source_pages": [],
        "output_path": "/tmp/fake.md",
        "output_format": "markdown",
    }
    runner = CliRunner()
    result = runner.invoke(cli, ["query", "What is RAG?", "--format", "markdown"])
    assert result.exit_code == 0
    assert "/tmp/fake.md" in result.output
    _, kwargs = mocked_query_wiki.call_args
    assert kwargs.get("output_format") == "markdown"


def test_cli_query_rejects_invalid_format():
    runner = CliRunner()
    result = runner.invoke(cli, ["query", "q", "--format", "pdf"])
    assert result.exit_code == 2  # Click usage error


def test_cli_query_all_formats_accepted(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "x",
        "citations": [],
        "source_pages": [],
        "output_path": "/tmp/fake",
        "output_format": "markdown",
    }
    runner = CliRunner()
    for fmt in ("text", "markdown", "marp", "html", "chart", "jupyter"):
        res = runner.invoke(cli, ["query", "q", "--format", fmt])
        assert res.exit_code == 0, f"fmt {fmt} failed: {res.output}"


def test_cli_query_surfaces_output_error(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "x",
        "citations": [],
        "source_pages": [],
        "output_error": "simulated failure",
    }
    runner = CliRunner()
    result = runner.invoke(cli, ["query", "q", "--format", "markdown"])
    # Stderr is merged into output by default for CliRunner
    # Check the result captured stderr too
    combined = (result.output or "") + (result.stderr_bytes.decode() if hasattr(result, "stderr_bytes") else "")
    assert "simulated failure" in combined or "simulated failure" in result.output
