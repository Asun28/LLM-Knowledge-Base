"""Tests for the graph builder and visualization."""

import logging
from datetime import date
from pathlib import Path
from unittest.mock import patch

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


# ── Phase 4 graph fixes (cycle 55 fold) ───────────────────────────────


def test_graph_stats_avoids_per_node_degree_calls(monkeypatch):
    """graph_stats must use bulk in_degree() / out_degree() — never per-node calls.

    Folded from test_v01003_graph_fixes (cycle 55) Q1 design upgrade. The
    source's `test_graph_stats_uses_precomputed_out_degrees` had two halves:
    (a) `inspect.getsource(graph_stats); assert "out_degrees" in src` —
    vacuous per C11-L1, and (b) behavioral assertion on the orphans alias.

    Per Step-5 Q1 decision (b), the design specified a behavioral SPY
    upgrade: replace the source-grep with a spy on `InDegreeView.__call__`
    and `OutDegreeView.__call__` that fires only when nbunch != None
    (per-node call path). The orphan-count half lands as a separate test
    (`test_graph_stats_orphan_detection_with_isolated_node` below).

    Reverting graph_stats from `dict(graph.in_degree())` to a per-node loop
    `{n: graph.in_degree(n) for n in graph.nodes()}` would fire the spy
    with nbunch=specific-node N times — failing this test. The current
    bulk implementation invokes `__call__` only with nbunch=None (or via
    iteration of the view), so per-node counts stay at 0.

    Cycle-55 R1 DeepSeek + Sonnet flagged the original fold as a
    design-deviance MAJOR (Q1 spy upgrade not implemented). Cycle-55 R2
    Codex flagged the original spy's try/finally restoration as a
    leak-risk if assignment raised mid-statement; this version uses
    pytest's `monkeypatch` fixture which guarantees automatic restoration
    even on test-collection abort or KeyboardInterrupt.
    """
    import networkx as nx
    from networkx.classes.reportviews import InDegreeView, OutDegreeView

    from kb.graph.builder import graph_stats

    g = nx.DiGraph()
    for i in range(20):
        g.add_node(f"n{i}")
    g.add_edge("n0", "n1")
    g.add_edge("n1", "n2")

    in_call_orig = InDegreeView.__call__
    out_call_orig = OutDegreeView.__call__
    counts = {"in_per_node": 0, "out_per_node": 0}

    def in_spy(self, nbunch=None, weight=None):
        if nbunch is not None:
            counts["in_per_node"] += 1
        return in_call_orig(self, nbunch, weight)

    def out_spy(self, nbunch=None, weight=None):
        if nbunch is not None:
            counts["out_per_node"] += 1
        return out_call_orig(self, nbunch, weight)

    monkeypatch.setattr(InDegreeView, "__call__", in_spy)
    monkeypatch.setattr(OutDegreeView, "__call__", out_spy)

    graph_stats(g)

    assert counts["in_per_node"] == 0, (
        f"graph_stats called in_degree(n) per-node {counts['in_per_node']}x; "
        "use dict(g.in_degree()) instead"
    )
    assert counts["out_per_node"] == 0, (
        f"graph_stats called out_degree(n) per-node {counts['out_per_node']}x; "
        "use dict(g.out_degree()) instead"
    )


def test_graph_stats_orphan_detection_with_isolated_node():
    """graph_stats reports a degree-zero node in the 'orphans' alias.

    Folded from test_v01003_graph_fixes (cycle 55) — orphan-count half of
    the source's `test_graph_stats_uses_precomputed_out_degrees`. The
    `inspect.getsource` grep half was dropped per C11-L1; behavioral
    upgrade lives in `test_graph_stats_avoids_per_node_degree_calls`
    above. This test pairs with that one to cover both intents of the
    original (no per-node degree calls + isolated-node classification).

    Existing `test_graph_stats_orphan_detection` at line 109 covers the
    `no_inbound` field via build_graph + wiki pages — DIFFERENT field,
    DIFFERENT graph-construction approach; both tests have value.
    """
    import networkx as nx

    from kb.graph.builder import graph_stats

    g = nx.DiGraph()
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    g.add_node("d")  # orphan: no in or out edges

    stats = graph_stats(g)
    assert stats["orphans"] == ["d"], f"Expected ['d'] orphan, got {stats['orphans']}"


