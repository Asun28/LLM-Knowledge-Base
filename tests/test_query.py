"""Tests for the query engine and citations."""

from pathlib import Path
from unittest.mock import patch

import pytest

from kb.query.citations import extract_citations, format_citations
from kb.query.engine import query_wiki, search_pages


def _create_wiki_page(path: Path, title: str, content: str, page_type: str = "concept") -> None:
    """Helper to create a wiki page with frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = f"""---
title: "{title}"
source:
  - raw/articles/test.md
created: 2026-04-06
updated: 2026-04-06
type: {page_type}
confidence: stated
---

"""
    path.write_text(fm + content, encoding="utf-8")


# ── Citation tests ─────────────────────────────────────────────


def test_extract_citations():
    """extract_citations finds [source: path] patterns."""
    text = "RAG is important [source: concepts/rag] and uses LLMs [source: concepts/llm]."
    citations = extract_citations(text)
    assert len(citations) == 2
    assert citations[0]["path"] == "concepts/rag"
    assert citations[0]["type"] == "wiki"


def test_extract_citations_raw_refs():
    """extract_citations finds [ref: path] patterns."""
    text = "According to the paper [ref: raw/papers/attention.pdf], transformers work."
    citations = extract_citations(text)
    assert len(citations) == 1
    assert citations[0]["type"] == "raw"
    assert citations[0]["path"] == "raw/papers/attention.pdf"


def test_extract_citations_empty():
    """extract_citations returns empty list for no citations."""
    assert extract_citations("No citations here.") == []


def test_format_citations():
    """format_citations produces markdown source list."""
    citations = [
        {"type": "wiki", "path": "concepts/rag", "context": "..."},
        {"type": "raw", "path": "raw/papers/test.pdf", "context": "..."},
    ]
    result = format_citations(citations)
    assert "[[concepts/rag]]" in result
    assert "`raw/papers/test.pdf`" in result


def test_format_citations_deduplicates():
    """format_citations removes duplicate paths."""
    citations = [
        {"type": "wiki", "path": "concepts/rag", "context": "..."},
        {"type": "wiki", "path": "concepts/rag", "context": "..."},
    ]
    result = format_citations(citations)
    assert result.count("concepts/rag") == 1


def test_format_citations_empty():
    """format_citations returns empty string for no citations."""
    assert format_citations([]) == ""


def test_format_citations_html_mode():
    """HTML mode returns <ul> with escaped <a> anchors."""
    citations = [
        {"type": "wiki", "path": "concepts/rag", "context": "..."},
        {"type": "raw", "path": "raw/articles/foo.md", "context": "..."},
    ]
    result = format_citations(citations, mode="html")
    assert "<ul" in result
    assert '<a href="./wiki/concepts/rag.md">concepts/rag</a>' in result
    assert "<code>raw/articles/foo.md</code>" in result


def test_format_citations_marp_mode():
    """Marp mode matches markdown rendering (kept distinct for future divergence)."""
    citations = [
        {"type": "wiki", "path": "concepts/rag", "context": "..."},
        {"type": "raw", "path": "raw/a.md", "context": "..."},
    ]
    out = format_citations(citations, mode="marp")
    assert "[[concepts/rag]]" in out
    assert "`raw/a.md`" in out


def test_format_citations_default_mode_unchanged():
    """Default mode must match previous behavior exactly — no call-site breakage."""
    citations = [{"type": "wiki", "path": "concepts/rag", "context": "x"}]
    legacy = format_citations(citations)
    explicit = format_citations(citations, mode="markdown")
    assert legacy == explicit
    assert "[[concepts/rag]]" in legacy


def test_format_citations_invalid_mode():
    """Unknown mode raises ValueError."""
    with pytest.raises(ValueError, match="mode"):
        format_citations([], mode="latex")


# ── Search tests ───────────────────────────────────────────────


def test_search_pages(tmp_wiki):
    """search_pages finds pages matching query terms."""
    _create_wiki_page(
        tmp_wiki / "concepts" / "rag.md",
        "Retrieval Augmented Generation",
        "RAG combines retrieval with generation for better LLM answers.",
    )
    _create_wiki_page(
        tmp_wiki / "concepts" / "fine-tuning.md",
        "Fine-Tuning",
        "Fine-tuning adapts a pre-trained model to specific tasks.",
    )
    results = search_pages("How does RAG work?", tmp_wiki)
    assert len(results) >= 1
    assert results[0]["id"] == "concepts/rag"


def test_search_pages_title_boost(tmp_wiki):
    """search_pages weights title matches higher than content matches."""
    _create_wiki_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "A technique for language models.",
    )
    _create_wiki_page(
        tmp_wiki / "summaries" / "article1.md",
        "Some Article",
        "This article mentions RAG briefly in passing.",
        page_type="summary",
    )
    results = search_pages("RAG", tmp_wiki)
    assert len(results) >= 1
    # Title match should rank higher
    assert results[0]["id"] == "concepts/rag"


def test_search_pages_empty_wiki(tmp_wiki):
    """search_pages returns empty list for empty wiki."""
    results = search_pages("anything", tmp_wiki)
    assert results == []


def test_search_pages_no_match(tmp_wiki):
    """search_pages returns empty list when no pages match."""
    _create_wiki_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "About retrieval augmented generation.",
    )
    results = search_pages("quantum computing", tmp_wiki)
    assert results == []


# ── Query integration tests ────────────────────────────────────


@patch("kb.query.engine.call_llm")
def test_query_wiki(mock_llm, tmp_wiki):
    """query_wiki searches, builds context, and calls LLM."""
    mock_llm.return_value = "RAG combines retrieval with generation [source: concepts/rag]."
    _create_wiki_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "RAG uses a retriever to find relevant documents before generating.",
    )
    result = query_wiki("What is RAG?", tmp_wiki)
    assert result["question"] == "What is RAG?"
    assert "RAG" in result["answer"]
    assert len(result["citations"]) >= 1
    assert "concepts/rag" in result["source_pages"]
    mock_llm.assert_called_once()


@patch("kb.query.engine.call_llm")
def test_query_wiki_no_results(mock_llm, tmp_wiki):
    """query_wiki handles empty wiki gracefully."""
    result = query_wiki("What is quantum computing?", tmp_wiki)
    assert "No relevant pages" in result["answer"]
    mock_llm.assert_not_called()


# ── Phase 4.5 HIGH regression tests ──────────────────────────────────────────


@patch("kb.query.engine.call_llm")
def test_query_wiki_h5_raw_dir_derivation(mock_llm, tmp_wiki):
    """Regression: Phase 4.5 HIGH item H5 (drop dead raw_dir containment try/except).

    query_wiki must still work after the dead candidate.relative_to() block was removed.
    raw_dir is now derived unconditionally from wiki_dir without a try/except guard.
    """
    mock_llm.return_value = "RAG stands for Retrieval-Augmented Generation."
    _create_wiki_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "RAG is a technique combining retrieval with generation.",
    )
    # wiki_dir is tmp_wiki — raw is derived as tmp_wiki.parent / "raw"
    result = query_wiki("What is RAG?", tmp_wiki)
    # Must return a valid dict (no crash from the removed try/except)
    assert isinstance(result, dict)
    assert "answer" in result
    assert "citations" in result
