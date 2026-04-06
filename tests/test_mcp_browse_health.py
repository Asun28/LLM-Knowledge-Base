"""Tests for MCP browse and health tools (kb.mcp.browse, kb.mcp.health)."""

from unittest.mock import patch

import kb.config
import kb.mcp.app
import kb.mcp.browse
import kb.utils.pages
from kb.mcp.browse import (
    kb_list_pages,
    kb_list_sources,
    kb_read_page,
    kb_search,
    kb_stats,
)
from kb.mcp.health import kb_evolve, kb_lint

# ── Helpers ──────────────────────────────────────────────────────


def _setup_browse_dirs(tmp_project, monkeypatch):
    """Monkeypatch config and module-level paths for browse tools."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    monkeypatch.setattr(kb.config, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(kb.config, "RAW_DIR", raw_dir)
    # Patch module-level imports bound at import time
    monkeypatch.setattr(kb.mcp.browse, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(kb.mcp.browse, "RAW_DIR", raw_dir)
    monkeypatch.setattr(kb.mcp.app, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(kb.utils.pages, "WIKI_DIR", wiki_dir)
    return wiki_dir, raw_dir


# ── kb_search ────────────────────────────────────────────────────


def test_kb_search_returns_results(tmp_project, monkeypatch, create_wiki_page):
    """kb_search finds pages matching a keyword query."""
    wiki_dir, _ = _setup_browse_dirs(tmp_project, monkeypatch)
    create_wiki_page(
        "concepts/retrieval-augmented-generation",
        title="Retrieval Augmented Generation",
        content="RAG combines retrieval with generation for grounded answers.",
        wiki_dir=wiki_dir,
    )
    create_wiki_page(
        "entities/openai",
        title="OpenAI",
        content="OpenAI builds large language models.",
        wiki_dir=wiki_dir,
    )

    result = kb_search("retrieval augmented generation")
    assert "Found" in result
    assert "retrieval-augmented-generation" in result


def test_kb_search_no_results(tmp_project, monkeypatch, create_wiki_page):
    """kb_search returns a 'no matches' message for nonexistent terms."""
    wiki_dir, _ = _setup_browse_dirs(tmp_project, monkeypatch)
    create_wiki_page(
        "concepts/rag",
        title="RAG",
        content="Retrieval augmented generation.",
        wiki_dir=wiki_dir,
    )

    result = kb_search("xyzzyplugh")
    assert result == "No matching pages found."


def test_kb_search_max_results_clamped(tmp_project, monkeypatch, create_wiki_page):
    """kb_search clamps max_results > 100 to 100 (no crash)."""
    wiki_dir, _ = _setup_browse_dirs(tmp_project, monkeypatch)
    create_wiki_page(
        "concepts/rag",
        title="RAG",
        content="Retrieval augmented generation.",
        wiki_dir=wiki_dir,
    )

    # Should not error — internally clamped to 100
    result = kb_search("retrieval", max_results=999)
    assert isinstance(result, str)
    # Either finds results or returns no-match — no crash
    assert "Found" in result or "No matching" in result


# ── kb_read_page ─────────────────────────────────────────────────


def test_kb_read_page_exists(tmp_project, monkeypatch, create_wiki_page):
    """kb_read_page returns the full content of an existing page."""
    wiki_dir, _ = _setup_browse_dirs(tmp_project, monkeypatch)
    create_wiki_page(
        "concepts/rag",
        title="RAG",
        content="RAG is retrieval augmented generation.",
        wiki_dir=wiki_dir,
    )

    result = kb_read_page("concepts/rag")
    assert "RAG" in result
    assert "retrieval augmented generation" in result
    # Should contain frontmatter
    assert "title:" in result


def test_kb_read_page_not_found(tmp_project, monkeypatch):
    """kb_read_page returns 'not found' error for a nonexistent page."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    result = kb_read_page("concepts/nonexistent")
    assert "not found" in result.lower() or "Page not found" in result


