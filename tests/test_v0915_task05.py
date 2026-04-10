"""Phase 3.96 Task 5 — Graph module fixes."""


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
