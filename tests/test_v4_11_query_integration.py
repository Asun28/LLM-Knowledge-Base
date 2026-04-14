"""End-to-end tests for query_wiki with output_format."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from kb.query.engine import query_wiki


def _create_page(wiki_dir: Path, page_id: str, title: str, content: str) -> None:
    path = wiki_dir / f"{page_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = f"""---
title: "{title}"
source:
  - "raw/articles/fake.md"
created: 2026-04-14
updated: 2026-04-14
type: concept
confidence: stated
---

{content}
"""
    path.write_text(fm, encoding="utf-8")


@pytest.fixture
def wiki_with_pages(tmp_wiki):
    _create_page(tmp_wiki, "concepts/rag", "RAG", "RAG means Retrieval Augmented Generation.")
    _create_page(tmp_wiki, "entities/openai", "OpenAI", "OpenAI is an AI lab.")
    return tmp_wiki


@pytest.fixture
def mock_llm():
    with patch("kb.query.engine.call_llm") as m:
        m.return_value = "RAG is Retrieval Augmented Generation. [source: concepts/rag]"
        yield m


def test_query_wiki_text_format_no_file(wiki_with_pages, mock_llm, monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    result = query_wiki("What is RAG?", wiki_dir=wiki_with_pages, output_format="text")
    assert "output_path" not in result


def test_query_wiki_no_format_default(wiki_with_pages, mock_llm, monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    result = query_wiki("What is RAG?", wiki_dir=wiki_with_pages)
    assert "output_path" not in result


def test_query_wiki_markdown_format_writes(wiki_with_pages, mock_llm, monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    result = query_wiki("What is RAG?", wiki_dir=wiki_with_pages, output_format="markdown")
    assert "output_path" in result
    assert result["output_format"] == "markdown"
    path = Path(result["output_path"])
    assert path.exists()
    assert "What is RAG?" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("fmt", ["markdown", "marp", "html", "chart", "jupyter"])
def test_query_wiki_all_formats(wiki_with_pages, mock_llm, monkeypatch, tmp_path, fmt):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    result = query_wiki("What is RAG?", wiki_dir=wiki_with_pages, output_format=fmt)
    assert "output_path" in result
    assert Path(result["output_path"]).exists()


def test_query_wiki_keyword_only_enforcement(wiki_with_pages, mock_llm):
    """output_format must be keyword-only — positional 5th arg must error."""
    with pytest.raises(TypeError):
        query_wiki("q", None, 10, None, "markdown")  # type: ignore[misc]


def test_query_wiki_existing_return_keys_preserved(wiki_with_pages, mock_llm):
    result = query_wiki("What is RAG?", wiki_dir=wiki_with_pages)
    for key in ("question", "answer", "citations", "source_pages", "context_pages"):
        assert key in result


def test_query_wiki_no_results_no_output_write(tmp_wiki, mock_llm, monkeypatch, tmp_path):
    """No match → early return; no file written even with output_format set."""
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    result = query_wiki("nonsense xyzzy pagerank", wiki_dir=tmp_wiki, output_format="markdown")
    assert "answer" in result
    assert "output_path" not in result


def test_query_wiki_invalid_format_surfaces_error(wiki_with_pages, mock_llm, monkeypatch, tmp_path):
    """Unknown format → output_error set, answer still present."""
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    result = query_wiki("What is RAG?", wiki_dir=wiki_with_pages, output_format="pdf")
    # Unknown format: result has output_error but no output_path
    assert "output_path" not in result
    assert "output_error" in result
    assert "answer" in result