def test_export_mermaid_deterministic_edge_order(tmp_wiki):
    """Two exports of the same graph must produce byte-identical output."""
    from kb.graph.builder import build_graph
    from kb.graph.export import export_mermaid

    (tmp_wiki / "concepts").mkdir(parents=True, exist_ok=True)
    for name in ("alpha", "beta", "gamma"):
        (tmp_wiki / "concepts" / f"{name}.md").write_text(
            f"---\ntitle: {name}\ntype: concept\nconfidence: stated\n---\n"
            f"Links: [[concepts/alpha]] [[concepts/beta]] [[concepts/gamma]]\n",
            encoding="utf-8",
        )
    g = build_graph(tmp_wiki)
    a = export_mermaid(g, wiki_dir=tmp_wiki, max_nodes=10)
    b = export_mermaid(g, wiki_dir=tmp_wiki, max_nodes=10)
    assert a == b


def test_graph_init_does_not_export_scan_wiki_pages():
    import kb.graph as _g

    assert "scan_wiki_pages" not in _g.__all__


# ═══════════════════════════════════════════════════════════════════════
# Cycle 78 freeze-and-fold — moved verbatim from tests/test_v0916_task05.py
# (graph/builder.py parts). Only deviation: fold-site networkx import.
# ═══════════════════════════════════════════════════════════════════════

import networkx as nx  # noqa: E402  — fold-site import (cycle 78)


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


# Cycle 80 freeze-and-fold — moved verbatim from tests/test_v0915_task05.py
# (Phase 3.96 Task 5 — Graph module fixes).
class TestBuildGraphNoSelfLoops:
    def test_self_link_not_added(self, tmp_wiki, create_wiki_page):
        from kb.graph.builder import build_graph

        create_wiki_page(
            "concepts/rag",
            wiki_dir=tmp_wiki,
            content="# RAG\n\nSee [[concepts/rag]] for more.",
        )
        graph = build_graph(tmp_wiki)
        assert not graph.has_edge("concepts/rag", "concepts/rag")

    def test_normal_link_still_added(self, tmp_wiki, create_wiki_page):
        from kb.graph.builder import build_graph

        create_wiki_page(
            "concepts/rag",
            wiki_dir=tmp_wiki,
            content="# RAG\n\nSee [[concepts/transformer]] for more.",
        )
        create_wiki_page(
            "concepts/transformer",
            wiki_dir=tmp_wiki,
            content="# Transformer",
        )
        graph = build_graph(tmp_wiki)
        assert graph.has_edge("concepts/rag", "concepts/transformer")

    def test_self_link_in_frontmatter_not_added(self, tmp_wiki, create_wiki_page):
        """Wikilinks that appear in YAML frontmatter values should not create edges."""
        from kb.graph.builder import build_graph

        # page with [[concepts/other]] in frontmatter (e.g., a source: value with brackets)
        # and the same self-ref in body
        page_path = tmp_wiki / "concepts" / "rag.md"
        page_path.write_text(
            "---\ntitle: RAG\nsource:\n  - raw/articles/test.md\n---\n"
            "# RAG\n\nSee [[concepts/rag]] for more.\n",
            encoding="utf-8",
        )
        graph = build_graph(tmp_wiki)
        assert not graph.has_edge("concepts/rag", "concepts/rag")


class TestGraphStatsDeterminism:
    def test_betweenness_centrality_deterministic(self, tmp_wiki, create_wiki_page):
        from kb.graph.builder import build_graph, graph_stats

        for i in range(5):
            links = " ".join(f"[[concepts/page{j}]]" for j in range(5) if j != i)
            create_wiki_page(f"concepts/page{i}", wiki_dir=tmp_wiki, content=links)
        graph = build_graph(tmp_wiki)
        stats1 = graph_stats(graph)
        stats2 = graph_stats(graph)
        assert stats1["bridge_nodes"] == stats2["bridge_nodes"]

    def test_bridge_nodes_empty_on_empty_graph(self, tmp_wiki):
        from kb.graph.builder import build_graph, graph_stats

        graph = build_graph(tmp_wiki)
        stats = graph_stats(graph)
        assert stats["bridge_nodes"] == []


