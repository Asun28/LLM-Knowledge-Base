"""Cycle 45 AC34: lint runner check order is a stable contract."""

from kb.lint import runner

EXPECTED_CHECK_ORDER = [
    "dead_links",
    "orphan_pages",
    "staleness",
    "frontmatter_staleness",
    "status_mature_stale",
    "authored_by_drift",
    "frontmatter",
    "source_coverage",
    "wikilink_cycles",
    "stub_pages",
    "duplicate_slugs",
    "inline_callouts",
]


def test_lint_runner_enumeration_order_unchanged(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "scan_wiki_pages", lambda _wiki_dir: [])
    monkeypatch.setattr(runner, "build_graph", lambda _wiki_dir: object())
    monkeypatch.setattr(runner, "get_verdict_summary", lambda _path=None: None)

    for name in (
        "check_dead_links",
        "check_orphan_pages",
        "check_staleness",
        "check_frontmatter_staleness",
        "check_status_mature_stale",
        "check_authored_by_drift",
        "check_frontmatter",
        "check_source_coverage",
        "check_cycles",
        "check_stub_pages",
        "check_duplicate_slugs",
        "check_inline_callouts",
    ):
        monkeypatch.setattr(runner, name, lambda *a, **k: [])

    report = runner.run_all_checks(tmp_path / "wiki", tmp_path / "raw")

    assert [check["name"] for check in report["checks_run"]] == EXPECTED_CHECK_ORDER
