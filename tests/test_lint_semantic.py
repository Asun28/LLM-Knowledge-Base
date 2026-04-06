"""Tests for semantic lint checks (fidelity, consistency, completeness contexts)."""

from pathlib import Path

from kb.lint.semantic import (
    build_completeness_context,
    build_consistency_context,
    build_fidelity_context,
)


def _create_page(wiki_dir: Path, page_id: str, title: str, content: str, source_ref: str) -> None:
    """Helper to create a wiki page with frontmatter."""
    page_path = wiki_dir / f"{page_id}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        f"---\ntitle: \"{title}\"\nsource:\n  - {source_ref}\n"
        f"created: 2026-04-06\nupdated: 2026-04-06\ntype: concept\n"
        f"confidence: stated\n---\n\n"
    )
    page_path.write_text(fm + content, encoding="utf-8")


def _create_source(raw_dir: Path, source_ref: str, content: str) -> None:
    """Helper to create a raw source file."""
    source_path = raw_dir / source_ref.removeprefix("raw/")
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(content, encoding="utf-8")


# ── Fidelity context ──────────────────────────────────────────


def test_build_fidelity_context(tmp_project):
    """build_fidelity_context returns page + source side by side."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG uses retrieval.", "raw/articles/rag.md")
    _create_source(raw_dir, "raw/articles/rag.md", "RAG full article text.")

    context = build_fidelity_context("concepts/rag", wiki_dir, raw_dir)
    assert "Source Fidelity Check" in context
    assert "RAG uses retrieval." in context
    assert "RAG full article text." in context
    assert "Traced" in context
    assert "Unsourced" in context


def test_build_fidelity_context_missing_page(tmp_project):
    """build_fidelity_context returns error for missing page."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    context = build_fidelity_context("concepts/nonexistent", wiki_dir, raw_dir)
    assert "Error:" in context


# ── Consistency context ───────────────────────────────────────


def test_build_consistency_context_explicit(tmp_project):
    """build_consistency_context with explicit page IDs returns grouped content."""
    wiki_dir = tmp_project / "wiki"
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG content.", "raw/articles/rag.md")
    _create_page(wiki_dir, "concepts/llm", "LLM", "LLM content.", "raw/articles/llm.md")

    context = build_consistency_context(["concepts/rag", "concepts/llm"], wiki_dir)
    assert "Cross-Page Consistency Check" in context
    assert "RAG content." in context
    assert "LLM content." in context


def test_build_consistency_context_auto_shared_sources(tmp_project):
    """build_consistency_context auto-selects pages sharing sources."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    # Two pages sharing the same source
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG content.", "raw/articles/shared.md")
    _create_page(wiki_dir, "concepts/llm", "LLM", "LLM content.", "raw/articles/shared.md")
    _create_source(raw_dir, "raw/articles/shared.md", "Shared source.")

    context = build_consistency_context(wiki_dir=wiki_dir, raw_dir=raw_dir)
    assert "Group" in context
    # Both pages should appear in at least one group
    assert "concepts/rag" in context or "concepts/llm" in context


def test_build_consistency_context_empty(tmp_project):
    """build_consistency_context with no groups returns informative message."""
    wiki_dir = tmp_project / "wiki"
    # Single page, no groups possible
    _create_page(
        wiki_dir, "concepts/rag", "RAG", "Content with unique words only.",
        "raw/articles/unique1.md",
    )

    context = build_consistency_context(wiki_dir=wiki_dir)
    assert "No page groups found" in context or "Group" in context


def test_build_consistency_context_auto_wikilinks(tmp_project):
    """build_consistency_context groups pages connected by wikilinks."""
    wiki_dir = tmp_project / "wiki"
    _create_page(
        wiki_dir, "concepts/rag", "RAG",
        "RAG uses [[concepts/llm]] models.", "raw/articles/rag.md",
    )
    _create_page(wiki_dir, "concepts/llm", "LLM", "LLM content.", "raw/articles/llm.md")

    context = build_consistency_context(wiki_dir=wiki_dir)
    assert "Group" in context


# ── Completeness context ──────────────────────────────────────


def test_build_completeness_context(tmp_project):
    """build_completeness_context returns source alongside page for comparison."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    _create_page(wiki_dir, "concepts/rag", "RAG", "Short summary.", "raw/articles/rag.md")
    _create_source(raw_dir, "raw/articles/rag.md", "Long detailed source with many claims.")

    context = build_completeness_context("concepts/rag", wiki_dir, raw_dir)
    assert "Completeness Check" in context
    assert "Short summary." in context
    assert "Long detailed source" in context
    assert "NOT represented" in context


def test_build_completeness_context_missing_page(tmp_project):
    """build_completeness_context returns error for missing page."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    context = build_completeness_context("concepts/nonexistent", wiki_dir, raw_dir)
    assert "Error:" in context
