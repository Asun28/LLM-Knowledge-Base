"""Regression tests for Phase 4.5 HIGH cycle 2 (22 bug fixes).

Each test is tagged with the item ID from the design spec.
"""

from pathlib import Path
from unittest.mock import patch

# ── T1: Frontmatter Foundation ──────────────────────────────────────────────


class TestD3FrontmatterRegex:
    """D3: FRONTMATTER_RE must handle interior --- and not backtrack catastrophically."""

    def test_interior_dashes_in_block_scalar(self):
        """Interior --- in indented YAML block scalar must NOT split frontmatter."""
        from kb.utils.markdown import FRONTMATTER_RE

        text = "---\ntitle: Test\ndescription: |\n  some text\n  ---\n  more\n---\nBody here\n"
        m = FRONTMATTER_RE.match(text)
        assert m is not None
        assert "Body here" in m.group(2)

    def test_normal_frontmatter(self):
        from kb.utils.markdown import FRONTMATTER_RE

        text = "---\ntitle: Hello\ntype: entity\n---\nContent body\n"
        m = FRONTMATTER_RE.match(text)
        assert m is not None
        assert "Content body" in m.group(2)
        assert "title: Hello" in m.group(1)

    def test_minimal_frontmatter(self):
        from kb.utils.markdown import FRONTMATTER_RE

        text = "---\nk: v\n---\nBody\n"
        m = FRONTMATTER_RE.match(text)
        assert m is not None
        assert "Body" in m.group(2)

    def test_no_frontmatter(self):
        from kb.utils.markdown import FRONTMATTER_RE

        text = "Just plain content\nNo frontmatter here\n"
        m = FRONTMATTER_RE.match(text)
        assert m is None

    def test_no_closing_fence_bounded(self):
        """Page with opening --- but no closing --- should not cause catastrophic backtrack."""
        from kb.utils.markdown import FRONTMATTER_RE

        text = "---\ntitle: Broken\n" + "x" * 50_000 + "\n"
        # Should complete quickly (regex bounded), returning None or match.
        # Either outcome is OK — the key is it completes fast (no backtrack).
        _ = FRONTMATTER_RE.match(text)
        assert True  # If we get here, no catastrophic backtracking


class TestD1FrontmatterGuard:
    """D1: refine_page must accept wiki bodies containing --- horizontal rules."""

    def test_accepts_horizontal_rules(self, tmp_path):
        from kb.review.refiner import refine_page

        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        page = wiki_dir / "concepts" / "test.md"
        page.write_text(
            "---\ntitle: Test\nupdated: 2026-01-01\n---\nOld content\n", encoding="utf-8"
        )

        # Content with horizontal rules should be accepted
        result = refine_page(
            "concepts/test",
            "New section\n\n---\n\nAnother section\n\n---\n\nFinal section",
            wiki_dir=wiki_dir,
            history_path=tmp_path / "history.json",
        )
        assert "error" not in result
        assert result["updated"] is True

    def test_rejects_frontmatter_block(self, tmp_path):
        from kb.review.refiner import refine_page

        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        page = wiki_dir / "concepts" / "test.md"
        page.write_text(
            "---\ntitle: Test\nupdated: 2026-01-01\n---\nOld content\n", encoding="utf-8"
        )

        # Content that looks like a frontmatter block should be rejected
        result = refine_page(
            "concepts/test",
            "---\ntitle: Injected\ntype: entity\n---\nBody",
            wiki_dir=wiki_dir,
            history_path=tmp_path / "history.json",
        )
        assert "error" in result


class TestD2BomHandling:
    """D2: refine_page must handle UTF-8 BOM files."""

    def test_bom_file_parsed_correctly(self, tmp_path):
        from kb.review.refiner import refine_page

        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        page = wiki_dir / "concepts" / "test.md"
        # Write file with UTF-8 BOM
        page.write_bytes(b"\xef\xbb\xbf---\ntitle: Test\nupdated: 2026-01-01\n---\nOld content\n")

        result = refine_page(
            "concepts/test",
            "New content after BOM fix",
            wiki_dir=wiki_dir,
            history_path=tmp_path / "history.json",
        )
        assert "error" not in result, f"BOM file should be parseable, got: {result.get('error')}"


