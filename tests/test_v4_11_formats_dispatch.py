"""Tests for the render_output dispatcher."""

from __future__ import annotations

import pytest

from kb.query.formats import VALID_FORMATS, render_output


@pytest.fixture
def sample():
    return {
        "question": "What is RAG?",
        "answer": "RAG is ...",
        "citations": [],
        "source_pages": ["concepts/rag"],
        "context_pages": [],
    }


def test_valid_formats_contents():
    assert VALID_FORMATS == frozenset({"text", "markdown", "marp", "html", "chart", "jupyter"})


def test_dispatch_markdown_writes_file(monkeypatch, tmp_path, sample):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = render_output("markdown", sample)
    assert path.exists()
    assert path.suffix == ".md"
    assert "What is RAG?" in path.read_text(encoding="utf-8")


def test_dispatch_html(monkeypatch, tmp_path, sample):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = render_output("html", sample)
    assert path.exists()
    assert path.suffix == ".html"
    content = path.read_text(encoding="utf-8")
    assert content.startswith("<!DOCTYPE html>")


def test_dispatch_chart_writes_py_and_json(monkeypatch, tmp_path, sample):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = render_output("chart", sample)
    assert path.exists()
    assert path.suffix == ".py"
    json_sidecar = path.with_suffix(".json")
    assert json_sidecar.exists()


def test_dispatch_jupyter(monkeypatch, tmp_path, sample):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = render_output("jupyter", sample)
    assert path.exists()
    assert path.suffix == ".ipynb"


def test_dispatch_marp(monkeypatch, tmp_path, sample):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = render_output("marp", sample)
    assert path.exists()
    assert path.suffix == ".md"
    assert "marp: true" in path.read_text(encoding="utf-8")


def test_dispatch_unknown_format(sample):
    with pytest.raises(ValueError, match="unknown format"):
        render_output("pdf", sample)


def test_dispatch_text_is_noop(sample):
    """text format does not write a file — returns None."""
    path = render_output("text", sample)
    assert path is None


def test_dispatch_case_normalization(monkeypatch, tmp_path, sample):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = render_output("  MARKDOWN  ", sample)
    assert path.exists()
    assert path.suffix == ".md"


def test_dispatch_empty_answer_ok(monkeypatch, tmp_path):
    """Empty answer is OK — adapter writes 'No answer synthesized'."""
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    empty = {"question": "q", "answer": "", "citations": [], "source_pages": []}
    path = render_output("markdown", empty)
    assert path.exists()