class TestGraphStatsMostLinked:
    def test_zero_in_degree_excluded(self, tmp_wiki, create_wiki_page):
        """most_linked should not include pages with no inbound links."""
        from kb.graph.builder import build_graph, graph_stats

        # page0 links to page1 — page0 has 0 in-degree, page1 has 1
        create_wiki_page("concepts/page0", wiki_dir=tmp_wiki, content="[[concepts/page1]]")
        create_wiki_page("concepts/page1", wiki_dir=tmp_wiki, content="No outbound links.")
        graph = build_graph(tmp_wiki)
        stats = graph_stats(graph)
        most_linked_ids = [n for n, _ in stats["most_linked"]]
        assert "concepts/page0" not in most_linked_ids
        assert "concepts/page1" in most_linked_ids

    def test_most_linked_all_isolated_is_empty(self, tmp_wiki, create_wiki_page):
        """If no page has any inbound links, most_linked should be empty."""
        from kb.graph.builder import build_graph, graph_stats

        create_wiki_page("concepts/standalone", wiki_dir=tmp_wiki, content="No links here.")
        graph = build_graph(tmp_wiki)
        stats = graph_stats(graph)
        assert stats["most_linked"] == []


class TestPageRankExceptionHandling:
    def test_graph_stats_returns_empty_pagerank_on_error(self, tmp_wiki):
        """graph_stats handles NetworkX errors gracefully."""
        import networkx as nx

        from kb.graph.builder import graph_stats

        # Empty graph — pagerank on an empty graph can raise NetworkXError in some versions
        graph = nx.DiGraph()
        stats = graph_stats(graph)
        # Should not raise; pagerank is either [] or a valid list
        assert isinstance(stats["pagerank"], list)


class TestFrontmatterNotScannedForLinks:
    def test_wikilink_in_frontmatter_not_added_as_edge(self, tmp_wiki):
        """Wikilinks appearing only in YAML frontmatter should NOT create edges."""
        from kb.graph.builder import build_graph

        # Manually create two pages; put [[concepts/other]] only in frontmatter source value
        (tmp_wiki / "concepts").mkdir(exist_ok=True)
        (tmp_wiki / "concepts" / "rag.md").write_text(
            "---\ntitle: RAG\nsource:\n  - '[[concepts/other]]'\n---\n# RAG\n",
            encoding="utf-8",
        )
        (tmp_wiki / "concepts" / "other.md").write_text(
            "---\ntitle: Other\nsource:\n  - raw/articles/test.md\n---\n# Other\n",
            encoding="utf-8",
        )
        graph = build_graph(tmp_wiki)
        # The frontmatter wikilink must NOT be treated as a real link
        assert not graph.has_edge("concepts/rag", "concepts/other")


class TestSanitizeLabel:
    def test_semicolon_removed(self):
        """Fix 5.6: semicolons in Mermaid labels should be stripped."""
        from kb.graph.export import _sanitize_label

        result = _sanitize_label("Title; With Semicolon")
        assert ";" not in result
        assert "Title" in result

    def test_standard_chars_removed(self):
        from kb.graph.export import _sanitize_label

        result = _sanitize_label('Label "quotes" [brackets] {braces}')
        assert '"' not in result
        assert "[" not in result
        assert "{" not in result

    def test_clean_label_unchanged(self):
        from kb.graph.export import _sanitize_label

        assert _sanitize_label("Clean Label") == "Clean Label"


class TestSafeNodeId:
    def test_dot_replaced(self):
        """Fix 5.7: dots in page IDs must be replaced to avoid Mermaid parse errors."""
        from kb.graph.export import _safe_node_id

        result = _safe_node_id("concepts/v0.9")
        assert "." not in result
        assert "_" in result

    def test_slash_replaced(self):
        from kb.graph.export import _safe_node_id

        result = _safe_node_id("concepts/rag")
        assert "/" not in result
        assert result == "concepts_rag"

    def test_collision_deduplication(self):
        from kb.graph.export import _safe_node_id

        seen: set[str] = set()
        id1 = _safe_node_id("concepts/rag", seen)
        id2 = _safe_node_id("concepts/rag", seen)
        assert id1 != id2


