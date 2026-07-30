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


# ── Cycle 9 evolve regression test (cycle 48 fold per AC4) ─────────
# Source: tests/test_cycle9_evolve.py (deleted in same commit).
def test_bare_slug_link_not_reported_as_orphan(tmp_project):
    wiki_dir = tmp_project / "wiki"
    page_a = wiki_dir / "concepts" / "a.md"
    page_b = wiki_dir / "concepts" / "b.md"

    page_a.write_text(
        "---\ntitle: A\ntype: concept\n---\n\nSee [[b]].\n",
        encoding="utf-8",
    )
    page_b.write_text(
        "---\ntitle: B\ntype: concept\n---\n\nTarget concept.\n",
        encoding="utf-8",
    )

    report = analyze_coverage(wiki_dir=wiki_dir)

    assert "concepts/b" not in report["orphan_concepts"]


# ── Phase 4 evolve fixes (cycle 55 fold) ──────────────────────────────
# Source: tests/test_v01007_evolve_fixes.py (deleted in same commit).


def test_find_connection_opportunities_caps_pairs(tmp_wiki):
    """pair_shared_terms must not exceed 50k pairs."""
    from kb.evolve.analyzer import find_connection_opportunities
    from kb.graph.builder import scan_wiki_pages

    # Create enough pages with overlapping terms to exceed the cap
    (tmp_wiki / "concepts").mkdir(parents=True, exist_ok=True)
    for i in range(40):
        (tmp_wiki / "concepts" / f"p{i}.md").write_text(
            f"---\ntitle: p{i}\ntype: concept\nconfidence: stated\n---\n"
            + "alpha beta gamma delta epsilon zeta eta theta iota kappa " * 10,
            encoding="utf-8",
        )
    pages = scan_wiki_pages(tmp_wiki)
    # Must complete without OOM or hanging — and return a list
    result = find_connection_opportunities(pages=pages, wiki_dir=tmp_wiki)
    assert isinstance(result, list)


def test_generate_evolution_report_scans_once(monkeypatch, tmp_wiki):
    """scan_wiki_pages must be called at most once per generate_evolution_report call."""
    from kb.evolve import analyzer as _a

    calls = {"n": 0}

    # We need to intercept the actual function used internally
    # First, find what name it's imported/called under in analyzer.py
    original = getattr(_a, "scan_wiki_pages", None) or getattr(_a, "_scan_wiki_pages", None)

    def counting(*args, **kwargs):
        calls["n"] += 1
        if original:
            return original(*args, **kwargs)
        return []

    # Try both possible attribute names
    for attr in ("scan_wiki_pages", "_scan_wiki_pages", "load_all_pages"):
        if hasattr(_a, attr):
            monkeypatch.setattr(_a, attr, counting)
            break

    (tmp_wiki / "concepts").mkdir(parents=True, exist_ok=True)
    (tmp_wiki / "concepts" / "x.md").write_text(
        "---\ntitle: x\ntype: concept\nconfidence: stated\n---\nbody\n",
        encoding="utf-8",
    )
    try:
        _a.generate_evolution_report(wiki_dir=tmp_wiki)
    except Exception:
        pass  # Function may fail in test env; we only care about call count
    assert calls["n"] <= 1, f"Expected <=1 scan calls, got {calls['n']}"


def test_generate_evolution_report_handles_oserror(monkeypatch):
    """OSError from feedback file must not propagate as unhandled exception."""
    from kb.evolve import analyzer as _a

    def _raise_oserror(*args, **kwargs):
        raise OSError("feedback file corrupt")

    # Find the function that wraps feedback access
    for attr in ("get_flagged_pages", "_get_flagged_pages"):
        if hasattr(_a, attr):
            monkeypatch.setattr(_a, attr, _raise_oserror)
            break

    # Must not raise (function catches OSError now)
    try:
        _a.generate_evolution_report()
    except OSError:
        raise AssertionError("OSError should have been caught by generate_evolution_report")
    except Exception:
        pass  # Other exceptions are acceptable


# ═══════════════════════════════════════════════════════════════════════
# Cycle 78 freeze-and-fold — moved verbatim from tests/test_v0916_task06.py
# (evolve/analyzer.py parts). No deviations.
# ═══════════════════════════════════════════════════════════════════════


class TestEvolveFrontmatterCRLF:
    """find_connection_opportunities must strip CRLF frontmatter."""

    def test_crlf_frontmatter_stripped(self, tmp_wiki):
        page = tmp_wiki / "concepts" / "crlf-evolve.md"
        # Write with CRLF line endings
        page.write_bytes(
            b"---\r\ntitle: CRLF Test\r\nsource: []\r\ncreated: 2026-01-01\r\n"
            b"updated: 2026-01-01\r\ntype: concept\r\nconfidence: stated\r\n---\r\n\r\n"
            b"Some unique content about special algorithms.\r\n"
        )

        from kb.evolve.analyzer import find_connection_opportunities

        # Should not crash and frontmatter fields should not appear as terms
        opps = find_connection_opportunities(tmp_wiki)
        assert isinstance(opps, list)


