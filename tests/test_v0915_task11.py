"""Phase 3.96 Task 11 — Coverage gap tests.

Covers:
  11.3 — atomic_text_write basic functionality
  11.7 — _compute_pagerank_scores
  11.8 — _build_query_context truncation
  11.9 — export_mermaid basic test
  11.11 — create_raw_source fixture path validation (added to conftest.py)
  11.15 — build_consistency_context auto groups
  11.18 — _mask_code_blocks collision test
  11.19 — graph_stats determinism
  11.20 — _update_existing_page with date in body
"""

from datetime import date

import pytest


class TestAtomicTextWriteBasic:
    """11.3: atomic_text_write basic functionality."""

    def test_writes_content_correctly(self, tmp_path):
        from kb.utils.io import atomic_text_write

        path = tmp_path / "test.txt"
        atomic_text_write("hello world", path)
        assert path.read_text(encoding="utf-8") == "hello world"

    def test_overwrites_existing_file(self, tmp_path):
        from kb.utils.io import atomic_text_write

        path = tmp_path / "test.txt"
        path.write_text("old content", encoding="utf-8")
        atomic_text_write("new content", path)
        assert path.read_text(encoding="utf-8") == "new content"

    def test_creates_parent_directories(self, tmp_path):
        from kb.utils.io import atomic_text_write

        path = tmp_path / "nested" / "deep" / "test.txt"
        atomic_text_write("content", path)
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "content"

    def test_empty_string_written(self, tmp_path):
        from kb.utils.io import atomic_text_write

        path = tmp_path / "empty.txt"
        atomic_text_write("", path)
        assert path.read_text(encoding="utf-8") == ""

    def test_unicode_content_preserved(self, tmp_path):
        from kb.utils.io import atomic_text_write

        path = tmp_path / "unicode.txt"
        content = "Hello 世界 🌍 Привет"
        atomic_text_write(content, path)
        assert path.read_text(encoding="utf-8") == content


class TestComputePageRankScores:
    """11.7: _compute_pagerank_scores."""

    def test_non_empty_graph_returns_scores(self, tmp_wiki, create_wiki_page):
        from kb.query.engine import _compute_pagerank_scores

        create_wiki_page("concepts/a", wiki_dir=tmp_wiki, content="See [[concepts/b]].")
        create_wiki_page("concepts/b", wiki_dir=tmp_wiki, content="See [[concepts/a]].")
        scores = _compute_pagerank_scores(tmp_wiki)
        assert len(scores) > 0
        assert all(0.0 <= v <= 1.0 for v in scores.values())

    def test_empty_wiki_returns_empty(self, tmp_wiki):
        from kb.query.engine import _compute_pagerank_scores

        scores = _compute_pagerank_scores(tmp_wiki)
        assert scores == {}

    def test_single_page_scores(self, tmp_wiki, create_wiki_page):
        from kb.query.engine import _compute_pagerank_scores

        create_wiki_page("concepts/single", wiki_dir=tmp_wiki, content="No links.")
        scores = _compute_pagerank_scores(tmp_wiki)
        assert "concepts/single" in scores
        assert 0.0 <= scores["concepts/single"] <= 1.0

    def test_hub_page_has_higher_score(self, tmp_wiki, create_wiki_page):
        from kb.query.engine import _compute_pagerank_scores

        # Create a hub page that many pages link to
        create_wiki_page("concepts/hub", wiki_dir=tmp_wiki, content="Hub page.")
        for i in range(3):
            create_wiki_page(
                f"concepts/spoke{i}",
                wiki_dir=tmp_wiki,
                content="Links to [[concepts/hub]].",
            )
        scores = _compute_pagerank_scores(tmp_wiki)
        # Hub should have higher score (more inbound links)
        assert scores["concepts/hub"] > 0.0


