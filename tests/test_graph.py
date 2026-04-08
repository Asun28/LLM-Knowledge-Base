"""Tests for the graph builder and visualization."""

from pathlib import Path

from kb.graph.builder import build_graph, graph_stats, page_id, scan_wiki_pages


def _create_wiki_page(path: Path, title: str, content: str, page_type: str = "concept") -> None:
    """Helper to create a wiki page with frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = f"""---
title: "{title}"
source:
  - raw/articles/test.md
created: 2026-04-06
updated: 2026-04-06
type: {page_type}
confidence: stated
---

"""
    path.write_text(frontmatter + content, encoding="utf-8")


def test_scan_wiki_pages(tmp_wiki):
    """scan_wiki_pages finds markdown files in wiki subdirs."""
    _create_wiki_page(tmp_wiki / "concepts" / "rag.md", "RAG", "Content about RAG")
    _create_wiki_page(tmp_wiki / "entities" / "openai.md", "OpenAI", "Content about OpenAI")
    pages = scan_wiki_pages(tmp_wiki)
    assert len(pages) == 2
    names = [p.stem for p in pages]
    assert "rag" in names
    assert "openai" in names


def test_scan_wiki_pages_empty(tmp_wiki):
    """scan_wiki_pages returns empty list for empty wiki."""
    pages = scan_wiki_pages(tmp_wiki)
    assert pages == []


def test_page_id(tmp_wiki):
    """page_id returns relative path without .md extension."""
    page = tmp_wiki / "concepts" / "rag.md"
    assert page_id(page, tmp_wiki) == "concepts/rag"


def test_build_graph_nodes(tmp_wiki):
    """build_graph creates nodes for all wiki pages."""
    _create_wiki_page(tmp_wiki / "concepts" / "rag.md", "RAG", "About RAG")
    _create_wiki_page(tmp_wiki / "concepts" / "llm.md", "LLM", "About LLMs")
    _create_wiki_page(tmp_wiki / "entities" / "openai.md", "OpenAI", "About OpenAI")
    graph = build_graph(tmp_wiki)
    assert graph.number_of_nodes() == 3
    assert "concepts/rag" in graph.nodes()
    assert "concepts/llm" in graph.nodes()
    assert "entities/openai" in graph.nodes()


def test_build_graph_edges(tmp_wiki):
    """build_graph creates edges from wikilinks."""
    _create_wiki_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "RAG uses [[concepts/llm]] and is developed by [[entities/openai]].",
    )
    _create_wiki_page(tmp_wiki / "concepts" / "llm.md", "LLM", "LLMs power [[concepts/rag]].")
    _create_wiki_page(tmp_wiki / "entities" / "openai.md", "OpenAI", "OpenAI builds LLMs.")
    graph = build_graph(tmp_wiki)
    assert graph.number_of_edges() == 3
    assert graph.has_edge("concepts/rag", "concepts/llm")
    assert graph.has_edge("concepts/rag", "entities/openai")
    assert graph.has_edge("concepts/llm", "concepts/rag")


def test_build_graph_empty(tmp_wiki):
    """build_graph returns empty graph for empty wiki."""
    graph = build_graph(tmp_wiki)
    assert graph.number_of_nodes() == 0
    assert graph.number_of_edges() == 0


def test_graph_stats(tmp_wiki):
    """graph_stats computes correct statistics."""
    _create_wiki_page(
        tmp_wiki / "summaries" / "article1.md",
        "Article 1",
        "Links to [[concepts/rag]] and [[entities/openai]].",
        page_type="summary",
    )
    _create_wiki_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "RAG is discussed in [[summaries/article1]].",
    )
    _create_wiki_page(
        tmp_wiki / "entities" / "openai.md",
        "OpenAI",
        "OpenAI content, no outgoing links to wiki pages.",
    )
    graph = build_graph(tmp_wiki)
    stats = graph_stats(graph)
    assert stats["nodes"] == 3
    assert stats["edges"] == 3  # article1->rag, article1->openai, rag->article1
    assert stats["components"] == 1  # All connected
    assert isinstance(stats["most_linked"], list)


def test_graph_stats_orphan_detection(tmp_wiki):
    """graph_stats identifies orphan pages (pages with links out but none in)."""
    _create_wiki_page(
        tmp_wiki / "summaries" / "orphan.md",
        "Orphan Summary",
        "This links to [[concepts/rag]] but nobody links here.",
        page_type="summary",
    )
    _create_wiki_page(tmp_wiki / "concepts" / "rag.md", "RAG", "RAG content, no links.")
    graph = build_graph(tmp_wiki)
    stats = graph_stats(graph)
    assert "summaries/orphan" in stats["no_inbound"]
