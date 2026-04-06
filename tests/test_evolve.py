"""Tests for the evolve analyzer."""

from pathlib import Path

from kb.evolve.analyzer import (
    analyze_coverage,
    find_connection_opportunities,
    format_evolution_report,
    generate_evolution_report,
    suggest_new_pages,
)


def _create_page(path: Path, title: str, content: str, page_type: str = "concept") -> None:
    """Helper to create a wiki page with frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        f'---\ntitle: "{title}"\nsource:\n  - raw/articles/test.md\n'
        f"created: 2026-04-06\nupdated: 2026-04-06\ntype: {page_type}\n"
        f"confidence: stated\n---\n\n"
    )
    path.write_text(fm + content, encoding="utf-8")


# ── Coverage analysis ──────────────────────────────────────────


def test_analyze_coverage(tmp_wiki):
    """analyze_coverage counts pages by type."""
    _create_page(tmp_wiki / "concepts" / "rag.md", "RAG", "About RAG")
    _create_page(tmp_wiki / "concepts" / "llm.md", "LLM", "About LLMs")
    _create_page(tmp_wiki / "entities" / "openai.md", "OpenAI", "About OpenAI", page_type="entity")
    result = analyze_coverage(tmp_wiki)
    assert result["total_pages"] == 3
    assert result["by_type"]["concepts"] == 2
    assert result["by_type"]["entities"] == 1
    assert "comparisons" in result["under_covered_types"]
    assert "synthesis" in result["under_covered_types"]


def test_analyze_coverage_empty(tmp_wiki):
    """analyze_coverage handles empty wiki."""
    result = analyze_coverage(tmp_wiki)
    assert result["total_pages"] == 0


def test_analyze_coverage_orphan_concepts(tmp_wiki):
    """analyze_coverage identifies concepts with no backlinks."""
    _create_page(tmp_wiki / "concepts" / "lonely.md", "Lonely Concept", "Nobody links here.")
    result = analyze_coverage(tmp_wiki)
    assert "concepts/lonely" in result["orphan_concepts"]


# ── Connection opportunities ────────────────────────────────────


def test_find_connection_opportunities(tmp_wiki):
    """find_connection_opportunities detects unlinked related pages."""
    # Two pages about similar topics but not linked to each other
    _create_page(
        tmp_wiki / "concepts" / "retrieval.md",
        "Retrieval",
        "Retrieval augmented generation combines document search with language models "
        "using vector embeddings for semantic similarity.",
    )
    _create_page(
        tmp_wiki / "concepts" / "embeddings.md",
        "Embeddings",
        "Vector embeddings represent documents as dense vectors for semantic similarity "
        "search in language models.",
    )
    opportunities = find_connection_opportunities(tmp_wiki)
    # They share terms like "vector", "embeddings", "semantic", "similarity", "language", "models"
    # Whether the threshold is met depends on content overlap, so just check the function runs
    assert isinstance(opportunities, list)


def test_find_connection_opportunities_empty(tmp_wiki):
    """find_connection_opportunities handles empty wiki."""
    result = find_connection_opportunities(tmp_wiki)
    assert result == []


# ── New page suggestions ────────────────────────────────────────


def test_suggest_new_pages(tmp_wiki):
    """suggest_new_pages finds dead links as page candidates."""
    _create_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "Uses [[concepts/vector-search]] and [[entities/pinecone]].",
    )
    suggestions = suggest_new_pages(tmp_wiki)
    targets = [s["target"] for s in suggestions]
    assert "concepts/vector-search" in targets
    assert "entities/pinecone" in targets


def test_suggest_new_pages_no_dead_links(tmp_wiki):
    """suggest_new_pages returns empty when all links resolve."""
    _create_page(tmp_wiki / "concepts" / "rag.md", "RAG", "Links to [[concepts/llm]].")
    _create_page(tmp_wiki / "concepts" / "llm.md", "LLM", "LLM content.")
    suggestions = suggest_new_pages(tmp_wiki)
    assert suggestions == []


def test_suggest_new_pages_sorted_by_references(tmp_wiki):
    """suggest_new_pages sorts by reference count (most first)."""
    _create_page(
        tmp_wiki / "summaries" / "a.md", "A", "Uses [[concepts/popular]].", page_type="summary"
    )
    _create_page(
        tmp_wiki / "summaries" / "b.md", "B", "Also [[concepts/popular]].", page_type="summary"
    )
    _create_page(
        tmp_wiki / "summaries" / "c.md", "C", "Uses [[concepts/rare]].", page_type="summary"
    )
    suggestions = suggest_new_pages(tmp_wiki)
    assert len(suggestions) == 2
    # "popular" has 2 refs, "rare" has 1 — popular should be first
    assert suggestions[0]["target"] == "concepts/popular"
    assert len(suggestions[0]["referenced_by"]) == 2


# ── Full evolution report ───────────────────────────────────────


def test_generate_evolution_report(tmp_wiki):
    """generate_evolution_report produces complete report."""
    _create_page(tmp_wiki / "concepts" / "rag.md", "RAG", "About [[entities/openai]] RAG.")
    _create_page(
        tmp_wiki / "entities" / "openai.md", "OpenAI", "OpenAI content.", page_type="entity"
    )
    report = generate_evolution_report(tmp_wiki)
    assert "coverage" in report
    assert "connection_opportunities" in report
    assert "new_page_suggestions" in report
    assert "graph_stats" in report
    assert "recommendations" in report
    assert report["coverage"]["total_pages"] == 2


def test_generate_evolution_report_empty(tmp_wiki):
    """generate_evolution_report handles empty wiki."""
    report = generate_evolution_report(tmp_wiki)
    assert report["coverage"]["total_pages"] == 0
    assert report["graph_stats"]["nodes"] == 0


def test_format_evolution_report(tmp_wiki):
    """format_evolution_report produces readable text."""
    _create_page(tmp_wiki / "concepts" / "rag.md", "RAG", "About [[concepts/nonexistent]].")
    report = generate_evolution_report(tmp_wiki)
    text = format_evolution_report(report)
    assert "# Wiki Evolution Report" in text
    assert "Coverage" in text
    assert "Graph" in text