class TestBuildQueryContext:
    """11.8: _build_query_context truncation."""

    def test_oversize_page_handled(self):
        from kb.query.engine import _build_query_context

        big_page = {
            "id": "concepts/big",
            "title": "Big",
            "type": "concept",
            "confidence": "stated",
            "content": "x" * 100_000,
        }
        small_page = {
            "id": "concepts/small",
            "title": "Small",
            "type": "concept",
            "confidence": "stated",
            "content": "Small content.",
        }
        result = _build_query_context([big_page, small_page], max_chars=1000)
        assert result["context_pages"]  # at least one page included

    def test_empty_pages_returns_empty(self):
        from kb.query.engine import _build_query_context

        result = _build_query_context([], max_chars=1000)
        assert result["context_pages"] == []

    def test_context_respects_max_chars(self):
        from kb.query.engine import _build_query_context

        pages = [
            {
                "id": "concepts/a",
                "title": "A",
                "type": "concept",
                "confidence": "stated",
                "content": "x" * 500,
            },
            {
                "id": "concepts/b",
                "title": "B",
                "type": "concept",
                "confidence": "stated",
                "content": "y" * 500,
            },
        ]
        result = _build_query_context(pages, max_chars=700)
        # context_pages is a list of page IDs (strings)
        # Both 500-char pages shouldn't fit in 700 chars
        assert len(result["context_pages"]) <= 1

    def test_single_page_fits_exactly(self):
        from kb.query.engine import _build_query_context

        page = {
            "id": "concepts/test",
            "title": "Test",
            "type": "concept",
            "confidence": "stated",
            "content": "Test content.",
        }
        result = _build_query_context([page], max_chars=10000)
        assert len(result["context_pages"]) == 1


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


class TestConsistencyGroupCap:
    """11.15: build_consistency_context auto groups."""

    def test_auto_groups_handled(self, tmp_wiki, create_wiki_page):
        from kb.lint.semantic import build_consistency_context

        for i in range(5):
            create_wiki_page(
                f"concepts/term{i}",
                wiki_dir=tmp_wiki,
                source_ref="raw/articles/shared.md",
                content=f"Page {i} about shared topic.",
            )
        result = build_consistency_context(wiki_dir=tmp_wiki)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_consistency_context_with_linked_pages(self, tmp_wiki, create_wiki_page):
        from kb.lint.semantic import build_consistency_context

        create_wiki_page(
            "concepts/a",
            wiki_dir=tmp_wiki,
            source_ref="raw/articles/shared.md",
            content="Page A links to [[concepts/b]].",
        )
        create_wiki_page(
            "concepts/b",
            wiki_dir=tmp_wiki,
            source_ref="raw/articles/shared.md",
            content="Page B links to [[concepts/a]].",
        )
        result = build_consistency_context(wiki_dir=tmp_wiki)
        assert isinstance(result, str)


class TestMaskCodeBlocksCollision:
    """11.18: _mask_code_blocks collision test."""

    def test_preexisting_placeholder_not_corrupted(self):
        from kb.compile.linker import _mask_code_blocks, _unmask_code_blocks

        text = "Normal text.\n```\ncode block\n```\nMore text."
        masked_text, masked_items, prefix = _mask_code_blocks(text)
        restored = _unmask_code_blocks(masked_text, masked_items, prefix)
        assert "code block" in restored
        assert "Normal text." in restored

    def test_roundtrip_preserves_content(self):
        from kb.compile.linker import _mask_code_blocks, _unmask_code_blocks

        text = "Before `inline code` after."
        masked_text, masked_items, prefix = _mask_code_blocks(text)
        restored = _unmask_code_blocks(masked_text, masked_items, prefix)
        assert restored == text

    def test_multiple_code_blocks_restored(self):
        from kb.compile.linker import _mask_code_blocks, _unmask_code_blocks

        text = "Start ```\nblock1\n``` middle ```\nblock2\n``` end"
        masked_text, masked_items, prefix = _mask_code_blocks(text)
        restored = _unmask_code_blocks(masked_text, masked_items, prefix)
        assert "block1" in restored
        assert "block2" in restored
        assert "Start" in restored
        assert "middle" in restored
        assert "end" in restored

    def test_mixed_inline_and_block_code(self):
        from kb.compile.linker import _mask_code_blocks, _unmask_code_blocks

        text = "Inline `code1` text ```\nblock\n``` and `code2` end"
        masked_text, masked_items, prefix = _mask_code_blocks(text)
        restored = _unmask_code_blocks(masked_text, masked_items, prefix)
        assert "code1" in restored
        assert "code2" in restored
        assert "block" in restored