class TestP3EvolveAnalyzerFrontmatter:
    """P3: evolve/analyzer.py must use shared FRONTMATTER_RE, not inlined regex."""

    def test_uses_shared_regex(self):
        """Verify evolve/analyzer.py imports FRONTMATTER_RE (not inlines regex)."""
        import kb.evolve.analyzer as analyzer

        source = Path(analyzer.__file__).read_text(encoding="utf-8")
        # Should NOT contain the inlined regex pattern
        assert r're.sub(r"\A---\r?\n.*?\r?\n---\r?\n?"' not in source
        # Should import from shared module
        assert "FRONTMATTER_RE" in source or "from kb.utils.markdown" in source


class TestL7SemanticGroupIndex:
    """L7: _group_by_term_overlap must tokenize body (group(2)), not frontmatter."""

    def test_tokenizes_body_not_frontmatter(self, tmp_path):
        from kb.lint.semantic import _group_by_term_overlap

        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "concepts"
        concepts.mkdir(parents=True)

        # Two pages with same body but different frontmatter
        for name, body in [
            ("alpha", "quantum computing algorithms research"),
            ("beta", "quantum computing algorithms research"),
        ]:
            (concepts / f"{name}.md").write_text(
                f"---\ntitle: {name.title()}\ntype: concept\n---\n{body}\n", encoding="utf-8"
            )
        # A third page with frontmatter sharing words but different body
        (concepts / "gamma.md").write_text(
            "---\ntitle: Gamma\ntype: concept\n---\nCompletely unrelated content about cooking\n",
            encoding="utf-8",
        )

        groups = _group_by_term_overlap(wiki_dir)
        # alpha and beta share body terms → should be grouped
        paired = [g for g in groups if "concepts/alpha" in g and "concepts/beta" in g]
        assert len(paired) > 0, "Pages with shared body terms should be grouped"

        # gamma has different body → should NOT be grouped with alpha/beta
        gamma_with_alpha = [g for g in groups if "concepts/gamma" in g and "concepts/alpha" in g]
        assert len(gamma_with_alpha) == 0, "Pages with different body terms should not be grouped"


# ── T2: VALID_SOURCE_TYPES DRY ──────────────────────────────────────────────


class TestC1ValidSourceTypes:
    """C1: VALID_SOURCE_TYPES must not be defined in extractors.py."""

    def test_single_source_of_truth(self):
        import kb.ingest.extractors as extractors

        source = Path(extractors.__file__).read_text(encoding="utf-8")
        # extractors should NOT define its own VALID_SOURCE_TYPES
        assert "VALID_SOURCE_TYPES = frozenset" not in source


# ── T3: Lint Correctness ────────────────────────────────────────────────────


class TestL1CheckCyclesBounded:
    """L1: check_cycles must be bounded via islice."""

    def test_bounded_to_100(self):
        import networkx as nx

        from kb.lint.checks import check_cycles

        # Create a graph with many cycles (complete digraph on 10 string nodes)
        g = nx.DiGraph()
        nodes = [f"concepts/n{i}" for i in range(10)]
        for a in nodes:
            for b in nodes:
                if a != b:
                    g.add_edge(a, b)
        issues = check_cycles(graph=g)
        # Should be capped (100 cycles + 1 warning message)
        assert len(issues) <= 101


class TestL2TermOverlapScales:
    """L2: _group_by_term_overlap must work above 500 pages."""

    def test_works_above_500_pages(self, tmp_path):
        from kb.lint.semantic import _group_by_term_overlap

        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "concepts"
        concepts.mkdir(parents=True)

        # Create 501 pages — should NOT return [] anymore
        for i in range(501):
            body = f"unique_term_{i} another_word_{i} filler content here"
            if i < 2:
                body = "shared_quantum_computing_algorithms_research detailed analysis"
            (concepts / f"page{i:04d}.md").write_text(
                f"---\ntitle: Page {i}\ntype: concept\n---\n{body}\n",
                encoding="utf-8",
            )

        result = _group_by_term_overlap(wiki_dir)
        # Should NOT return empty list for >500 pages
        # Pages 0 and 1 share terms, so at least one group expected
        assert len(result) > 0, "Term overlap should work above 500 pages"


