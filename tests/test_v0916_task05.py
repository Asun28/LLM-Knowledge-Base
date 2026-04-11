"""Phase 3.97 Task 05 — Query / Graph / Citations fixes."""

import re
from pathlib import Path

import networkx as nx
import pytest


class TestPageRankEdgeFreeGraph:
    """_compute_pagerank_scores must return {} for graphs with no edges."""

    def test_edge_free_graph_returns_empty(self, tmp_wiki):
        """A wiki with pages but no wikilinks should get empty pagerank."""
        # Create two pages with no wikilinks between them
        for name in ("page-a", "page-b"):
            page = tmp_wiki / "concepts" / f"{name}.md"
            page.write_text(
                f'---\ntitle: "{name}"\nsource: []\ncreated: 2026-01-01\n'
                "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
                f"Content for {name}.\n",
                encoding="utf-8",
            )

        from kb.query.engine import _compute_pagerank_scores

        scores = _compute_pagerank_scores(tmp_wiki)
        assert scores == {}


class TestPageRankOSErrorCaught:
    """_compute_pagerank_scores must catch OSError from build_graph."""

    def test_os_error_returns_empty(self):
        from unittest.mock import patch

        from kb.query.engine import _compute_pagerank_scores

        with patch("kb.query.engine.build_graph", side_effect=OSError("disk error")):
            result = _compute_pagerank_scores()
            assert result == {}


class TestExtractCitationsTypeOverride:
    """extract_citations must override cite_type based on path prefix."""

    def test_source_keyword_with_raw_path(self):
        from kb.query.citations import extract_citations

        text = "According to [source: raw/papers/test.pdf] the model works."
        cites = extract_citations(text)
        assert len(cites) == 1
        assert cites[0]["type"] == "raw"  # overridden from "wiki"
        assert cites[0]["path"] == "raw/papers/test.pdf"

    def test_source_keyword_with_wiki_path(self):
        from kb.query.citations import extract_citations

        text = "According to [source: concepts/rag] the model works."
        cites = extract_citations(text)
        assert len(cites) == 1
        assert cites[0]["type"] == "wiki"  # stays as wiki


class TestExtractCitationsModuleLevel:
    """_CITATION_PATTERN should be a module-level compiled regex."""

    def test_pattern_is_module_level(self):
        from kb.query import citations

        assert hasattr(citations, "_CITATION_PATTERN")
        assert isinstance(citations._CITATION_PATTERN, re.Pattern)


class TestGraphStatsNarrowException:
    """graph_stats betweenness_centrality should use narrow exception."""

    def test_graph_stats_on_empty_graph(self):
        from kb.graph.builder import graph_stats

        g = nx.DiGraph()
        stats = graph_stats(g)
        assert stats["nodes"] == 0
        assert stats["bridge_nodes"] == []


class TestGraphStatsPageRankValueError:
    """graph_stats PageRank should catch ValueError."""

    def test_pagerank_value_error_caught(self):
        from unittest.mock import patch

        from kb.graph.builder import graph_stats

        g = nx.DiGraph()
        g.add_node("a")

        with patch("kb.graph.builder.nx.pagerank", side_effect=ValueError("test")):
            stats = graph_stats(g)
            assert stats["pagerank"] == []


class TestTokenizeDeadBranchRemoved:
    """tokenize regex should not have dead second branch."""

    def test_two_char_tokens_still_work(self):
        from kb.query.bm25 import tokenize

        result = tokenize("AI is great")
        assert "ai" in result  # 2-char token should still match