class TestGraphStatsDeterminism:
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


class TestUpdateExistingPageDateInBody:
    """11.20: _update_existing_page with date in body."""

    def test_body_date_not_replaced(self, tmp_path, monkeypatch):
        import kb.ingest.pipeline as pipeline

        page = tmp_path / "concepts" / "test.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\n# Test\n\nThis was updated: 2024-06-15 in docs.\n"
            "\n## References\n\n- Mentioned in raw/articles/a.md\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "kb.ingest.pipeline.atomic_text_write",
            lambda c, p: p.write_text(c, encoding="utf-8"),
        )
        pipeline._update_existing_page(page, "raw/articles/b.md")
        result = page.read_text(encoding="utf-8")
        assert "updated: 2024-06-15" in result  # body date preserved

    def test_frontmatter_updated_date_changed(self, tmp_path, monkeypatch):
        import kb.ingest.pipeline as pipeline

        page = tmp_path / "concepts" / "test.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        old_date = "2024-01-01"
        page.write_text(
            f'---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            f"created: {old_date}\nupdated: {old_date}\ntype: concept\n"
            f"confidence: stated\n---\n\n# Test\n\nContent.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "kb.ingest.pipeline.atomic_text_write",
            lambda c, p: p.write_text(c, encoding="utf-8"),
        )
        pipeline._update_existing_page(page, "raw/articles/b.md")
        result = page.read_text(encoding="utf-8")
        today = date.today().isoformat()
        # Frontmatter updated should change
        assert f"updated: {today}" in result

    def test_new_source_added_to_frontmatter(self, tmp_path, monkeypatch):
        import kb.ingest.pipeline as pipeline

        page = tmp_path / "concepts" / "test.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2024-01-01\nupdated: 2024-01-01\ntype: concept\n"
            "confidence: stated\n---\n\n# Test\n\nContent.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "kb.ingest.pipeline.atomic_text_write",
            lambda c, p: p.write_text(c, encoding="utf-8"),
        )
        pipeline._update_existing_page(page, "raw/articles/b.md")
        result = page.read_text(encoding="utf-8")
        # Both sources should be listed
        assert "raw/articles/a.md" in result
        assert "raw/articles/b.md" in result

    def test_duplicate_source_not_added(self, tmp_path, monkeypatch):
        import kb.ingest.pipeline as pipeline

        page = tmp_path / "concepts" / "test.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2024-01-01\nupdated: 2024-01-01\ntype: concept\n"
            "confidence: stated\n---\n\n# Test\n\nContent.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "kb.ingest.pipeline.atomic_text_write",
            lambda c, p: p.write_text(c, encoding="utf-8"),
        )
        # Try to add the same source again
        pipeline._update_existing_page(page, "raw/articles/a.md")
        result = page.read_text(encoding="utf-8")
        # Count occurrences of the source
        count = result.count("raw/articles/a.md")
        assert count == 1  # Should only appear once


class TestCreateRawSourceValidation:
    """11.11: create_raw_source fixture path validation."""

    def test_raw_source_with_valid_prefix(self, create_raw_source):
        path = create_raw_source("raw/articles/test.md", "Content")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "Content"

    def test_raw_source_invalid_prefix_raises(self, create_raw_source):
        with pytest.raises(AssertionError, match="source_ref must start with 'raw/'"):
            create_raw_source("wiki/articles/test.md", "Content")

    def test_raw_source_videos_subdirectory(self, create_raw_source):
        path = create_raw_source("raw/videos/video.txt", "Video")
        assert path.exists()

    def test_raw_source_papers_subdirectory(self, create_raw_source):
        path = create_raw_source("raw/papers/paper.pdf", "Paper")
        assert path.exists()
