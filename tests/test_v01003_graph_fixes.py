"""Tests for Phase 4 graph/ fixes."""

from __future__ import annotations


def test_graph_stats_uses_precomputed_out_degrees():
    """graph_stats must use precomputed out_degrees dict for orphan detection, not graph.degree(n).

    Verified via: source uses out_degrees dict, and stats returns correct orphan count.
    """
    import inspect

    import networkx as nx

    from kb.graph.builder import graph_stats

    # Verify source code uses out_degrees dict, not graph.degree(n) per-node
    src = inspect.getsource(graph_stats)
    assert "out_degrees" in src, "graph_stats must precompute out_degrees dict"
    assert "graph.degree(n)" not in src, "graph_stats must not call graph.degree(n) per-node"

    # Verify correct orphan count
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
