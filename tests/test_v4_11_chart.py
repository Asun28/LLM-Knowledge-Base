"""Tests for kb.query.formats.chart adapter."""

from __future__ import annotations

import ast
import json

import pytest

from kb.query.formats.chart import render_chart


@pytest.fixture
def sample():
    return {
        "question": "What is RAG?",
        "answer": "RAG is ...",
        "citations": [{"type": "wiki", "path": "concepts/rag", "context": "..."}],
        "source_pages": ["concepts/rag", "entities/openai", "concepts/embeddings"],
        "context_pages": ["concepts/rag"],
    }


def test_chart_returns_script_and_json(sample):
    script, data_json = render_chart(sample)
    assert isinstance(script, str)
    assert isinstance(data_json, str)


def test_chart_json_is_valid(sample):
    _, data_json = render_chart(sample)
    data = json.loads(data_json)
    assert data["question"] == "What is RAG?"
    assert len(data["source_pages"]) == 3
    assert data["source_pages"][0]["rank"] == 1
    assert data["source_pages"][0]["id"] == "concepts/rag"


def test_chart_script_parses_as_python(sample):
    script, _ = render_chart(sample)
    ast.parse(script)  # valid Python syntax


def test_chart_script_imports_matplotlib(sample):
    script, _ = render_chart(sample)
    assert "import matplotlib.pyplot as plt" in script


def test_chart_script_injection_safe_from_question():
    """Script is template-only — hostile question lands only in the JSON sidecar."""
    hostile = {
        "question": '"""; import os; os.system("rm -rf /"); x = """',
        "answer": "ok",
        "citations": [],
        "source_pages": ["concepts/rag"],
        "context_pages": [],
    }
    script, data_json = render_chart(hostile)
    ast.parse(script)
    # Round-trip the hostile content through JSON
    data = json.loads(data_json)
    assert data["question"] == hostile["question"]
    # The hostile payload is NOT in the script source (it lives only in JSON)
    assert 'os.system("rm -rf /")' not in script


def test_chart_injection_safe_from_page_id():
    """Page IDs are JSON-encoded into the sidecar, never f-string interpolated."""
    hostile = {
        "question": "q",
        "answer": "a",
        "citations": [],
        "source_pages": ["concepts/'); import os; os.system('pwn'); x='"],
        "context_pages": [],
    }
    script, data_json = render_chart(hostile)
    ast.parse(script)
    data = json.loads(data_json)
    assert data["source_pages"][0]["id"] == hostile["source_pages"][0]
    # The hostile page ID must NOT appear in the script body
    assert "os.system('pwn')" not in script


def test_chart_empty_source_pages():
    """Zero pages produces a script that prints an error and exits cleanly."""
    empty = {
        "question": "q",
        "answer": "a",
        "citations": [],
        "source_pages": [],
        "context_pages": [],
    }
    script, data_json = render_chart(empty)
    ast.parse(script)
    data = json.loads(data_json)
    assert data["source_pages"] == []
    # The script has an explicit empty-guard
    assert "No source pages" in script


def test_chart_rejects_oversize():
    from kb.config import MAX_OUTPUT_CHARS

    oversize = {
        "question": "q",
        "answer": "x" * (MAX_OUTPUT_CHARS + 1),
        "citations": [],
        "source_pages": [],
    }
    with pytest.raises(ValueError, match="MAX_OUTPUT_CHARS"):
        render_chart(oversize)
