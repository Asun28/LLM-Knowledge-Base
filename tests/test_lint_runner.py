"""Regression tests for the lint runner and individual lint checks."""

import unittest.mock as mock


def test_check_orphan_pages_does_not_mutate_shared_graph(tmp_wiki, create_wiki_page):
    """Regression: Phase 4.5 CRITICAL item 8 (sentinel _index:* nodes leaked into shared_graph)."""
    create_wiki_page(page_id="concepts/a", title="A", content="Body.", wiki_dir=tmp_wiki)
    # Create index.md with a wikilink so the sentinel-node path is exercised
    (tmp_wiki / "index.md").write_text(
        "---\ntitle: Index\n---\n\n[[concepts/a]]\n", encoding="utf-8"
    )
    from kb.graph.builder import build_graph
    from kb.lint.checks import check_orphan_pages

    graph = build_graph(tmp_wiki)
    before_nodes = set(graph.nodes)
    _ = check_orphan_pages(tmp_wiki, graph=graph)
    after_nodes = set(graph.nodes)
    assert before_nodes == after_nodes, f"shared_graph mutated: added {after_nodes - before_nodes}"


def test_check_orphan_pages_does_not_report_index_sentinel(tmp_wiki, create_wiki_page):
    """Regression: Phase 4.5 CRITICAL item 8 (sentinel _index:* must not leak into orphans)."""
    create_wiki_page(page_id="concepts/a", title="A", content="Body.", wiki_dir=tmp_wiki)
    # Create an index.md with a wikilink so sentinel node augments into the graph
    (tmp_wiki / "index.md").write_text(
        "---\ntitle: Index\n---\n\n[[concepts/a]]\n", encoding="utf-8"
    )
    from kb.graph.builder import build_graph
    from kb.lint.checks import check_orphan_pages

    graph = build_graph(tmp_wiki)
    result = check_orphan_pages(tmp_wiki, graph=graph)
    orphan_pages = {issue["page"] for issue in result if issue.get("check") == "orphan_page"}
    assert "_index:index.md" not in orphan_pages, (
        f"Sentinel _index: node leaked into orphan warnings: {orphan_pages}"
    )


def test_run_all_checks_fix_rescans_before_downstream_checks(tmp_project, create_wiki_page):
    """Regression: Phase 4.5 CRITICAL item 9 (fix mode must re-scan so downstream checks see post-fix state)."""
    # Page A has two outbound links: one to existing B, one dead link to Z.
    # After fix_dead_links strips the dead link, A has ONE outbound link (to B).
    # If the re-scan never happened, shared_pages/shared_graph inside run_all_checks would
    # still reflect the PRE-fix content when downstream checks (orphan, cycle, stub) run.
    wiki_dir = tmp_project / "wiki"
    create_wiki_page(page_id="concepts/b", title="B", content="Body of B.", wiki_dir=wiki_dir)
    create_wiki_page(
        page_id="concepts/a",
        title="A",
        content="See [[concepts/b]] and [[concepts/z-nonexistent]] for details.",
        wiki_dir=wiki_dir,
    )
    from kb.lint.runner import run_all_checks

    # (1) Baseline with fix=False — must report at least one dead link
    report_no_fix = run_all_checks(wiki_dir=wiki_dir, fix=False)
    dead_links_before = [i for i in report_no_fix["issues"] if i.get("check") == "dead_link"]
    assert len(dead_links_before) >= 1, f"expected dead link before fix: {report_no_fix}"

    # (2) fix=True — runner should apply fix AND report it in fixes_applied
    report_fixed = run_all_checks(wiki_dir=wiki_dir, fix=True)
    assert report_fixed.get("fixes_applied"), f"fix not applied: {report_fixed}"
    fixed_targets = {f.get("target") for f in report_fixed["fixes_applied"]}
    assert any("z-nonexistent" in str(t) for t in fixed_targets), (
        f"expected z-nonexistent in fixed_targets: {fixed_targets}"
    )

    # (3) The page file on disk must have the dead wikilink bracket syntax stripped.
    # fix_dead_links replaces [[path/to/slug]] with the slug basename (plain text),
    # so "[[concepts/z-nonexistent]]" → "z-nonexistent". The brackets must be gone.
    a_path = wiki_dir / "concepts" / "a.md"
    a_content = a_path.read_text(encoding="utf-8")
    assert "[[concepts/z-nonexistent]]" not in a_content, (
        f"fix_dead_links did not strip [[concepts/z-nonexistent]] wikilink syntax from disk:\n{a_content}"
    )

    # (4) KEY behavioral assertion — a subsequent clean run must report NO dead links.
    # This proves the on-disk state is fully consistent; if the re-scan inside fix=True
    # had been skipped, downstream checks in that run would have operated on stale data,
    # and this follow-up clean run also exposes whether the file was actually patched.
    report_recheck = run_all_checks(wiki_dir=wiki_dir, fix=False)
    dead_links_after = [i for i in report_recheck["issues"] if i.get("check") == "dead_link"]
    assert not dead_links_after, (
        f"after fix mode, a subsequent clean run should show no dead links:\n{dead_links_after}"
    )


def test_run_all_checks_fix_rescan_call_count(tmp_project, create_wiki_page):
    """Safety-net: scan_wiki_pages + build_graph must each be called twice when fixes are applied."""
    # This is the lightweight companion to the behavior test above.
    # It patches at the runner-module level to catch any future refactor that removes the
    # explicit re-scan block without breaking the behavior test indirectly.
    wiki_dir = tmp_project / "wiki"
    create_wiki_page(page_id="concepts/b", title="B", content="Body of B.", wiki_dir=wiki_dir)
    create_wiki_page(
        page_id="concepts/a",
        title="A",
        content="See [[concepts/b]] and [[concepts/z-nonexistent]] for details.",
        wiki_dir=wiki_dir,
    )
    import kb.lint.runner as runner_mod

    real_scan = runner_mod.scan_wiki_pages
    real_build = runner_mod.build_graph

    with (
        mock.patch.object(runner_mod, "scan_wiki_pages", side_effect=real_scan) as mock_scan,
        mock.patch.object(runner_mod, "build_graph", side_effect=real_build) as mock_build,
    ):
        report = runner_mod.run_all_checks(wiki_dir=wiki_dir, fix=True)

    fixes = report.get("fixes_applied", [])
    assert fixes, f"Expected fixes_applied to be non-empty; broken link was not fixed: {report}"

    assert mock_scan.call_count >= 2, (
        f"scan_wiki_pages called {mock_scan.call_count} time(s) with fix=True + fixes applied; "
        f"expected >=2 (initial + post-fix re-scan)"
    )
    assert mock_build.call_count >= 2, (
        f"build_graph called {mock_build.call_count} time(s) with fix=True + fixes applied; "
        f"expected >=2 (initial + post-fix rebuild)"
    )