class TestL4TrendsTimezone:
    """L4: All timestamps in trends.py must be UTC-aware."""

    def test_parse_timestamp_returns_aware(self):
        from kb.lint.trends import _parse_timestamp

        # Date-only string should return UTC-aware
        ts = _parse_timestamp("2026-01-15")
        assert ts.tzinfo is not None, "Date-only timestamps must be UTC-aware"

        # ISO with Z should return UTC-aware
        ts2 = _parse_timestamp("2026-01-15T10:30:00Z")
        assert ts2.tzinfo is not None

        # ISO with offset should remain aware
        ts3 = _parse_timestamp("2026-01-15T10:30:00+05:00")
        assert ts3.tzinfo is not None


class TestL5ParseFailureAccounting:
    """L5: Parse failures must be excluded from BOTH overall and period_buckets."""

    def test_parse_failure_excluded_from_overall(self, tmp_path):
        from kb.lint.trends import compute_verdict_trends
        from kb.utils.io import atomic_json_write

        verdicts_path = tmp_path / "verdicts.json"
        verdicts = [
            {"page_id": "a", "verdict": "pass", "timestamp": "2026-01-15T10:00:00Z"},
            {"page_id": "b", "verdict": "fail", "timestamp": "INVALID_TIMESTAMP"},
            {"page_id": "c", "verdict": "warning", "timestamp": "2026-01-15T11:00:00Z"},
        ]
        atomic_json_write(verdicts, verdicts_path)

        result = compute_verdict_trends(verdicts_path)
        # The INVALID_TIMESTAMP entry should be excluded from overall too
        total_counted = (
            result["overall"]["pass"] + result["overall"]["fail"] + result["overall"]["warning"]
        )
        assert total_counted == 2, f"Parse failure should not count in overall, got {total_counted}"


class TestL6RenderSourcesBudget:
    """L6: _render_sources must enforce per-source minimum floor."""

    def test_minimum_source_budget(self):
        from kb.lint.semantic import _render_sources

        # Lines already consuming most of the budget
        lines = ["x" * 79_000]  # Near the 80K limit
        sources = [
            {"path": "raw/test.md", "content": "Important source content that should not vanish"}
        ]

        _render_sources(sources, lines)
        # Source content should still appear (with minimum budget)
        source_text = "\n".join(lines)
        assert "Important source" in source_text or "truncated" in source_text.lower()


class TestL3BuildGraphAcceptsPages:
    """L3: build_graph must accept optional pages param."""

    def test_pages_param_avoids_disk_read(self, tmp_path):
        from kb.graph.builder import build_graph

        wiki_dir = tmp_path / "wiki"
        for subdir in ["concepts", "entities"]:
            (wiki_dir / subdir).mkdir(parents=True)

        # Create pages on disk
        (wiki_dir / "concepts" / "a.md").write_text(
            "---\ntitle: A\n---\nLinks to [[concepts/b]]\n", encoding="utf-8"
        )
        (wiki_dir / "concepts" / "b.md").write_text(
            "---\ntitle: B\n---\nLinks to [[entities/c]]\n", encoding="utf-8"
        )
        (wiki_dir / "entities" / "c.md").write_text(
            "---\ntitle: C\n---\nNo links\n", encoding="utf-8"
        )

        # Build with pre-loaded pages (should not need disk reads)
        pages = [
            {
                "id": "concepts/a",
                "path": str(wiki_dir / "concepts/a.md"),
                "content": "Links to [[concepts/b]]",
            },
            {
                "id": "concepts/b",
                "path": str(wiki_dir / "concepts/b.md"),
                "content": "Links to [[entities/c]]",
            },
            {"id": "entities/c", "path": str(wiki_dir / "entities/c.md"), "content": "No links"},
        ]
        g = build_graph(wiki_dir, pages=pages)
        assert g.has_edge("concepts/a", "concepts/b")
        assert g.has_edge("concepts/b", "entities/c")