# -- Cycle 92 fold from test_v0915_task11.py (graph export/builder subset) --


class TestExportMermaid:
    """11.9: export_mermaid basic test."""

    def test_basic_mermaid_output(self, tmp_wiki, create_wiki_page):
        from kb.graph.export import export_mermaid

        create_wiki_page("concepts/a", wiki_dir=tmp_wiki, content="See [[concepts/b]].")
        create_wiki_page("concepts/b", wiki_dir=tmp_wiki, content="About B.")
        result = export_mermaid(tmp_wiki)
        assert result.startswith("graph LR")

    def test_empty_wiki_mermaid(self, tmp_wiki):
        from kb.graph.export import export_mermaid

        result = export_mermaid(tmp_wiki)
        assert "graph LR" in result

    def test_mermaid_contains_pages(self, tmp_wiki, create_wiki_page):
        from kb.graph.export import export_mermaid

        create_wiki_page("concepts/alice", wiki_dir=tmp_wiki, content="Link to [[concepts/bob]].")
        create_wiki_page("concepts/bob", wiki_dir=tmp_wiki, content="Link to [[concepts/charlie]].")
        create_wiki_page("concepts/charlie", wiki_dir=tmp_wiki, content="Standalone.")
        result = export_mermaid(tmp_wiki)
        # Should contain the graph syntax and some node references
        assert "graph LR" in result

    def test_mermaid_max_nodes_cap(self, tmp_wiki, create_wiki_page):
        from kb.graph.export import export_mermaid

        # Create more than 30 pages
        for i in range(40):
            create_wiki_page(
                f"concepts/page{i}",
                wiki_dir=tmp_wiki,
                content=f"Page {i}",
            )
        result = export_mermaid(tmp_wiki, max_nodes=10)
        # Should still be valid mermaid
        assert "graph LR" in result


# Renamed from TestGraphStatsDeterminism (collision with the class of the same
# name already in this receiver) — origin suffix _t11 per cycle-92 fold rules.
class TestGraphStatsDeterminism_t11:
    """11.19: graph_stats determinism."""

    def test_betweenness_centrality_deterministic(self, tmp_wiki, create_wiki_page):
        from kb.graph.builder import build_graph, graph_stats

        for i in range(5):
            links = " ".join(f"[[concepts/page{j}]]" for j in range(5) if j != i)
            create_wiki_page(f"concepts/page{i}", wiki_dir=tmp_wiki, content=links)
        graph = build_graph(tmp_wiki)
        stats1 = graph_stats(graph)
        stats2 = graph_stats(graph)
        assert stats1["bridge_nodes"] == stats2["bridge_nodes"]

    def test_stats_returns_consistent_keys(self, tmp_wiki, create_wiki_page):
        from kb.graph.builder import build_graph, graph_stats

        create_wiki_page("concepts/a", wiki_dir=tmp_wiki, content="[[concepts/b]]")
        create_wiki_page("concepts/b", wiki_dir=tmp_wiki, content="[[concepts/a]]")
        graph = build_graph(tmp_wiki)
        stats = graph_stats(graph)
        # Check for expected keys
        assert isinstance(stats, dict)

    def test_empty_graph_stats(self, tmp_wiki):
        from kb.graph.builder import build_graph, graph_stats

        graph = build_graph(tmp_wiki)
        stats = graph_stats(graph)
        assert isinstance(stats, dict)


# -- Cycle 93 fold from test_v0912_phase393.py (graph export subset) --


