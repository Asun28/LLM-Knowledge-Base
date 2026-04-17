"""Tests for Phase 4 query/ correctness fixes."""

from __future__ import annotations


def test_citation_rejects_double_dot_midcomponent():
    from kb.query.citations import extract_citations

    text = "See [source: raw/a..b/page]."
    cites = extract_citations(text)
    assert cites == [], f"Expected empty but got {cites}"


def test_citation_rejects_empty_component():
    from kb.query.citations import extract_citations

    text = "See [source: raw//page]."
    assert extract_citations(text) == []


def test_citation_accepts_valid_path():
    from kb.query.citations import extract_citations

    text = "See [source: raw/articles/my-paper.md]."
    cites = extract_citations(text)
    assert len(cites) == 1


def test_rewrite_query_falls_back_on_overlong_output(monkeypatch):
    """LLM preamble must trigger fallback to original question."""
    from kb.query import rewriter as _rw

    def _fake_llm(prompt, tier="scan", **kwargs):
        return "The question asks about X. Standalone version: What is RAG?"

    monkeypatch.setattr(_rw, "call_llm", _fake_llm)
    out = _rw.rewrite_query("What is RAG?", conversation_context="user: earlier\nassistant: ok")
    # Fallback: output is > 3x len of original, so use original
    assert out == "What is RAG?"


def test_rewrite_query_skip_heuristic_detects_deictic():
    """'Tell me more about that approach' must NOT be skipped."""
    from kb.query import rewriter as _rw

    assert _rw._should_rewrite("Tell me more about that approach") is True
    assert _rw._should_rewrite("What is retrieval augmented generation system") is False


def test_bm25_empty_corpus_logs_debug_not_warning(caplog):
    import logging

    from kb.query.bm25 import BM25Index

    # BM25Index takes list of token lists; pass one doc with no tokens → avgdl=0
    with caplog.at_level(logging.DEBUG, logger="kb.query.bm25"):
        BM25Index(documents=[[]])

    # Must have no WARNING records about avgdl
    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    avgdl_warnings = [
        r for r in warning_records if "avgdl" in r.message.lower() or "avg" in r.message.lower()
    ]
    assert avgdl_warnings == [], f"Unexpected avgdl warning: {avgdl_warnings}"
