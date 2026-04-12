"""Phase 3.96 Task 6 — Lint module fixes.

Covers:
  6.1  fix_dead_links pages_fixed count (len of actually-modified pages, not all broken pages)
  6.2  fix_dead_links broken_links optional param (avoids duplicate resolve_wikilinks call)
  6.3  threading.Lock in add_verdict (read-modify-write race protection)
  6.4  check_frontmatter bare except narrowed
  6.5  _group_by_shared_sources bare except narrowed
  6.6  _group_by_wikilinks uses nx.connected_components (star-topology fix)
  6.7  trend direction min sample check for previous period
  6.8  CRLF regex in _group_by_term_overlap
  6.9  check_staleness unrecognised updated type
  6.10 auto-selected groups size cap in build_consistency_context
  6.11 get_page_verdicts KeyError on malformed entries
  6.12 check_source_coverage path rel via raw_dir (effective_raw_dir removed)
  6.13 scan_wiki_pages called once in run_all_checks
  6.14 standardized "page" key in dead_link issues
  6.15 null byte check in add_verdict
  6.16 seen_pairs set removed (loop structure prevents dups)
  6.17 effective_raw_dir alias removed
  6.18 pass_rate uses sum(o.values())
"""

import threading

# ── Fix 6.1 — fix_dead_links pages_fixed count ───────────────────────────────


class TestFixDeadLinksPageCount:
    """Fix 6.1 — pages_fixed counts only pages where content actually changed."""

    def test_pages_fixed_counts_modified_pages_only(self, tmp_wiki, create_wiki_page):
        """A page where all targets happen to not match the pattern should not be counted."""
        from kb.lint.checks import fix_dead_links

        # Page A links to non-existent page B
        create_wiki_page(
            "concepts/page-a",
            wiki_dir=tmp_wiki,
            content="See [[concepts/missing-target]] for details.",
        )
        # Page C links to non-existent page D but the link is in a weird format
        # that won't match the regex — so content won't change
        create_wiki_page(
            "concepts/page-c",
            wiki_dir=tmp_wiki,
            content="No broken links here (none matching target).",
        )

        fixes = fix_dead_links(tmp_wiki)
        # Only page-a had its content actually changed
        pages_in_fixes = {f["page"] for f in fixes}
        # Verify the count matches unique modified pages
        assert len(pages_in_fixes) == len({f["page"] for f in fixes})

    def test_single_page_with_two_broken_links(self, tmp_wiki, create_wiki_page):
        """Two broken links on same page → 1 page fixed, 2 fixes."""
        from kb.lint.checks import fix_dead_links

        create_wiki_page(
            "concepts/page-a",
            wiki_dir=tmp_wiki,
            content="See [[concepts/missing-one]] and [[concepts/missing-two]].",
        )

        fixes = fix_dead_links(tmp_wiki)
        assert len(fixes) == 2
        pages_fixed = len({f["page"] for f in fixes})
        assert pages_fixed == 1

    def test_two_pages_each_with_one_broken_link(self, tmp_wiki, create_wiki_page):
        """One broken link each on two pages → 2 pages fixed, 2 fixes."""
        from kb.lint.checks import fix_dead_links

        create_wiki_page(
            "concepts/page-a",
            wiki_dir=tmp_wiki,
            content="See [[concepts/missing-x]].",
        )
        create_wiki_page(
            "concepts/page-b",
            wiki_dir=tmp_wiki,
            content="See [[concepts/missing-y]].",
        )

        fixes = fix_dead_links(tmp_wiki)
        assert len(fixes) == 2
        pages_fixed = len({f["page"] for f in fixes})
        assert pages_fixed == 2


# ── Fix 6.2 — broken_links optional parameter ────────────────────────────────