class TestGraphExportFixes:
    """graph/export.py fixes."""

    def test_sanitize_label_strips_newlines(self):
        from kb.graph.export import _sanitize_label

        result = _sanitize_label("Line 1\nLine 2")
        assert "\n" not in result, f"Newline not stripped: {result!r}"

    def test_sanitize_label_strips_backticks(self):
        from kb.graph.export import _sanitize_label

        result = _sanitize_label("`code term`")
        assert "`" not in result, f"Backtick not stripped: {result!r}"

    def test_export_mermaid_empty_wiki(self, tmp_wiki):
        from kb.graph.export import export_mermaid

        result = export_mermaid(wiki_dir=tmp_wiki)
        assert result.startswith("graph LR")

    def test_export_mermaid_with_pages(self, tmp_wiki, create_wiki_page):
        from kb.graph.export import export_mermaid

        create_wiki_page(page_id="concepts/rag", title="RAG", wiki_dir=tmp_wiki)
        result = export_mermaid(wiki_dir=tmp_wiki)
        assert "graph LR" in result
        assert "concepts" in result


# -- Cycle 93 fold from test_phase4_audit_compile.py (graph builder subset) --


def test_bare_slug_wikilink_creates_graph_edge(tmp_wiki):
    """Bare-slug wikilinks [[foo]] must produce graph edges to entities/foo."""
    from kb.graph.builder import build_graph

    # Entity page: entities/foo
    (tmp_wiki / "entities" / "foo.md").write_text(
        "---\ntitle: Foo\ntype: entity\nconfidence: stated\n---\ncontent\n"
    )
    # Concept page linking to [[foo]] (bare slug, no subdir/)
    (tmp_wiki / "concepts" / "bar.md").write_text(
        "---\ntitle: Bar\ntype: concept\nconfidence: stated\n---\n[[foo]]\n"
    )

    graph = build_graph(wiki_dir=tmp_wiki)
    assert graph.has_edge("concepts/bar", "entities/foo"), (
        "Bare-slug [[foo]] from concepts/bar did not produce an edge to entities/foo"
    )


# -- Cycle 93 fold from test_phase4_audit_observability.py (pagerank logging subset) --


def test_pagerank_failure_logs_warning(caplog):
    """PageRank convergence failure must emit a warning with the graph size."""
    import networkx as nx

    from kb.graph.builder import graph_stats

    g = nx.DiGraph()
    g.add_edges_from([("a", "b"), ("b", "a"), ("c", "a")])

    with patch("networkx.pagerank", side_effect=nx.PowerIterationFailedConvergence(100)):
        with caplog.at_level(logging.WARNING, logger="kb.graph.builder"):
            stats = graph_stats(g)

    assert stats["pagerank"] == []
    warning_texts = " ".join(r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)
    assert (
        "pagerank" in warning_texts.lower()
        or "converge" in warning_texts.lower()
        or "failed" in warning_texts.lower()
    )


# -- Cycle 93 fold from test_v0913_phase394.py (graph stats + export) --


class TestGraphStatsBetweennessException:
    """graph/builder.py graph_stats: betweenness_centrality failure is caught."""

    def test_betweenness_exception_does_not_propagate(self, monkeypatch):
        """A failure in betweenness_centrality must be caught and return empty bridge_nodes."""
        import networkx as nx

        from kb.graph.builder import graph_stats

        def failing_bc(graph, **kw):
            raise RuntimeError("betweenness boom")

        monkeypatch.setattr(nx, "betweenness_centrality", failing_bc)

        g = nx.DiGraph()
        g.add_edge("a", "b")
        stats = graph_stats(g)
        assert stats["bridge_nodes"] == [], (
            f"Expected empty bridge_nodes, got {stats['bridge_nodes']}"
        )


class TestGraphStatsOrphansKeyRenamed:
    """graph/builder.py graph_stats: 'orphans' key renamed to 'no_inbound'."""

    def test_no_inbound_key_present(self):
        """graph_stats must return 'no_inbound' key (not 'orphans')."""
        import networkx as nx

        from kb.graph.builder import graph_stats

        g = nx.DiGraph()
        g.add_edge("a", "b")
        g.add_node("c")  # isolated
        stats = graph_stats(g)
        assert "no_inbound" in stats, f"'no_inbound' key missing from stats: {list(stats.keys())}"