def test_kb_read_page_traversal_blocked(tmp_project, monkeypatch):
    """kb_read_page blocks path traversal attempts with '..'."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    result = kb_read_page("../../../etc/passwd")
    assert "Error" in result or "Invalid" in result


# ── kb_list_pages ────────────────────────────────────────────────


def test_kb_list_pages_all(tmp_project, monkeypatch, create_wiki_page):
    """kb_list_pages lists all wiki pages with correct count."""
    wiki_dir, _ = _setup_browse_dirs(tmp_project, monkeypatch)
    create_wiki_page("concepts/rag", title="RAG", content="About RAG.", wiki_dir=wiki_dir)
    create_wiki_page(
        "entities/openai", title="OpenAI", content="About OpenAI.",
        page_type="entity", wiki_dir=wiki_dir,
    )
    create_wiki_page(
        "summaries/test-article", title="Test Article", content="Summary.",
        page_type="summary", wiki_dir=wiki_dir,
    )

    result = kb_list_pages()
    assert "Total: 3 page(s)" in result
    assert "concepts/rag" in result
    assert "entities/openai" in result
    assert "summaries/test-article" in result


def test_kb_list_pages_filtered(tmp_project, monkeypatch, create_wiki_page):
    """kb_list_pages filters by page type prefix."""
    wiki_dir, _ = _setup_browse_dirs(tmp_project, monkeypatch)
    create_wiki_page("concepts/rag", title="RAG", content="About RAG.", wiki_dir=wiki_dir)
    create_wiki_page("concepts/llm", title="LLM", content="About LLM.", wiki_dir=wiki_dir)
    create_wiki_page(
        "entities/openai", title="OpenAI", content="About OpenAI.",
        page_type="entity", wiki_dir=wiki_dir,
    )

    result = kb_list_pages(page_type="concepts")
    assert "Total: 2 page(s)" in result
    assert "concepts/rag" in result
    assert "concepts/llm" in result
    assert "entities/openai" not in result


# ── kb_list_sources ──────────────────────────────────────────────


def test_kb_list_sources_empty(tmp_project, monkeypatch):
    """kb_list_sources returns zero count when raw dir has no files."""
    _, raw_dir = _setup_browse_dirs(tmp_project, monkeypatch)
    # raw subdirectories exist but are empty (created by tmp_project fixture)

    result = kb_list_sources()
    assert "Total:" in result
    assert "0 source file(s)" in result


# ── kb_stats ─────────────────────────────────────────────────────


def test_kb_stats_runs(tmp_project, monkeypatch):
    """kb_stats returns formatted statistics via mocked analyze_coverage and graph_stats."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    mock_coverage = {
        "total_pages": 42,
        "by_type": {"concept": 20, "entity": 15, "summary": 7},
        "under_covered_types": ["comparison"],
        "orphan_concepts": ["concepts/orphan-one"],
    }
    mock_stats = {
        "nodes": 42,
        "edges": 78,
        "components": 3,
        "most_linked": [("entities/openai", 10), ("concepts/rag", 8)],
        "pagerank": [("entities/openai", 0.085), ("concepts/rag", 0.072)],
        "bridge_nodes": [("concepts/llm", 0.15)],
    }

    # Lazy imports inside kb_stats — patch at the source module
    with (
        patch("kb.evolve.analyzer.analyze_coverage", return_value=mock_coverage) as mock_cov,
        patch("kb.graph.builder.build_graph", return_value="fake_graph") as mock_bg,
        patch("kb.graph.builder.graph_stats", return_value=mock_stats) as mock_gs,
    ):
        result = kb_stats()

    mock_cov.assert_called_once()
    mock_bg.assert_called_once()
    mock_gs.assert_called_once_with("fake_graph")

    assert "Wiki Statistics" in result
    assert "42" in result  # total pages
    assert "concept: 20" in result
    assert "entity: 15" in result
    assert "78 edges" in result
    assert "3 component(s)" in result
    assert "comparison" in result  # missing type
    assert "orphan-one" in result  # orphan concept
    assert "entities/openai" in result  # most linked + pagerank
    assert "concepts/llm" in result  # bridge node


def test_kb_stats_error_handling(tmp_project, monkeypatch):
    """kb_stats returns an error message when underlying functions fail."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    # Lazy import — patch at source module
    with patch("kb.evolve.analyzer.analyze_coverage", side_effect=RuntimeError("boom")):
        result = kb_stats()

    assert "Error" in result
    assert "boom" in result


# ── kb_lint ──────────────────────────────────────────────────────


def test_kb_lint_runs(tmp_project, monkeypatch):
    """kb_lint returns a formatted lint report via mocked run_all_checks."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    # Lazy imports inside kb_lint — patch at source module
    mock_report = {"errors": [], "warnings": []}
    mock_text = "# Lint Report\n\nAll checks passed."
    with (
        patch("kb.lint.runner.run_all_checks", return_value=mock_report) as mock_rac,
        patch("kb.lint.runner.format_report", return_value=mock_text) as mock_fr,
    ):
        result = kb_lint()

    mock_rac.assert_called_once()
    mock_fr.assert_called_once()
    assert "Lint Report" in result
    assert "All checks passed" in result


def test_kb_lint_error_handling(tmp_project, monkeypatch):
    """kb_lint returns an error message when run_all_checks raises."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    # Lazy import — patch at source module
    with patch("kb.lint.runner.run_all_checks", side_effect=RuntimeError("lint crash")):
        result = kb_lint()

    assert "Error" in result
    assert "lint crash" in result


# ── kb_evolve ────────────────────────────────────────────────────


def test_kb_evolve_runs(tmp_project, monkeypatch):
    """kb_evolve returns a formatted evolution report via mocked functions."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    # Lazy imports inside kb_evolve — patch at source module
    with (
        patch(
            "kb.evolve.analyzer.generate_evolution_report",
            return_value={"coverage": {}, "suggestions": []},
        ) as mock_ger,
        patch(
            "kb.evolve.analyzer.format_evolution_report",
            return_value="# Wiki Evolution Report\n\nNo gaps found.",
        ) as mock_fer,
    ):
        result = kb_evolve()

    mock_ger.assert_called_once()
    mock_fer.assert_called_once()
    assert "Evolution Report" in result
    assert "No gaps found" in result


def test_kb_evolve_error_handling(tmp_project, monkeypatch):
    """kb_evolve returns an error message when analysis raises."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    # Lazy import — patch at source module
    with patch(
        "kb.evolve.analyzer.generate_evolution_report",
        side_effect=RuntimeError("evolve crash"),
    ):
        result = kb_evolve()

    assert "Error" in result
    assert "evolve crash" in result
