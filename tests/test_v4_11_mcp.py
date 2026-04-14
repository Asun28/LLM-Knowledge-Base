"""Tests for kb_query MCP tool with output_format param."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from kb.mcp.core import kb_query


@pytest.fixture
def mocked_query_wiki():
    with patch("kb.mcp.core.query_wiki") as m:
        yield m


def test_mcp_kb_query_format_requires_use_api(mocked_query_wiki):
    """output_format requires use_api=True — default mode returns raw context."""
    result = kb_query("What is RAG?", output_format="markdown", use_api=False)
    assert result.startswith("Error:")
    assert "use_api" in result


def test_mcp_kb_query_invalid_format():
    result = kb_query("q", output_format="pdf", use_api=True)
    assert result.startswith("Error:")
    assert "pdf" in result


def test_mcp_kb_query_empty_format_default_mode_not_errored(monkeypatch, tmp_wiki):
    """Empty output_format + Claude Code mode — existing behavior preserved."""
    monkeypatch.setattr("kb.mcp.core.PROJECT_ROOT", tmp_wiki.parent)
    # Any existing wiki or empty wiki; we just check it doesn't spuriously error
    # on output_format validation
    result = kb_query("What is RAG?", output_format="", use_api=False)
    # Should NOT start with "Error: unknown output_format" or similar
    assert "unknown output_format" not in result
    assert "output_format requires use_api" not in result


def test_mcp_kb_query_format_use_api_success(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "RAG is ...",
        "citations": [{"type": "wiki", "path": "concepts/rag", "context": "..."}],
        "source_pages": ["concepts/rag"],
        "output_path": "/tmp/out.md",
        "output_format": "markdown",
    }
    result = kb_query("What is RAG?", output_format="markdown", use_api=True)
    assert "Output written to: /tmp/out.md" in result
    assert "(markdown)" in result


def test_mcp_kb_query_format_case_normalization(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "ok",
        "citations": [],
        "source_pages": [],
        "output_path": "/tmp/out.md",
        "output_format": "markdown",
    }
    result = kb_query("q", output_format="  MARKDOWN  ", use_api=True)
    assert not result.startswith("Error:")


def test_mcp_kb_query_format_text_equals_no_format(mocked_query_wiki):
    """output_format='text' should behave like empty — no file output, no error."""
    mocked_query_wiki.return_value = {
        "answer": "ok", "citations": [], "source_pages": [],
    }
    result = kb_query("q", output_format="text", use_api=True)
    assert not result.startswith("Error:")


def test_mcp_kb_query_format_output_error_surfaced(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "ok",
        "citations": [],
        "source_pages": [],
        "output_error": "disk full",
    }
    result = kb_query("q", output_format="markdown", use_api=True)
    assert "[warn] Output format failed: disk full" in result