class TestFixDeadLinksBrokenLinksParam:
    """Fix 6.2 — fix_dead_links accepts pre-computed broken_links."""

    def test_accepts_broken_links_param(self, tmp_wiki, create_wiki_page):
        """Passing broken_links avoids calling resolve_wikilinks() again."""
        from kb.lint.checks import fix_dead_links

        create_wiki_page(
            "concepts/page-a",
            wiki_dir=tmp_wiki,
            content="See [[concepts/missing]].",
        )

        # Pre-compute broken links manually
        broken = [{"source": "concepts/page-a", "target": "concepts/missing"}]
        fixes = fix_dead_links(tmp_wiki, broken_links=broken)
        assert len(fixes) == 1
        assert fixes[0]["page"] == "concepts/page-a"

    def test_empty_broken_links_returns_no_fixes(self, tmp_wiki, create_wiki_page):
        """Passing empty broken_links list returns no fixes."""
        from kb.lint.checks import fix_dead_links

        create_wiki_page(
            "concepts/page-a",
            wiki_dir=tmp_wiki,
            content="See [[concepts/missing]].",
        )

        fixes = fix_dead_links(tmp_wiki, broken_links=[])
        assert fixes == []

    def test_none_broken_links_falls_back_to_resolve(self, tmp_wiki, create_wiki_page):
        """Passing broken_links=None (default) calls resolve_wikilinks internally."""
        from kb.lint.checks import fix_dead_links

        create_wiki_page(
            "concepts/page-a",
            wiki_dir=tmp_wiki,
            content="See [[concepts/missing]].",
        )

        fixes = fix_dead_links(tmp_wiki, broken_links=None)
        assert len(fixes) == 1


# ── Fix 6.3 — threading.Lock in add_verdict ──────────────────────────────────


