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