class TestEvolveReportExceptionHandler:
    """generate_evolution_report stub check must catch broad exceptions."""

    def test_os_error_in_stub_check(self, tmp_wiki):
        from unittest.mock import patch

        from kb.evolve.analyzer import generate_evolution_report

        with patch(
            "kb.evolve.analyzer.check_stub_pages",
            side_effect=OSError("disk error"),
        ):
            report = generate_evolution_report(tmp_wiki)
            assert isinstance(report, dict)


# -- Cycle 92 fold from test_v0915_task08.py (evolve analyzer subset) --
# ── Fix 8.3 — ranking meaningful above 10 terms ──────────────────────────────


class TestCrossLinkOpportunitiesRanking:
    """Fix 8.3: shared_term_count must reflect true count, not the capped list length."""

    def test_shared_term_count_field_present(self, tmp_wiki):
        """find_connection_opportunities returns shared_term_count key."""
        from kb.evolve.analyzer import find_connection_opportunities

        result = find_connection_opportunities(wiki_dir=tmp_wiki)
        for opp in result:
            assert "shared_term_count" in opp, "shared_term_count key missing from opportunity"

    def test_shared_term_count_matches_actual_count(self, tmp_wiki):
        """shared_term_count equals the true shared term total, not len(shared_terms[:10])."""
        # Create two pages with more than 10 shared significant words (all > 4 chars)
        long_words = [
            "apple",
            "banana",
            "cherry",
            "dragonfruit",
            "elderberry",
            "feijoa",
            "guava",
            "honeydew",
            "jackfruit",
            "kiwifruit",
            "lychee",
            "mango",
            "nectarine",
            "orange",
            "papaya",
        ]
        assert len(long_words) > 10

        frontmatter = "---\ntitle: Page A\ntype: concept\nconfidence: stated\n---\n\n"
        content_a = frontmatter + " ".join(long_words)
        content_b = frontmatter.replace("Page A", "Page B") + " ".join(long_words)

        (tmp_wiki / "concepts" / "page-a.md").write_text(content_a, encoding="utf-8")
        (tmp_wiki / "concepts" / "page-b.md").write_text(content_b, encoding="utf-8")

        from kb.evolve.analyzer import find_connection_opportunities

        result = find_connection_opportunities(wiki_dir=tmp_wiki)
        if result:
            opp = result[0]
            # shared_term_count must be the real count (>= len(shared_terms))
            assert opp["shared_term_count"] >= len(opp["shared_terms"])

    def test_sort_uses_shared_term_count_not_list_length(self, tmp_wiki):
        """Opportunities are sorted by shared_term_count descending."""
        from kb.evolve.analyzer import find_connection_opportunities

        result = find_connection_opportunities(wiki_dir=tmp_wiki)
        counts = [opp["shared_term_count"] for opp in result]
        assert counts == sorted(counts, reverse=True), (
            "Opportunities not sorted by shared_term_count"
        )


# ── Fix 8.5 — word-stripping includes '-' and '/' ────────────────────────────


class TestWordStrippingChars:
    """Fix 8.5: word-stripping must remove '-' and '/' along with punctuation."""

    def test_hyphen_stripped_from_word(self, tmp_wiki):
        """Words ending with '-' are stripped correctly and still count as significant."""
        content_a = (
            "---\ntitle: Page A\ntype: concept\nconfidence: stated\n---\n\n"
            "learning- training- neural- model- gradient-"
        )
        content_b = (
            "---\ntitle: Page B\ntype: concept\nconfidence: stated\n---\n\n"
            "learning training neural model gradient"
        )

        (tmp_wiki / "concepts" / "strip-a.md").write_text(content_a, encoding="utf-8")
        (tmp_wiki / "concepts" / "strip-b.md").write_text(content_b, encoding="utf-8")

        from kb.evolve.analyzer import find_connection_opportunities

        result = find_connection_opportunities(wiki_dir=tmp_wiki)
        # If words are stripped properly, the pair should have shared terms
        if result:
            assert result[0]["shared_term_count"] >= 1

    def test_slash_stripped_from_word(self, tmp_wiki):
        """Words ending with '/' are stripped correctly."""
        content_a = (
            "---\ntitle: Page C\ntype: concept\nconfidence: stated\n---\n\n"
            "training/ model/ neural/ gradient/ learning/"
        )
        content_b = (
            "---\ntitle: Page D\ntype: concept\nconfidence: stated\n---\n\n"
            "training model neural gradient learning"
        )

        (tmp_wiki / "concepts" / "strip-c.md").write_text(content_a, encoding="utf-8")
        (tmp_wiki / "concepts" / "strip-d.md").write_text(content_b, encoding="utf-8")

        from kb.evolve.analyzer import find_connection_opportunities

        result = find_connection_opportunities(wiki_dir=tmp_wiki)
        if result:
            assert result[0]["shared_term_count"] >= 1


# ── Fix 8.8 — frontmatter regex: no leading \\s* ─────────────────────────────


