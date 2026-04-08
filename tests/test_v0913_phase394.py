"""Tests for Phase 3.94 backlog fixes (v0.9.13)."""


# ── Task 1: BM25 & Query Engine ─────────────────────────────────────────────


class TestBM25DuplicateTokens:
    def test_duplicate_tokens_do_not_inflate_score(self):
        from kb.query.bm25 import BM25Index

        docs = [["neural", "network", "training"], ["python", "code"]]
        index = BM25Index(docs)
        score_single = index.score(["neural"])[0]
        score_double = index.score(["neural", "neural"])[0]
        assert score_single == score_double, (
            f"Duplicate tokens inflated score: single={score_single}, double={score_double}"
        )

    def test_unique_tokens_still_sum_correctly(self):
        from kb.query.bm25 import BM25Index

        docs = [["neural", "network"], ["python", "code"]]
        index = BM25Index(docs)
        score_two = index.score(["neural", "network"])[0]
        score_one = index.score(["neural"])[0]
        assert score_two > score_one


class TestQueryEngineMaxResults:
    def test_max_results_clamped_at_library_level(self, monkeypatch):
        """search_pages must not return more than MAX_SEARCH_RESULTS pages."""
        from kb.config import MAX_SEARCH_RESULTS
        from kb.query.engine import search_pages

        # Create MAX_SEARCH_RESULTS + 10 fake pages, all matching the query
        fake_pages = [
            {
                "id": f"concepts/fake-{i}",
                "path": f"wiki/concepts/fake-{i}.md",
                "title": f"Fake Concept {i}",
                "type": "concept",
                "confidence": "stated",
                "sources": [],
                "created": "2026-01-01",
                "updated": "2026-01-01",
                "content": "neural network deep learning",
                "raw_content": "neural network deep learning",
            }
            for i in range(MAX_SEARCH_RESULTS + 10)
        ]
        monkeypatch.setattr("kb.query.engine.load_all_pages", lambda *a, **kw: fake_pages)

        results = search_pages("neural network", max_results=9999)
        assert len(results) <= MAX_SEARCH_RESULTS, (
            f"Expected at most {MAX_SEARCH_RESULTS} results, got {len(results)}"
        )


class TestQueryContextTopPageWarning:
    def test_warns_when_top_page_excluded_by_limit(self, caplog):
        import logging

        from kb.query.engine import _build_query_context

        big_page = {
            "id": "concepts/big",
            "type": "concept",
            "confidence": "stated",
            "title": "Big Page",
            "content": "x" * 1000,
        }
        small_page = {
            "id": "concepts/small",
            "type": "concept",
            "confidence": "stated",
            "title": "Small Page",
            "content": "y" * 10,
        }
        with caplog.at_level(logging.WARNING, logger="kb.query.engine"):
            _build_query_context([big_page, small_page], max_chars=100)
        assert any("big" in r.message.lower() for r in caplog.records), (
            "Expected WARNING mentioning excluded top-page 'big'"
        )


class TestCitationsWikilinkNormalization:
    def test_wikilink_wrapped_path_extracted(self):
        from kb.query.citations import extract_citations

        text = "See [source: [[concepts/rag]]] for details."
        citations = extract_citations(text)
        paths = [c["path"] for c in citations]
        assert "concepts/rag" in paths, f"Expected 'concepts/rag' in {paths}"

    def test_plain_path_still_extracted(self):
        from kb.query.citations import extract_citations

        text = "See [source: concepts/rag] for details."
        citations = extract_citations(text)
        assert len(citations) == 1
        assert citations[0]["path"] == "concepts/rag"


# ── Task 2: Lint Runner, Checks, Verdicts ───────────────────────────────────


class TestDeadLinkFilterAfterFix:
    """lint/runner.py run_all_checks: fixed dead links removed from report."""

    def test_fixed_links_excluded_from_report(self, tmp_wiki, create_wiki_page):
        """After --fix, dead links that were fixed must not appear in the report."""
        from kb.lint.runner import run_all_checks

        # Create a page that links to a non-existent page
        create_wiki_page(
            page_id="concepts/linker",
            title="Linker",
            content="See [[concepts/nonexistent]] for more.",
            wiki_dir=tmp_wiki,
        )

        report = run_all_checks(wiki_dir=tmp_wiki, fix=True)
        dead_link_issues = [
            i
            for i in report["issues"]
            if i.get("check") == "dead_link" and "nonexistent" in i.get("target", "")
        ]
        assert len(dead_link_issues) == 0, (
            f"Fixed dead link still appears in report: {dead_link_issues}"
        )


class TestStalenessDatetimeBug:
    """lint/checks.py check_staleness: handles datetime.datetime updated field."""

    def test_staleness_does_not_raise_for_datetime_updated(self, tmp_wiki):
        """check_staleness must not crash when python-frontmatter parses updated as datetime."""
        from kb.lint.checks import check_staleness

        # Write a page with a full ISO datetime string that frontmatter parses as datetime
        page_dir = tmp_wiki / "concepts"
        page_dir.mkdir(exist_ok=True)
        page_path = page_dir / "datetime-page.md"
        page_path.write_text(
            "---\n"
            "title: Datetime Page\n"
            'source:\n  - "raw/articles/src.md"\n'
            "created: 2025-01-01\n"
            "updated: 2025-01-01T12:00:00\n"
            "type: concept\n"
            "confidence: stated\n"
            "---\n\nContent here.\n",
            encoding="utf-8",
        )
        # Should not raise TypeError
        issues = check_staleness(tmp_wiki)
        # The result is a list — no exception means pass
        assert isinstance(issues, list)


class TestVerdictPathTraversal:
    """lint/verdicts.py add_verdict: rejects path traversal in page_id."""

    def test_add_verdict_rejects_path_traversal(self, tmp_path):
        """add_verdict must raise ValueError for page_ids with '..' or leading '/'."""
        import pytest

        from kb.lint.verdicts import add_verdict

        with pytest.raises(ValueError, match="Invalid page_id"):
            add_verdict("../etc/passwd", "fidelity", "pass", path=tmp_path / "v.json")

        with pytest.raises(ValueError, match="Invalid page_id"):
            add_verdict("/absolute/path", "fidelity", "pass", path=tmp_path / "v.json")


class TestVerdictNotesCap:
    """lint/verdicts.py add_verdict: notes length is capped."""

    def test_add_verdict_rejects_oversized_notes(self, tmp_path):
        """add_verdict must raise ValueError when notes exceed MAX_NOTES_LEN."""
        import pytest

        from kb.lint.verdicts import add_verdict

        with pytest.raises(ValueError, match="Notes too long"):
            add_verdict(
                "concepts/test",
                "fidelity",
                "pass",
                notes="x" * 2001,
                path=tmp_path / "v.json",
            )
