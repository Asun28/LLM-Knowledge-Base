"""Regression tests for the lint runner and individual lint checks."""


def test_check_orphan_pages_does_not_mutate_shared_graph(tmp_wiki, create_wiki_page):
    """Regression: Phase 4.5 CRITICAL item 8 (sentinel _index:* nodes leaked into shared_graph)."""
    create_wiki_page(page_id="concepts/a", title="A", content="Body.", wiki_dir=tmp_wiki)
    # Create index.md with a wikilink so the sentinel-node path is exercised
    (tmp_wiki / "index.md").write_text(
        "---\ntitle: Index\n---\n\n[[concepts/a]]\n", encoding="utf-8"
    )
    from kb.graph.builder import build_graph
    from kb.lint.checks import check_orphan_pages

    graph = build_graph(tmp_wiki)
    before_nodes = set(graph.nodes)
    _ = check_orphan_pages(tmp_wiki, graph=graph)
    after_nodes = set(graph.nodes)
    assert before_nodes == after_nodes, f"shared_graph mutated: added {after_nodes - before_nodes}"


def test_check_orphan_pages_does_not_report_index_sentinel(tmp_wiki, create_wiki_page):
    """Regression: Phase 4.5 CRITICAL item 8 (sentinel _index:* must not leak into orphan warnings)."""
    create_wiki_page(page_id="concepts/a", title="A", content="Body.", wiki_dir=tmp_wiki)
    # Create an index.md with a wikilink so sentinel node augments into the graph
    (tmp_wiki / "index.md").write_text(
        "---\ntitle: Index\n---\n\n[[concepts/a]]\n", encoding="utf-8"
    )
    from kb.graph.builder import build_graph
    from kb.lint.checks import check_orphan_pages

    graph = build_graph(tmp_wiki)
    result = check_orphan_pages(tmp_wiki, graph=graph)
    orphan_pages = {issue["page"] for issue in result if issue.get("check") == "orphan_page"}
    assert "_index:index.md" not in orphan_pages, (
        f"Sentinel _index: node leaked into orphan warnings: {orphan_pages}"
    )
