"""Integration tests for Phase 2 MCP tools — tests actual MCP wrapper functions."""

from pathlib import Path

import kb.compile.linker
import kb.config
import kb.feedback.store
import kb.lint.semantic
import kb.review.context
import kb.review.refiner
import kb.utils.wiki_log
from kb.mcp_server import (
    kb_lint_consistency,
    kb_lint_deep,
    kb_query_feedback,
    kb_refine_page,
    kb_reliability_map,
    kb_review_page,
)


def _create_page(wiki_dir: Path, page_id: str, title: str, content: str, source_ref: str) -> None:
    """Helper to create a wiki page with frontmatter."""
    page_path = wiki_dir / f"{page_id}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        f'---\ntitle: "{title}"\nsource:\n  - {source_ref}\n'
        f"created: 2026-04-06\nupdated: 2026-04-06\ntype: concept\n"
        f"confidence: stated\n---\n\n"
    )
    page_path.write_text(fm + content, encoding="utf-8")


def _create_source(project_dir: Path, source_ref: str, content: str) -> None:
    """Helper to create a raw source file."""
    source_path = project_dir / source_ref
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(content, encoding="utf-8")


def _setup_project(tmp_project, monkeypatch):
    """Monkeypatch config paths to use tmp_project directory."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    monkeypatch.setattr(kb.config, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(kb.config, "RAW_DIR", raw_dir)
    monkeypatch.setattr(kb.config, "WIKI_LOG", wiki_dir / "log.md")
    # Also patch feedback/review paths to use tmp
    data_dir = tmp_project / ".data"
    data_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(kb.config, "FEEDBACK_PATH", data_dir / "query_feedback.json")
    monkeypatch.setattr(kb.config, "REVIEW_HISTORY_PATH", data_dir / "review_history.json")

    # Patch module-level imports that were bound at import time
    monkeypatch.setattr(kb.review.context, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(kb.review.context, "RAW_DIR", raw_dir)
    monkeypatch.setattr(kb.review.refiner, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(kb.review.refiner, "REVIEW_HISTORY_PATH", data_dir / "review_history.json")
    monkeypatch.setattr(kb.lint.semantic, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(kb.feedback.store, "FEEDBACK_PATH", data_dir / "query_feedback.json")
    monkeypatch.setattr(kb.compile.linker, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(kb.utils.wiki_log, "WIKI_LOG", wiki_dir / "log.md")

    return wiki_dir, raw_dir


# ── kb_review_page ────────────────────────────────────────────


def test_kb_review_page_returns_context(tmp_project, monkeypatch):
    """kb_review_page MCP tool returns review context with checklist."""
    wiki_dir, raw_dir = _setup_project(tmp_project, monkeypatch)
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG is retrieval.", "raw/articles/rag.md")
    _create_source(tmp_project, "raw/articles/rag.md", "Full article.")

    result = kb_review_page("concepts/rag")
    assert "Review Checklist" in result
    assert "RAG is retrieval." in result
    assert "Full article." in result


def test_kb_review_page_missing_page(tmp_project, monkeypatch):
    """kb_review_page returns error for non-existent page."""
    _setup_project(tmp_project, monkeypatch)
    result = kb_review_page("concepts/nonexistent")
    assert "Error" in result


# ── kb_refine_page ────────────────────────────────────────────


def test_kb_refine_page_updates_content(tmp_project, monkeypatch):
    """kb_refine_page MCP tool updates page and returns confirmation."""
    wiki_dir, _ = _setup_project(tmp_project, monkeypatch)
    _create_page(wiki_dir, "concepts/rag", "RAG", "Old.", "raw/articles/rag.md")

    result = kb_refine_page("concepts/rag", "New content.", "Fixed claims")
    assert "Refined: concepts/rag" in result
    assert "Fixed claims" in result
    # Verify file was actually updated
    text = (wiki_dir / "concepts" / "rag.md").read_text(encoding="utf-8")
    assert "New content." in text


def test_kb_refine_page_missing_page(tmp_project, monkeypatch):
    """kb_refine_page returns error for non-existent page."""
    _setup_project(tmp_project, monkeypatch)
    result = kb_refine_page("concepts/nonexistent", "Content.", "notes")
    assert "Error" in result


# ── kb_lint_deep ──────────────────────────────────────────────


def test_kb_lint_deep_returns_fidelity(tmp_project, monkeypatch):
    """kb_lint_deep MCP tool returns fidelity check context."""
    wiki_dir, raw_dir = _setup_project(tmp_project, monkeypatch)
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG content.", "raw/articles/rag.md")
    _create_source(tmp_project, "raw/articles/rag.md", "Source text.")

    result = kb_lint_deep("concepts/rag")
    assert "Source Fidelity Check" in result
    assert "RAG content." in result


# ── kb_lint_consistency ───────────────────────────────────────


def test_kb_lint_consistency_explicit_pages(tmp_project, monkeypatch):
    """kb_lint_consistency with explicit page IDs returns grouped content."""
    wiki_dir, _ = _setup_project(tmp_project, monkeypatch)
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG content.", "raw/articles/rag.md")
    _create_page(wiki_dir, "concepts/llm", "LLM", "LLM content.", "raw/articles/llm.md")

    result = kb_lint_consistency("concepts/rag,concepts/llm")
    assert "Cross-Page Consistency Check" in result
    assert "RAG content." in result
    assert "LLM content." in result


# ── kb_query_feedback ─────────────────────────────────────────


def test_kb_query_feedback_useful(tmp_project, monkeypatch):
    """kb_query_feedback MCP tool records feedback and returns confirmation."""
    _setup_project(tmp_project, monkeypatch)
    result = kb_query_feedback("What is RAG?", "useful", "concepts/rag")
    assert "Feedback recorded: useful" in result
    assert "Trust scores boosted" in result


def test_kb_query_feedback_invalid_rating(tmp_project, monkeypatch):
    """kb_query_feedback returns error for invalid rating."""
    _setup_project(tmp_project, monkeypatch)
    result = kb_query_feedback("Q", "bad_rating", "concepts/rag")
    assert "Error" in result


# ── kb_reliability_map ────────────────────────────────────────


def test_kb_reliability_map_empty(tmp_project, monkeypatch):
    """kb_reliability_map returns message when no feedback exists."""
    _setup_project(tmp_project, monkeypatch)
    result = kb_reliability_map()
    assert "No feedback recorded" in result


def test_kb_reliability_map_with_data(tmp_project, monkeypatch):
    """kb_reliability_map shows scores after feedback."""
    _setup_project(tmp_project, monkeypatch)
    kb_query_feedback("Q1", "useful", "concepts/rag")
    kb_query_feedback("Q2", "wrong", "concepts/rag")
    result = kb_reliability_map()
    assert "concepts/rag" in result
    assert "trust=" in result
