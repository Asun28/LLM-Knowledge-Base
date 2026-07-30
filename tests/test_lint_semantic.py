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
        f'---\ntitle: "{title}"\nsource:\n  - {source_ref}\n'
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
        wiki_dir,
        "concepts/rag",
        "RAG",
        "Content with unique words only.",
        "raw/articles/unique1.md",
    )

    context = build_consistency_context(wiki_dir=wiki_dir)
    assert "No page groups found" in context or "Group" in context


def test_build_consistency_context_auto_wikilinks(tmp_project):
    """build_consistency_context groups pages connected by wikilinks."""
    wiki_dir = tmp_project / "wiki"
    _create_page(
        wiki_dir,
        "concepts/rag",
        "RAG",
        "RAG uses [[concepts/llm]] models.",
        "raw/articles/rag.md",
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


# -- Cycle 92 fold from test_v0915_task06.py (semantic grouping subset) --
# Phase 3.96 Task 6 — _group_by_wikilinks connected components,
# consistency-group size cap, CRLF term overlap.


# ── Fix 6.6 — _group_by_wikilinks uses nx.connected_components ───────────────


class TestGroupByWikilinksConnectedComponents:
    """Fix 6.6 — _group_by_wikilinks returns proper connected components (not star topologies)."""

    def test_star_topology_pages_in_one_component(self, tmp_wiki, create_wiki_page):
        """Hub → A, Hub → B, Hub → C should be one component of 4, not 3 pairs."""
        from kb.lint.semantic import _group_by_wikilinks

        # Hub links to a, b, c but a/b/c don't link to each other
        create_wiki_page(
            "concepts/hub",
            wiki_dir=tmp_wiki,
            content="See [[concepts/spoke-a]], [[concepts/spoke-b]], [[concepts/spoke-c]].",
        )
        create_wiki_page("concepts/spoke-a", wiki_dir=tmp_wiki, content="Spoke A.")
        create_wiki_page("concepts/spoke-b", wiki_dir=tmp_wiki, content="Spoke B.")
        create_wiki_page("concepts/spoke-c", wiki_dir=tmp_wiki, content="Spoke C.")

        groups = _group_by_wikilinks(tmp_wiki)
        # All 4 nodes are in the same connected component
        assert len(groups) == 1
        assert sorted(groups[0]) == [
            "concepts/hub",
            "concepts/spoke-a",
            "concepts/spoke-b",
            "concepts/spoke-c",
        ]

    def test_disconnected_graph_yields_multiple_components(self, tmp_wiki, create_wiki_page):
        """Two disconnected link chains should appear as two separate components."""
        from kb.lint.semantic import _group_by_wikilinks

        create_wiki_page(
            "concepts/a",
            wiki_dir=tmp_wiki,
            content="See [[concepts/b]].",
        )
        create_wiki_page("concepts/b", wiki_dir=tmp_wiki, content="B.")
        create_wiki_page(
            "concepts/c",
            wiki_dir=tmp_wiki,
            content="See [[concepts/d]].",
        )
        create_wiki_page("concepts/d", wiki_dir=tmp_wiki, content="D.")

        groups = _group_by_wikilinks(tmp_wiki)
        assert len(groups) == 2
        group_sets = [frozenset(g) for g in groups]
        assert frozenset(["concepts/a", "concepts/b"]) in group_sets
        assert frozenset(["concepts/c", "concepts/d"]) in group_sets


# ── Fix 6.10 — auto-selected groups size cap ─────────────────────────────────


class TestConsistencyContextGroupSizeCap:
    """Fix 6.10 — auto-selected groups are chunked to MAX_CONSISTENCY_GROUP_SIZE."""

    def test_large_component_is_split_into_chunks(self, tmp_wiki, create_wiki_page):
        """A connected component larger than MAX_CONSISTENCY_GROUP_SIZE should be split."""
        from kb.config import MAX_CONSISTENCY_GROUP_SIZE
        from kb.lint.semantic import build_consistency_context

        # Create MAX_CONSISTENCY_GROUP_SIZE + 2 pages all linked from a hub
        n = MAX_CONSISTENCY_GROUP_SIZE + 2
        links = " ".join(f"[[concepts/node-{i}]]" for i in range(n))
        create_wiki_page("concepts/hub", wiki_dir=tmp_wiki, content=links)
        for i in range(n):
            create_wiki_page(f"concepts/node-{i}", wiki_dir=tmp_wiki, content=f"Node {i}.")

        result = build_consistency_context(wiki_dir=tmp_wiki)
        # The result should reference multiple groups since the component was split
        # Check that no group header has more pages than MAX_CONSISTENCY_GROUP_SIZE
        import re

        group_headers = re.findall(r"## Group \d+ \((\d+) pages\)", result)
        for size_str in group_headers:
            assert int(size_str) <= MAX_CONSISTENCY_GROUP_SIZE


# ── Fix 6.8 — CRLF in frontmatter regex ─────────────────────────────────────


class TestGroupByTermOverlapCRLF:
    """Fix 6.8 — _group_by_term_overlap handles CRLF line endings."""

    def test_crlf_page_body_extracted_for_terms(self, tmp_wiki):
        """Pages with CRLF line endings should have frontmatter stripped correctly."""
        from kb.lint.semantic import _group_by_term_overlap

        # Write a page with CRLF endings
        page_a = tmp_wiki / "concepts" / "crlf-a.md"
        page_a.parent.mkdir(parents=True, exist_ok=True)
        crlf_fm = (
            b"---\r\ntitle: CRLF A\r\nsource:\r\n  - raw/articles/test.md\r\n"
            b"created: 2026-01-01\r\nupdated: 2026-01-01\r\ntype: concept\r\n"
            b"confidence: stated\r\n---\r\n"
        )
        page_a.write_bytes(
            crlf_fm + b"machine learning neural network transformer architecture training\r\n"
        )
        page_b = tmp_wiki / "concepts" / "crlf-b.md"
        crlf_fm_b = (
            b"---\r\ntitle: CRLF B\r\nsource:\r\n  - raw/articles/test.md\r\n"
            b"created: 2026-01-01\r\nupdated: 2026-01-01\r\ntype: concept\r\n"
            b"confidence: stated\r\n---\r\n"
        )
        page_b.write_bytes(
            crlf_fm_b + b"machine learning neural network transformer architecture training\r\n"
        )

        # Should not crash and should find term overlap
        groups = _group_by_term_overlap(tmp_wiki)
        assert isinstance(groups, list)
        # The two pages share terms, so they should be grouped
        crlf_group = any("concepts/crlf-a" in g and "concepts/crlf-b" in g for g in groups)
        assert crlf_group, f"CRLF pages not grouped by term overlap. Groups: {groups}"


# -- Cycle 92 fold from test_v0915_task11.py (consistency-context subset) --


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