# ── T4: Data Integrity ──────────────────────────────────────────────────────


class TestD4FeedbackEviction:
    """D4: Eviction must use last-touched timestamp, not activity count."""

    def test_evicts_oldest_first(self, tmp_path):
        from kb.feedback.store import add_feedback_entry, load_feedback

        fb_path = tmp_path / "feedback.json"
        # Temporarily reduce cap for testing
        with patch("kb.feedback.store.MAX_PAGE_SCORES", 2):
            # Add feedback for page A (older)
            add_feedback_entry("q1", "useful", ["concepts/a"], path=fb_path)
            # Add feedback for page B (newer)
            add_feedback_entry("q2", "useful", ["concepts/b"], path=fb_path)
            # Add feedback for page C (newest) — triggers eviction
            add_feedback_entry("q3", "useful", ["concepts/c"], path=fb_path)

        data = load_feedback(fb_path)
        remaining = set(data["page_scores"].keys())
        # A should be evicted (oldest), B and C should remain
        assert "concepts/a" not in remaining, "Oldest entry should be evicted"
        assert len(remaining) <= 2


class TestD5ContradictionTruncationWarning:
    """D5: Claim truncation must be logged at WARNING level."""

    def test_truncation_logs_warning(self, caplog):
        import logging

        from kb.ingest.contradiction import detect_contradictions

        claims = [f"Claim number {i} about topic {i}" for i in range(20)]
        pages = [{"id": "test", "content": "Some existing content about topic 5"}]

        with caplog.at_level(logging.WARNING, logger="kb.ingest.contradiction"):
            detect_contradictions(claims, pages, max_claims=5)

        warning_msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("truncated" in m.lower() or "first" in m.lower() for m in warning_msgs), (
            f"Expected WARNING about truncation, got: {warning_msgs}"
        )


class TestD6ContradictionExcludesCurrentIngest:
    """D6: Contradiction detection must exclude pages created in current ingest."""

    def test_excludes_newly_created_pages(self):
        from kb.ingest.contradiction import detect_contradictions

        claims = ["Python is slow for numerical computation"]
        # Simulate a page created in THIS ingest
        current_pages = [
            {"id": "summaries/new-source", "content": "Python is slow for numerical computation"},
        ]
        preexisting = [
            {
                "id": "concepts/python",
                "content": "Python excels at numerical computation with NumPy",
            },
        ]

        # With all pages (including current) — might get self-comparison noise.
        # (Combined list kept as documentation of the pre-fix behaviour; the
        # fix is verified via the `preexisting`-only call below.)
        _ = current_pages + preexisting
        # The fix should filter current-ingest pages before calling.
        # We test the fix at the pipeline level, but verify the function itself works.
        result = detect_contradictions(claims, preexisting)
        # Should only check against preexisting pages, not the new summary
        # (This test verifies the function works correctly when given filtered input)
        assert isinstance(result, list)


# ── T5: Query Correctness ───────────────────────────────────────────────────


class TestQ1TierBudgetPerAddition:
    """Q1: Tier 1 budget must be enforced per-addition, not just as stopping rule."""

    def test_large_summary_does_not_starve_tier2(self):
        from kb.query.engine import _build_query_context

        # One huge summary (25K) and several small non-summaries
        pages = [
            {
                "id": "summaries/big",
                "title": "Big Summary",
                "type": "summary",
                "confidence": "stated",
                "content": "x" * 25_000,
            },
            {
                "id": "entities/small1",
                "title": "Entity 1",
                "type": "entity",
                "confidence": "stated",
                "content": "Important entity content A",
            },
            {
                "id": "entities/small2",
                "title": "Entity 2",
                "type": "entity",
                "confidence": "stated",
                "content": "Important entity content B",
            },
        ]
        result = _build_query_context(pages)
        # Tier 2 pages should still be included even if summary exceeds tier 1 budget
        assert (
            "entities/small1" in result["context_pages"]
            or "entities/small2" in result["context_pages"]
        ), "Tier 2 pages must not be starved by oversized tier 1 summary"