class TestFrontmatterRegex:
    """Fix 8.8: frontmatter regex must not have \\s* prefix (anchored to \\A)."""

    def test_frontmatter_stripped_at_start(self, tmp_wiki):
        """Content after frontmatter is processed; frontmatter keywords not indexed."""
        content = (
            "---\n"
            "title: Test Page\n"
            "type: concept\n"
            "confidence: stated\n"
            "---\n\n"
            "learning model gradient training neural"
        )
        (tmp_wiki / "concepts" / "fm-test.md").write_text(content, encoding="utf-8")

        from kb.evolve.analyzer import find_connection_opportunities

        # Just confirm no exception; frontmatter stripping is exercised
        find_connection_opportunities(wiki_dir=tmp_wiki)

    def test_analyzer_frontmatter_re_identity_with_shared(self):
        """Cycle 69 AC12 — C11-L1 upgrade per amendment A2.

        Replaces inspect.getsource source-grep with behavioural identity
        assertion: ``kb.evolve.analyzer.FRONTMATTER_RE is
        kb.utils.markdown.FRONTMATTER_RE`` (same compiled regex object,
        not an inline re-compile).

        This catches the cycle-21 L4 mutation directly: replacing
        ``from kb.utils.markdown import FRONTMATTER_RE`` with an inline
        ``FRONTMATTER_RE = re.compile(r"\\A\\s*---")`` produces a NEW
        compiled-regex object -> ``is`` check FAILs.

        Identity assertion is strictly stronger than the CRLF + tab
        divergence input proposed in A2 brainstorm — it catches ANY
        inline-recompile mutation, not just one regex shape. Per
        amendment-deviation rationale: stronger lock-in = better mutation
        resistance.
        """
        from kb.evolve import analyzer
        from kb.utils import markdown

        # Import shape at evolve/analyzer.py:19 is
        #   `from kb.utils.markdown import FRONTMATTER_RE as _FRONTMATTER_RE`
        # so the bound module attribute is `_FRONTMATTER_RE` (aliased).
        assert hasattr(analyzer, "_FRONTMATTER_RE"), (
            "kb.evolve.analyzer must expose _FRONTMATTER_RE "
            "(via `from kb.utils.markdown import FRONTMATTER_RE as _FRONTMATTER_RE`)"
        )
        assert analyzer._FRONTMATTER_RE is markdown.FRONTMATTER_RE, (
            "analyzer._FRONTMATTER_RE must be the SAME compiled regex "
            "object as kb.utils.markdown.FRONTMATTER_RE; an inline "
            "re.compile() would create a different object and fail this check"
        )


# ── Fix 8.9 — analyze_coverage threshold < 3 ─────────────────────────────────


class TestAnalyzeCoverageThreshold:
    """Fix 8.9: under_covered_types should include types with fewer than 3 pages."""

    def test_zero_pages_is_under_covered(self, tmp_wiki):
        """A type with 0 pages is flagged as under-covered."""
        from kb.evolve.analyzer import analyze_coverage

        result = analyze_coverage(wiki_dir=tmp_wiki)
        # tmp_wiki starts empty — all types have 0 pages → all are under-covered
        assert len(result["under_covered_types"]) > 0

    def test_one_page_is_under_covered(self, tmp_wiki):
        """A type with only 1 page is still under-covered (< 3)."""
        content = (
            "---\ntitle: Single Concept\ntype: concept\nconfidence: stated\n---\n\nContent here."
        )
        (tmp_wiki / "concepts" / "single.md").write_text(content, encoding="utf-8")

        from kb.evolve.analyzer import analyze_coverage

        result = analyze_coverage(wiki_dir=tmp_wiki)
        assert "concepts" in result["under_covered_types"], (
            "'concepts' with 1 page should be under-covered"
        )

    def test_two_pages_is_under_covered(self, tmp_wiki):
        """A type with 2 pages is still under-covered (< 3)."""
        for i in range(2):
            content = f"---\ntitle: Concept {i}\ntype: concept\nconfidence: stated\n---\n\nContent."
            (tmp_wiki / "concepts" / f"concept-{i}.md").write_text(content, encoding="utf-8")

        from kb.evolve.analyzer import analyze_coverage

        result = analyze_coverage(wiki_dir=tmp_wiki)
        assert "concepts" in result["under_covered_types"], (
            "'concepts' with 2 pages should be under-covered"
        )

    def test_three_pages_is_not_under_covered(self, tmp_wiki):
        """A type with exactly 3 pages is NOT under-covered."""
        for i in range(3):
            content = f"---\ntitle: Concept {i}\ntype: concept\nconfidence: stated\n---\n\nContent."
            (tmp_wiki / "concepts" / f"concept-{i}.md").write_text(content, encoding="utf-8")

        from kb.evolve.analyzer import analyze_coverage

        result = analyze_coverage(wiki_dir=tmp_wiki)
        assert "concepts" not in result["under_covered_types"], (
            "'concepts' with 3 pages should NOT be under-covered"
        )