class TestMermaidSanitizeLabel:
    """graph/export.py _sanitize_label: parentheses stripped."""

    def test_parentheses_stripped_from_label(self):
        """_sanitize_label must remove '(' and ')' from page titles."""
        from kb.graph.export import _sanitize_label

        result = _sanitize_label("GPT-4 (OpenAI)")
        assert "(" not in result and ")" not in result, f"Parens not stripped: {result!r}"


# -- Cycle 93 fold from test_v0914_phase395.py (graph builder) --


class TestBuildGraphNodeIdCasing:
    """build_graph must normalize node IDs to lowercase."""

    def test_uppercase_filename_lowercased(self, tmp_wiki):
        # Create a page with uppercase in filename
        page_path = tmp_wiki / "entities" / "OpenAI.md"
        page_path.write_text(
            '---\ntitle: "OpenAI"\nsource:\n  - "raw/articles/test.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: entity\n"
            "confidence: stated\n---\n\nContent.\n",
            encoding="utf-8",
        )

        from kb.graph.builder import build_graph

        graph = build_graph(wiki_dir=tmp_wiki)
        node_ids = list(graph.nodes())
        for nid in node_ids:
            assert nid == nid.lower(), f"Node ID not lowercased: {nid}"


class TestGraphPageIdConsolidated:
    """graph/builder.page_id should delegate to utils/pages._page_id."""

    def test_consistent_with_utils(self, tmp_wiki):
        page_path = tmp_wiki / "concepts" / "test-page.md"
        page_path.write_text("---\ntitle: Test\n---\n", encoding="utf-8")

        from kb.graph.builder import page_id as graph_page_id
        from kb.utils.pages import _page_id as utils_page_id

        assert graph_page_id(page_path, tmp_wiki) == utils_page_id(page_path, tmp_wiki)


# -- Cycle 94 fold from test_v070.py (graph pagerank / bridge nodes) --


# ── 1. Graph: PageRank and Centrality ────────────────────────────


def test_graph_stats_includes_pagerank(tmp_wiki, create_wiki_page):
    """graph_stats returns pagerank key."""
    create_wiki_page("concepts/a", wiki_dir=tmp_wiki, content="See [[concepts/b]]")
    create_wiki_page("concepts/b", wiki_dir=tmp_wiki, content="See [[concepts/c]]")
    create_wiki_page("concepts/c", wiki_dir=tmp_wiki, content="See [[concepts/a]]")
    from kb.graph.builder import build_graph, graph_stats

    g = build_graph(tmp_wiki)
    stats = graph_stats(g)
    assert "pagerank" in stats
    assert len(stats["pagerank"]) > 0


def test_graph_stats_includes_bridge_nodes(tmp_wiki, create_wiki_page):
    """graph_stats returns bridge_nodes key."""
    create_wiki_page("concepts/a", wiki_dir=tmp_wiki, content="See [[concepts/b]]")
    create_wiki_page("concepts/b", wiki_dir=tmp_wiki, content="See [[concepts/c]]")
    create_wiki_page("concepts/c", wiki_dir=tmp_wiki, content="")
    from kb.graph.builder import build_graph, graph_stats

    g = build_graph(tmp_wiki)
    stats = graph_stats(g)
    assert "bridge_nodes" in stats


def test_graph_stats_bridge_nodes_filters_zero(tmp_wiki, create_wiki_page):
    """Bridge nodes with 0 centrality are filtered out."""
    # Two isolated pages -- no edges -- all centrality 0
    create_wiki_page("concepts/a", wiki_dir=tmp_wiki, content="No links")
    create_wiki_page("concepts/b", wiki_dir=tmp_wiki, content="No links")
    from kb.graph.builder import build_graph, graph_stats

    g = build_graph(tmp_wiki)
    stats = graph_stats(g)
    assert stats["bridge_nodes"] == []


def test_graph_stats_empty_graph():
    """graph_stats handles empty graph."""
    from kb.graph.builder import graph_stats

    g = nx.DiGraph()
    stats = graph_stats(g)
    assert stats["pagerank"] == []
    assert stats["bridge_nodes"] == []


# -- Cycle 94 fold from test_v090.py (graph edges use normalized wikilink targets) --


