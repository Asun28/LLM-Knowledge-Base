"""Cycle 16 AC14-AC16 — new lint checks wired into run_all_checks + format_report.

Direct import + tmp_wiki fixture.
"""

from pathlib import Path

from kb.lint.runner import format_report, run_all_checks


def _write_body(wiki_dir: Path, page_id: str, body: str = "body.") -> None:
    path = wiki_dir / f"{page_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f'title: "{page_id}"\n'
        'source: ["raw/articles/x.md"]\n'
        "created: 2026-04-01\n"
        "updated: 2026-04-01\n"
        "type: concept\n"
        "confidence: stated\n"
        f"---\n\n{body}\n",
        encoding="utf-8",
    )


class TestRunAllChecksKeys:
    def test_duplicate_slugs_key_present(self, tmp_wiki) -> None:
        """AC14 — run_all_checks output has duplicate_slugs key."""
        report = run_all_checks(wiki_dir=tmp_wiki)
        assert "duplicate_slugs" in report
        assert isinstance(report["duplicate_slugs"], list)

    def test_inline_callouts_key_present(self, tmp_wiki) -> None:
        """AC14 — run_all_checks output has inline_callouts key."""
        report = run_all_checks(wiki_dir=tmp_wiki)
        assert "inline_callouts" in report
        assert isinstance(report["inline_callouts"], list)

    def test_duplicate_slugs_flagged_pair_appears(self, tmp_wiki) -> None:
        _write_body(tmp_wiki, "concepts/attention")
        _write_body(tmp_wiki, "concepts/attnetion")
        report = run_all_checks(wiki_dir=tmp_wiki)
        assert len(report["duplicate_slugs"]) == 1
        assert report["duplicate_slugs"][0]["distance"] == 2

    def test_inline_callouts_aggregated_into_report(self, tmp_wiki) -> None:
        _write_body(tmp_wiki, "concepts/a", "> [!gap] hole here\n")
        _write_body(tmp_wiki, "concepts/b", "> [!contradiction] conflict\n")
        report = run_all_checks(wiki_dir=tmp_wiki)
        markers = sorted(c["marker"] for c in report["inline_callouts"])
        assert markers == ["contradiction", "gap"]


class TestSummaryCounters:
    def test_summary_warning_incremented_by_duplicate_slugs(self, tmp_wiki) -> None:
        _write_body(tmp_wiki, "concepts/attention")
        _write_body(tmp_wiki, "concepts/attnetion")
        report = run_all_checks(wiki_dir=tmp_wiki)
        # At least 1 warning from the flagged slug pair.
        assert report["summary"]["warning"] >= 1

    def test_summary_info_incremented_by_inline_callouts(self, tmp_wiki) -> None:
        _write_body(tmp_wiki, "concepts/a", "> [!gap] x\n")
        _write_body(tmp_wiki, "concepts/b", "> [!stale] y\n")
        report = run_all_checks(wiki_dir=tmp_wiki)
        # At least 2 info items from the two callouts.
        assert report["summary"]["info"] >= 2

    def test_summary_info_key_always_present(self, tmp_wiki) -> None:
        """Q7 lock — severity_counts must always have 'info' key.

        The runner.py init seeds {'error':0,'warning':0,'info':0}. Any
        future refactor that drops the 'info' seed would break this test,
        preventing silent regressions masked by a no-op setdefault.
        """
        report = run_all_checks(wiki_dir=tmp_wiki)
        assert "info" in report["summary"]

    def test_summary_info_includes_inline_callout_contribution(self, tmp_wiki) -> None:
        """Q7 — summary.info reflects inline_callouts count (at minimum).

        Other checks (stub_pages, frontmatter_updated_stale) also emit
        info-severity issues, so the exact delta depends on page shape.
        The invariant is: summary.info >= len(inline_callouts) and
        adding callout-bearing pages must increase summary.info by at
        least the callout count.
        """
        _write_body(tmp_wiki, "concepts/a", "plain body\n")
        baseline = run_all_checks(wiki_dir=tmp_wiki)["summary"]["info"]

        _write_body(tmp_wiki, "concepts/b", "> [!gap] one\n> [!stale] two\n")
        after = run_all_checks(wiki_dir=tmp_wiki)
        assert len(after["inline_callouts"]) == 2
        assert after["summary"]["info"] >= baseline + 2


class TestFormatReportSections:
    def test_renders_duplicate_slugs_section_when_nonempty(self, tmp_wiki) -> None:
        _write_body(tmp_wiki, "concepts/attention")
        _write_body(tmp_wiki, "concepts/attnetion")
        report = run_all_checks(wiki_dir=tmp_wiki)
        out = format_report(report)
        assert "## Duplicate slugs" in out
        assert "distance 2" in out

    def test_renders_inline_callouts_section_when_nonempty(self, tmp_wiki) -> None:
        _write_body(tmp_wiki, "concepts/a", "> [!gap] hole\n")
        report = run_all_checks(wiki_dir=tmp_wiki)
        out = format_report(report)
        assert "## Inline callouts" in out
        assert "[gap]" in out

    def test_omits_sections_when_empty(self, tmp_wiki) -> None:
        # One lone page → no duplicate slugs, no callouts.
        _write_body(tmp_wiki, "concepts/solo", "plain body\n")
        report = run_all_checks(wiki_dir=tmp_wiki)
        out = format_report(report)
        assert "## Duplicate slugs" not in out
        assert "## Inline callouts" not in out

    def test_renders_skip_record_for_large_wiki(self, tmp_wiki) -> None:
        # Force a skip record into the report.
        report = {
            "checks_run": [],
            "total_issues": 0,
            "issues": [],
            "summary": {"error": 0, "warning": 0, "info": 0},
            "fixes_applied": [],
            "duplicate_slugs": [
                {
                    "slug_a": "<skipped>",
                    "slug_b": "<skipped>",
                    "distance": -1,
                    "page_a": "",
                    "page_b": "",
                    "skipped_reason": "wiki too large (11000 pages > cap 10000)",
                }
            ],
            "inline_callouts": [],
        }
        out = format_report(report)
        assert "(skipped — wiki too large" in out


class TestChecksRunEntries:
    def test_duplicate_slugs_check_reported(self, tmp_wiki) -> None:
        report = run_all_checks(wiki_dir=tmp_wiki)
        names = {c["name"] for c in report["checks_run"]}
        assert "duplicate_slugs" in names
        assert "inline_callouts" in names