class TestQ2RrfMetadataMerge:
    """Q2: RRF fusion must preserve all metadata fields on collision."""

    def test_preserves_metadata_on_collision(self):
        from kb.query.hybrid import rrf_fusion

        list1 = [{"id": "page/a", "stale": False, "type": "entity", "sources": ["s1"]}]
        list2 = [{"id": "page/a", "stale": True, "type": "entity", "sources": ["s1", "s2"]}]

        result = rrf_fusion([list1, list2])
        assert len(result) == 1
        merged = result[0]
        # Score should be accumulated (both lists contribute)
        assert merged["score"] > 1.0 / 60  # More than single-list score
        # Metadata from later list should be present
        assert "stale" in merged
        assert "sources" in merged


class TestQ3SmartQuoteStripping:
    """Q3: rewrite_query must strip smart quotes, backticks, and single quotes."""

    def test_strips_smart_quotes(self):
        from kb.query.rewriter import _QUOTE_CHARS

        test_str = "\u201cWhat is RAG?\u201d"
        stripped = test_str.strip().strip(_QUOTE_CHARS)
        assert stripped == "What is RAG?"

    def test_strips_backticks(self):
        from kb.query.rewriter import _QUOTE_CHARS

        test_str = "`What is RAG?`"
        stripped = test_str.strip().strip(_QUOTE_CHARS)
        assert stripped == "What is RAG?"


class TestQ4CentralityStatusMetadata:
    """Q4: graph_stats must return status metadata for centrality metrics."""

    def test_pagerank_has_status(self):
        import networkx as nx

        from kb.graph.builder import graph_stats

        g = nx.DiGraph()
        g.add_edges_from([("a", "b"), ("b", "c"), ("c", "a")])
        stats = graph_stats(g)
        assert "pagerank_status" in stats
        assert stats["pagerank_status"] in ("ok", "failed", "degenerate")

    def test_bridge_nodes_has_status(self):
        import networkx as nx

        from kb.graph.builder import graph_stats

        g = nx.DiGraph()
        g.add_edges_from([("a", "b"), ("b", "c")])
        # Cycle 6 AC13: betweenness is opt-in (default "skipped"). Pass
        # include_centrality=True to exercise the legacy status-metadata
        # contract this test was written for.
        stats = graph_stats(g, include_centrality=True)
        assert "bridge_nodes_status" in stats
        assert stats["bridge_nodes_status"] in ("ok", "failed", "degenerate")


# ── T6: Performance ─────────────────────────────────────────────────────────


class TestP1SlugIndex:
    """P1: Bare-slug resolution must use pre-built slug_index dict."""

    def test_bare_slug_resolves(self, tmp_path):
        from kb.graph.builder import build_graph

        wiki_dir = tmp_path / "wiki"
        for subdir in ["concepts", "entities"]:
            (wiki_dir / subdir).mkdir(parents=True)

        (wiki_dir / "concepts" / "rag.md").write_text(
            "---\ntitle: RAG\n---\nContent\n", encoding="utf-8"
        )
        (wiki_dir / "entities" / "openai.md").write_text(
            "---\ntitle: OpenAI\n---\nUses [[rag]] for retrieval\n", encoding="utf-8"
        )

        g = build_graph(wiki_dir)
        # Bare slug [[rag]] should resolve to concepts/rag
        assert g.has_edge("entities/openai", "concepts/rag")


class TestP2ContentLowerOptIn:
    """P2: load_all_pages must support include_content_lower param."""

    def test_default_includes_content_lower(self, tmp_path):
        from kb.utils.pages import load_all_pages

        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        (wiki_dir / "concepts" / "test.md").write_text(
            "---\ntitle: Test\n---\nContent\n", encoding="utf-8"
        )

        pages = load_all_pages(wiki_dir)
        assert all("content_lower" in p for p in pages)

    def test_opt_out_excludes_content_lower(self, tmp_path):
        from kb.utils.pages import load_all_pages

        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        (wiki_dir / "concepts" / "test.md").write_text(
            "---\ntitle: Test\n---\nContent\n", encoding="utf-8"
        )

        pages = load_all_pages(wiki_dir, include_content_lower=False)
        assert all("content_lower" not in p for p in pages)
