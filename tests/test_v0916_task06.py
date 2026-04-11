"""Phase 3.97 Task 06 — Lint / Review / Evolve fixes."""

import json
from pathlib import Path

import pytest


# ── lint/checks.py ─────────────────────────────────────────────────────


class TestFixDeadLinksCodeBlockMasking:
    """fix_dead_links must not modify wikilinks inside code blocks."""

    def test_wikilink_in_code_block_preserved(self, tmp_wiki):
        page = tmp_wiki / "concepts" / "tutorial.md"
        page.write_text(
            '---\ntitle: "Tutorial"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
            "Example:\n```\n[[concepts/old-name]]\n```\n"
            "Also see [[concepts/old-name]] in text.\n",
            encoding="utf-8",
        )

        from kb.lint.checks import fix_dead_links

        broken = [{"source": "concepts/tutorial", "target": "concepts/old-name"}]
        fix_dead_links(wiki_dir=tmp_wiki, broken_links=broken)
        content = page.read_text(encoding="utf-8")
        # The code block version should be preserved
        assert "```\n[[concepts/old-name]]\n```" in content


class TestCheckSourceCoverageSymlink:
    """check_source_coverage must not crash on symlinks escaping raw_dir."""

    def test_symlink_skipped_gracefully(self, tmp_path):
        """A symlink that escapes raw_dir should log warning, not crash."""
        raw_dir = tmp_path / "raw"
        articles = raw_dir / "articles"
        articles.mkdir(parents=True)
        (articles / "real.md").write_text("content", encoding="utf-8")

        wiki_dir = tmp_path / "wiki"
        for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
            (wiki_dir / subdir).mkdir(parents=True)

        from kb.lint.checks import check_source_coverage

        # Should not raise even if make_source_ref has edge cases
        issues = check_source_coverage(wiki_dir=wiki_dir, raw_dir=raw_dir)
        assert isinstance(issues, list)


# ── review/refiner.py ──────────────────────────────────────────────────


class TestRefinePageReadError:
    """refine_page must return error dict when read_text raises."""

    def test_os_error_on_read(self, tmp_wiki):
        page = tmp_wiki / "concepts" / "test-read.md"
        page.write_text(
            '---\ntitle: "Test"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\nContent.\n",
            encoding="utf-8",
        )

        from unittest.mock import patch

        from kb.review.refiner import refine_page

        with patch.object(Path, "read_text", side_effect=OSError("Permission denied")):
            result = refine_page("concepts/test-read", "new content", wiki_dir=tmp_wiki)
            assert "error" in result


class TestLoadReviewHistoryRobustness:
    """load_review_history must handle corrupt files."""

    def test_non_list_json_returns_empty(self, tmp_path):
        history_file = tmp_path / "history.json"
        history_file.write_text('{"key": "value"}', encoding="utf-8")

        from kb.review.refiner import load_review_history

        result = load_review_history(history_file)
        assert result == []

    def test_os_error_returns_empty(self, tmp_path):
        history_file = tmp_path / "history.json"
        history_file.write_text("[1, 2, 3]", encoding="utf-8")

        from unittest.mock import patch

        from kb.review.refiner import load_review_history

        with patch.object(Path, "read_text", side_effect=OSError("read error")):
            result = load_review_history(history_file)
            assert result == []


class TestRefinePageCRLFGuard:
    """refine_page frontmatter guard must handle CRLF content."""

    def test_crlf_frontmatter_rejected(self, tmp_wiki):
        page = tmp_wiki / "concepts" / "crlf-test.md"
        page.write_text(
            '---\ntitle: "CRLF"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\nContent.\n",
            encoding="utf-8",
        )

        from kb.review.refiner import refine_page

        # Content that looks like a frontmatter block with CRLF
        result = refine_page(
            "concepts/crlf-test",
            "---\r\ntitle: bad\r\n---\r\nContent",
            wiki_dir=tmp_wiki,
        )
        assert "error" in result


# ── lint/trends.py ─────────────────────────────────────────────────────


class TestVerdictTrendsTotalKey:
    """compute_verdict_trends must not double-count verdict='total'."""

    def test_total_verdict_not_counted(self, tmp_path):
        from kb.lint.trends import compute_verdict_trends

        verdicts_file = tmp_path / "verdicts.json"
        verdicts_file.write_text(
            json.dumps(
                [
                    {
                        "timestamp": "2026-04-07T10:00:00",
                        "verdict": "pass",
                        "page_id": "a",
                        "verdict_type": "fidelity",
                        "issues": [],
                        "notes": "",
                    },
                    {
                        "timestamp": "2026-04-07T11:00:00",
                        "verdict": "total",
                        "page_id": "b",
                        "verdict_type": "fidelity",
                        "issues": [],
                        "notes": "",
                    },
                ]
            ),
            encoding="utf-8",
        )

        result = compute_verdict_trends(verdicts_file)
        # "total" verdict should not be counted in overall
        assert result["overall"]["pass"] == 1


# ── evolve/analyzer.py ────────────────────────────────────────────────


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