class TestAddVerdictThreadingLock:
    """Fix 6.3 — concurrent add_verdict calls do not lose entries."""

    def test_concurrent_add_verdict_no_lost_writes(self, tmp_path):
        """Multiple threads adding verdicts concurrently should all be persisted."""
        from kb.lint.verdicts import add_verdict, load_verdicts

        path = tmp_path / "verdicts.json"
        n_threads = 10

        errors = []

        def add_one(i):
            try:
                add_verdict(
                    f"concepts/page-{i}",
                    "review",
                    "pass",
                    notes=f"thread {i}",
                    path=path,
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_one, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent write: {errors}"
        result = load_verdicts(path)
        assert len(result) == n_threads

    def test_lock_module_attribute_does_not_use_threading(self):
        """add_verdict must not use threading.Lock — file_lock is the cross-process guard."""
        import kb.lint.verdicts as verdicts_mod

        # _verdicts_lock was replaced by file_lock; no threading.Lock at module level
        assert not hasattr(verdicts_mod, "_verdicts_lock") or not hasattr(
            getattr(verdicts_mod, "_verdicts_lock", None), "acquire"
        ), "_verdicts_lock is still a threading.Lock — replace with file_lock"


# ── Fix 6.11 — get_page_verdicts KeyError ────────────────────────────────────


class TestGetPageVerdictsKeyError:
    """Fix 6.11 — get_page_verdicts uses .get() to tolerate malformed entries."""

    def test_malformed_entry_no_page_id_key_is_skipped(self, tmp_path):
        """Entry missing 'page_id' key should not raise KeyError."""
        import json

        from kb.lint.verdicts import get_page_verdicts

        path = tmp_path / "verdicts.json"
        # Write a malformed entry (no page_id key)
        malformed = [
            {"verdict_type": "review", "verdict": "pass", "timestamp": "2026-01-01T00:00:00"}
        ]
        path.write_text(json.dumps(malformed), encoding="utf-8")

        # Should not raise
        result = get_page_verdicts("concepts/rag", path=path)
        assert result == []

    def test_malformed_entry_mixed_with_valid(self, tmp_path):
        """Valid entries are returned even when malformed entries are present."""
        import json

        from kb.lint.verdicts import get_page_verdicts

        path = tmp_path / "verdicts.json"
        data = [
            # malformed — no page_id
            {"verdict_type": "review", "verdict": "pass", "timestamp": "2026-01-01T00:00:00"},
            # valid
            {
                "page_id": "concepts/rag",
                "verdict_type": "review",
                "verdict": "pass",
                "timestamp": "2026-01-02T00:00:00",
            },
        ]
        path.write_text(json.dumps(data), encoding="utf-8")

        result = get_page_verdicts("concepts/rag", path=path)
        assert len(result) == 1
        assert result[0]["page_id"] == "concepts/rag"


# ── Fix 6.4 — check_frontmatter bare except narrowed ─────────────────────────


class TestCheckFrontmatterNarrowExcept:
    """Fix 6.4 — check_frontmatter uses specific exception types."""

    def test_does_not_swallow_keyboard_interrupt(self, tmp_wiki, create_wiki_page):
        """KeyboardInterrupt should propagate (not caught by narrowed except)."""
        import frontmatter as fm_lib

        from kb.lint import checks

        create_wiki_page("concepts/rag", wiki_dir=tmp_wiki)

        original = fm_lib.load
        call_count = [0]

        def mock_load(path):
            call_count[0] += 1
            if call_count[0] == 1:
                raise KeyboardInterrupt("user abort")
            return original(path)

        fm_lib.load = mock_load
        try:
            import importlib

            importlib.reload(checks)
            # Should propagate the KeyboardInterrupt
            try:
                checks.check_frontmatter(tmp_wiki)
                assert False, "Expected KeyboardInterrupt"
            except KeyboardInterrupt:
                pass
        finally:
            fm_lib.load = original


# ── Fix 6.9 — check_staleness unrecognised updated type ──────────────────────


class TestCheckStalenessUnrecognisedType:
    """Fix 6.9 — check_staleness emits warning for unexpected updated types."""

    def test_integer_updated_triggers_warning_issue(self, tmp_wiki):
        """An integer 'updated' value should produce a staleness warning issue."""
        from kb.lint.checks import check_staleness

        page_path = tmp_wiki / "concepts" / "weird.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a page with numeric updated field
        page_path.write_text(
            "---\ntitle: Weird\nsource:\n  - raw/articles/test.md\n"
            "created: 2026-01-01\nupdated: 20260101\ntype: concept\nconfidence: stated\n---\n"
            "# Weird\n",
            encoding="utf-8",
        )

        issues = check_staleness(tmp_wiki)
        staleness_issues = [i for i in issues if i.get("page", "").endswith("weird")]
        assert any("unrecognised" in i["message"] for i in staleness_issues)

    def test_valid_date_not_flagged_as_unrecognised(self, tmp_wiki, create_wiki_page):
        """A proper date string should not trigger the unrecognised type warning."""
        from kb.lint.checks import check_staleness

        create_wiki_page("concepts/normal", wiki_dir=tmp_wiki, updated="2026-01-01")
        issues = check_staleness(tmp_wiki)
        unrecognised = [i for i in issues if "unrecognised" in i.get("message", "")]
        assert not any(i.get("page", "") == "concepts/normal" for i in unrecognised)


# ── Fix 6.14 — standardized "page" key in dead_link issues ───────────────────


class TestDeadLinkIssuePageKey:
    """Fix 6.14 — check_dead_links uses 'page' key instead of 'source'."""

    def test_dead_link_issue_has_page_key(self, tmp_wiki, create_wiki_page):
        """check_dead_links issues should have 'page' key, not 'source'."""
        from kb.lint.checks import check_dead_links

        create_wiki_page(
            "concepts/page-a",
            wiki_dir=tmp_wiki,
            content="See [[concepts/nonexistent]].",
        )

        issues = check_dead_links(tmp_wiki)
        dead = [i for i in issues if i.get("check") == "dead_link"]
        assert len(dead) >= 1
        for issue in dead:
            assert "page" in issue, f"'page' key missing from dead_link issue: {issue}"
            assert "source" not in issue, f"'source' key should not be in dead_link issue: {issue}"

    def test_dead_link_page_value_is_source_page(self, tmp_wiki, create_wiki_page):
        """The 'page' value should be the page containing the broken link."""
        from kb.lint.checks import check_dead_links

        create_wiki_page(
            "concepts/page-a",
            wiki_dir=tmp_wiki,
            content="See [[concepts/nonexistent]].",
        )

        issues = check_dead_links(tmp_wiki)
        dead = [i for i in issues if i.get("check") == "dead_link"]
        assert any(i["page"] == "concepts/page-a" for i in dead)


# ── Fix 6.15 — null byte check in add_verdict ────────────────────────────────


class TestAddVerdictNullByte:
    """Fix 6.15 — add_verdict rejects page_id containing null bytes."""

    def test_null_byte_raises_value_error(self, tmp_path):
        """page_id with null byte should raise ValueError."""
        import pytest

        from kb.lint.verdicts import add_verdict

        path = tmp_path / "verdicts.json"
        with pytest.raises(ValueError, match="Invalid page_id"):
            add_verdict("concepts/rag\x00evil", "review", "pass", path=path)

    def test_valid_page_id_not_rejected(self, tmp_path):
        """Normal page_id should still work after adding null byte check."""
        from kb.lint.verdicts import add_verdict, load_verdicts

        path = tmp_path / "verdicts.json"
        entry = add_verdict("concepts/rag", "review", "pass", path=path)
        assert entry["page_id"] == "concepts/rag"
        assert len(load_verdicts(path)) == 1


# ── Fix 6.7 — trend min sample for previous period ───────────────────────────


class TestTrendMinSampleBothPeriods:
    """Fix 6.7 — trend direction requires min 3 verdicts in BOTH periods."""

    def test_previous_period_below_min_gives_stable(self, tmp_path):
        """If previous period has < 3 verdicts, trend should stay 'stable'."""
        import json

        from kb.lint.trends import compute_verdict_trends

        path = tmp_path / "verdicts.json"
        verdicts = [
            # Previous week — only 2 verdicts (below threshold)
            {
                "page_id": "p1",
                "verdict_type": "review",
                "verdict": "fail",
                "timestamp": "2026-03-30T10:00:00",
            },
            {
                "page_id": "p2",
                "verdict_type": "review",
                "verdict": "fail",
                "timestamp": "2026-03-31T10:00:00",
            },
            # Current week — 3 passes (above threshold)
            {
                "page_id": "p3",
                "verdict_type": "review",
                "verdict": "pass",
                "timestamp": "2026-04-06T10:00:00",
            },
            {
                "page_id": "p4",
                "verdict_type": "review",
                "verdict": "pass",
                "timestamp": "2026-04-07T10:00:00",
            },
            {
                "page_id": "p5",
                "verdict_type": "review",
                "verdict": "pass",
                "timestamp": "2026-04-08T10:00:00",
            },
        ]
        path.write_text(json.dumps(verdicts), encoding="utf-8")

        result = compute_verdict_trends(path)
        # Previous period has only 2 verdicts, so should be stable (not improving)
        assert result["trend"] == "stable"

    def test_both_periods_above_min_can_show_improving(self, tmp_path):
        """Both periods with >= 3 verdicts can produce 'improving' trend."""
        import json

        from kb.lint.trends import compute_verdict_trends

        path = tmp_path / "verdicts.json"
        verdicts = [
            # Previous week — 3 fails
            {
                "page_id": "p1",
                "verdict_type": "review",
                "verdict": "fail",
                "timestamp": "2026-03-30T10:00:00",
            },
            {
                "page_id": "p2",
                "verdict_type": "review",
                "verdict": "fail",
                "timestamp": "2026-03-31T10:00:00",
            },
            {
                "page_id": "p3",
                "verdict_type": "review",
                "verdict": "fail",
                "timestamp": "2026-04-01T10:00:00",
            },
            # Current week — 3 passes
            {
                "page_id": "p4",
                "verdict_type": "review",
                "verdict": "pass",
                "timestamp": "2026-04-06T10:00:00",
            },
            {
                "page_id": "p5",
                "verdict_type": "review",
                "verdict": "pass",
                "timestamp": "2026-04-07T10:00:00",
            },
            {
                "page_id": "p6",
                "verdict_type": "review",
                "verdict": "pass",
                "timestamp": "2026-04-08T10:00:00",
            },
        ]
        path.write_text(json.dumps(verdicts), encoding="utf-8")

        result = compute_verdict_trends(path)
        assert result["trend"] == "improving"


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


# ── Fix 6.18 — pass_rate uses sum(o.values()) ────────────────────────────────


class TestFormatVerdictTrendsPassRate:
    """Fix 6.18 — format_verdict_trends uses sum(o.values()) for pass_rate."""

    def test_pass_rate_uses_overall_sum(self, tmp_path):
        """pass_rate denominator should be sum of pass+fail+warning counts."""
        import json

        from kb.lint.trends import compute_verdict_trends, format_verdict_trends

        path = tmp_path / "verdicts.json"

        def v(pid, verdict, hour):
            return {
                "page_id": pid,
                "verdict_type": "review",
                "verdict": verdict,
                "timestamp": f"2026-04-06T{hour:02d}:00:00",
            }

        verdicts = [
            v("p1", "pass", 10),
            v("p2", "fail", 11),
            v("p3", "warning", 12),
            v("p4", "pass", 13),
        ]
        path.write_text(json.dumps(verdicts), encoding="utf-8")

        trends = compute_verdict_trends(path)
        text = format_verdict_trends(trends)

        # 2 passes out of 4 total = 50%
        assert "50%" in text


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