def test_graph_edges_match_normalized_links(tmp_wiki, create_wiki_page):
    """Graph builder creates edges using normalized wikilink targets."""
    from kb.graph.builder import build_graph

    create_wiki_page("concepts/rag", wiki_dir=tmp_wiki, content="See [[concepts/llm]]")
    create_wiki_page("concepts/llm", wiki_dir=tmp_wiki, content="An LLM concept.")

    graph = build_graph(tmp_wiki)
    assert graph.has_edge("concepts/rag", "concepts/llm")


# -- Cycle 94 fold from test_v099_phase39.py (Mermaid graph export) --


def _make_wiki_page(wiki_dir, subdir, slug, title, content, source_ref="raw/articles/test.md"):
    """Helper to create a wiki page with proper frontmatter."""
    today = date.today().isoformat()
    page_dir = wiki_dir / subdir
    page_dir.mkdir(parents=True, exist_ok=True)
    page_path = page_dir / f"{slug}.md"
    text = (
        f'---\ntitle: "{title}"\nsource:\n  - "{source_ref}"\n'
        f"created: {today}\nupdated: {today}\ntype: concept\nconfidence: stated\n---\n\n"
        f"{content}\n"
    )
    page_path.write_text(text, encoding="utf-8")
    return page_path


# ── Task 5: Mermaid graph export ─────────────────────────────


class TestMermaidGraphExport:
    """Test Mermaid diagram generation from wiki graph."""

    def test_empty_graph_returns_empty_mermaid(self, tmp_path):
        """Empty wiki produces minimal Mermaid diagram."""
        wiki_dir = tmp_path / "wiki"
        for sub in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
            (wiki_dir / sub).mkdir(parents=True)

        from kb.graph.export import export_mermaid

        result = export_mermaid(wiki_dir=wiki_dir)
        assert result.startswith("graph LR")

    def test_basic_graph_produces_valid_mermaid(self, tmp_path):
        """Simple graph produces valid Mermaid with nodes and edges."""
        wiki_dir = tmp_path / "wiki"
        _make_wiki_page(
            wiki_dir,
            "concepts",
            "rag",
            "RAG",
            "RAG combines [[concepts/retrieval]] with generation.",
        )
        _make_wiki_page(
            wiki_dir, "concepts", "retrieval", "Retrieval", "Retrieval is used by [[concepts/rag]]."
        )

        from kb.graph.export import export_mermaid

        result = export_mermaid(wiki_dir=wiki_dir)
        assert "graph LR" in result
        assert "concepts_rag" in result  # sanitized node ID
        assert "concepts_retrieval" in result
        assert "-->" in result

    def test_auto_prune_large_graph(self, tmp_path):
        """Graphs with >50 nodes are pruned to max_nodes most-connected."""
        wiki_dir = tmp_path / "wiki"
        # Create 60 pages
        for i in range(60):
            links = f"[[concepts/page-{(i + 1) % 60}]]"
            _make_wiki_page(
                wiki_dir,
                "concepts",
                f"page-{i}",
                f"Page {i}",
                f"Content for page {i}. {links}",
                source_ref=f"raw/articles/p{i}.md",
            )

        from kb.graph.export import export_mermaid

        result = export_mermaid(wiki_dir=wiki_dir, max_nodes=30)
        # Should be pruned — count node definitions
        node_lines = [line for line in result.split("\n") if '["' in line or '("' in line]
        assert len(node_lines) <= 30

    def test_node_labels_use_page_titles(self, tmp_path):
        """Node labels use page titles from frontmatter."""
        wiki_dir = tmp_path / "wiki"
        _make_wiki_page(wiki_dir, "entities", "openai", "OpenAI", "OpenAI makes GPT models.")

        from kb.graph.export import export_mermaid

        result = export_mermaid(wiki_dir=wiki_dir)
        assert "entities_openai" in result
        assert "OpenAI" in result  # title used as label

    def test_mcp_tool_returns_mermaid(self):
        """kb_graph_viz MCP tool returns Mermaid string."""
        from kb.mcp.health import kb_graph_viz

        result = kb_graph_viz()
        assert isinstance(result, str)
        assert "graph" in result.lower() or "no pages" in result.lower()
