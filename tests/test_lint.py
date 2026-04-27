"""Tests for the lint module."""

from datetime import date, timedelta
from pathlib import Path

from kb.lint.checks import (
    check_dead_links,
    check_frontmatter,
    check_orphan_pages,
    check_source_coverage,
    check_staleness,
)
from kb.lint.runner import format_report, run_all_checks


def _create_page(
    path: Path,
    title: str,
    content: str,
    page_type: str = "concept",
    updated: str | None = None,
) -> None:
    """Helper to create a wiki page with frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    updated = updated or date.today().isoformat()
    fm = (
        f'---\ntitle: "{title}"\nsource:\n  - raw/articles/test.md\n'
        f"created: 2026-04-06\nupdated: {updated}\ntype: {page_type}\n"
        f"confidence: stated\n---\n\n"
    )
    path.write_text(fm + content, encoding="utf-8")


# ── Dead link checks ───────────────────────────────────────────


def test_check_dead_links_found(tmp_wiki):
    """check_dead_links detects broken wikilinks."""
    _create_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "Links to [[entities/nonexistent]] which doesn't exist.",
    )
    issues = check_dead_links(tmp_wiki)
    assert len(issues) == 1
    assert issues[0]["check"] == "dead_link"
    assert issues[0]["target"] == "entities/nonexistent"


def test_check_dead_links_none(tmp_wiki):
    """check_dead_links returns empty when all links resolve."""
    _create_page(tmp_wiki / "concepts" / "rag.md", "RAG", "Links to [[concepts/llm]].")
    _create_page(tmp_wiki / "concepts" / "llm.md", "LLM", "LLM content.")
    issues = check_dead_links(tmp_wiki)
    assert issues == []


# ── Orphan page checks ─────────────────────────────────────────


def test_check_orphan_pages(tmp_wiki):
    """check_orphan_pages detects pages with outgoing but no incoming links."""
    _create_page(
        tmp_wiki / "concepts" / "orphan.md",
        "Orphan",
        "This links to [[concepts/rag]] but nobody links here.",
    )
    _create_page(tmp_wiki / "concepts" / "rag.md", "RAG", "No links.")
    issues = check_orphan_pages(tmp_wiki)
    orphan_pages = [i["page"] for i in issues if i["check"] == "orphan_page"]
    assert "concepts/orphan" in orphan_pages


def test_check_orphan_summaries_excluded(tmp_wiki):
    """check_orphan_pages does not flag summary pages as orphans."""
    _create_page(
        tmp_wiki / "summaries" / "article1.md",
        "Article 1",
        "Links to [[concepts/rag]].",
        page_type="summary",
    )
    _create_page(tmp_wiki / "concepts" / "rag.md", "RAG", "No links.")
    issues = check_orphan_pages(tmp_wiki)
    orphan_pages = [i["page"] for i in issues if i["check"] == "orphan_page"]
    assert "summaries/article1" not in orphan_pages


# ── Staleness checks ──────────────────────────────────────────


def test_check_staleness_stale_page(tmp_wiki):
    """check_staleness detects pages older than threshold."""
    old_date = (date.today() - timedelta(days=100)).isoformat()
    _create_page(tmp_wiki / "concepts" / "old.md", "Old Page", "Old content.", updated=old_date)
    issues = check_staleness(tmp_wiki, max_days=90)
    assert len(issues) == 1
    assert issues[0]["check"] == "stale_page"


def test_check_staleness_fresh_page(tmp_wiki):
    """check_staleness does not flag recently updated pages."""
    _create_page(tmp_wiki / "concepts" / "fresh.md", "Fresh Page", "Fresh content.")
    issues = check_staleness(tmp_wiki, max_days=90)
    assert issues == []


# ── Frontmatter checks ────────────────────────────────────────


def test_check_frontmatter_valid(tmp_wiki):
    """check_frontmatter passes for valid frontmatter."""
    _create_page(tmp_wiki / "concepts" / "valid.md", "Valid", "Content.")
    issues = check_frontmatter(tmp_wiki)
    assert issues == []


def test_check_frontmatter_invalid(tmp_wiki):
    """check_frontmatter catches missing required fields."""
    page = tmp_wiki / "concepts" / "bad.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    # Missing title, source, type, confidence
    page.write_text(
        "---\ncreated: 2026-04-06\nupdated: 2026-04-06\n---\n\nBad page.\n",
        encoding="utf-8",
    )
    issues = check_frontmatter(tmp_wiki)
    assert len(issues) == 1
    assert issues[0]["check"] == "frontmatter"
    assert len(issues[0]["errors"]) > 0


# ── Source coverage checks ─────────────────────────────────────


def test_check_source_coverage(tmp_wiki, tmp_path):
    """check_source_coverage detects unreferenced raw sources."""
    raw_dir = tmp_path / "raw"
    articles_dir = raw_dir / "articles"
    articles_dir.mkdir(parents=True)
    (articles_dir / "referenced.md").write_text("referenced content")
    (articles_dir / "orphaned.md").write_text("orphaned content")

    _create_page(
        tmp_wiki / "summaries" / "test.md",
        "Test",
        "Content referencing raw/articles/referenced.md",
        page_type="summary",
    )
    issues = check_source_coverage(tmp_wiki, raw_dir)
    orphaned_sources = [i["source"] for i in issues]
    assert "raw/articles/orphaned.md" in orphaned_sources
    assert "raw/articles/referenced.md" not in orphaned_sources


def test_check_source_coverage_empty(tmp_wiki, tmp_path):
    """check_source_coverage returns empty when no raw sources exist."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    issues = check_source_coverage(tmp_wiki, raw_dir)
    assert issues == []


# ── Runner tests ───────────────────────────────────────────────


def test_run_all_checks(tmp_wiki, tmp_path):
    """run_all_checks produces structured report."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _create_page(tmp_wiki / "concepts" / "test.md", "Test", "No links.")
    report = run_all_checks(tmp_wiki, raw_dir)
    assert "checks_run" in report
    assert "total_issues" in report
    assert "summary" in report
    # Cycle 3 M10 + PR review R1 Codex MAJOR: wired `check_frontmatter_staleness`
    # into run_all_checks so count bumped 7 -> 8.
    # Cycle 15 AC7: wired `check_status_mature_stale` + `check_authored_by_drift`
    # so count bumped 8 -> 10.
    # Cycle 16 AC14: wired `check_duplicate_slugs` + `check_inline_callouts`
    # so count bumped 10 -> 12.
    assert len(report["checks_run"]) == 12


def test_run_all_checks_empty(tmp_wiki, tmp_path):
    """run_all_checks handles empty wiki."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    report = run_all_checks(tmp_wiki, raw_dir)
    assert report["total_issues"] == 0


def test_format_report():
    """format_report produces readable text output."""
    report = {
        "checks_run": [{"name": "dead_links", "issues": 1}],
        "total_issues": 1,
        "issues": [{"check": "dead_link", "severity": "error", "message": "Broken link"}],
        "summary": {"error": 1, "warning": 0, "info": 0},
    }
    text = format_report(report)
    assert "# Wiki Lint Report" in text
    assert "Broken link" in text
    assert "1 issues" in text


def test_format_report_clean():
    """format_report handles clean wiki."""
    report = {
        "checks_run": [{"name": "dead_links", "issues": 0}],
        "total_issues": 0,
        "issues": [],
        "summary": {"error": 0, "warning": 0, "info": 0},
    }
    text = format_report(report)
    assert "No issues found" in text


# ── augment._resolve_raw_dir branch coverage (cycle 43 AC11 fold from test_cycle13_augment_raw_dir.py) ─


from kb.lint import augment  # noqa: E402  — imported at fold site to keep above tests independent


class TestRawDirDerivation:
    """Cycle 13 — AC8/AC15: run_augment raw_dir derivation regression.

    When caller supplies a custom ``wiki_dir`` but omits ``raw_dir``, the
    orchestrator derives ``raw_dir = wiki_dir.parent / "raw"`` so augment runs
    stay project-isolated. Mirrors the existing ``effective_data_dir``
    derivation pattern.

    The four sub-tests pin the four branches of the resolution decision:
    1. wiki_dir override + raw_dir omitted → derived sibling
    2. explicit raw_dir → honoured (custom path)
    3. no kwargs → fallback to module-level RAW_DIR
    4. explicit raw_dir == module RAW_DIR → honoured (proves ``raw_dir is not
       None`` branch, not value identity)

    The branch logic is extracted to ``_resolve_raw_dir(wiki_dir, raw_dir)``
    for direct testability — same pattern as cycle-13's
    ``_record_verdict_gap_callout`` extraction.
    """

    def test_wiki_override_derives_raw_sibling(self, tmp_kb_env):
        """Branch 1: custom wiki_dir + raw_dir omitted → derive sibling."""
        wiki = tmp_kb_env / "wiki"
        resolved = augment._resolve_raw_dir(wiki, None)
        expected = wiki.parent / "raw"
        assert resolved == expected, f"expected derived raw_dir={expected}, got {resolved}"

    def test_explicit_raw_dir_honoured(self, tmp_kb_env):
        """Branch 2: explicit raw_dir → honoured even with wiki override."""
        wiki = tmp_kb_env / "wiki"
        custom_raw = tmp_kb_env / "custom-raw"
        resolved = augment._resolve_raw_dir(wiki, custom_raw)
        assert resolved == custom_raw, f"expected explicit custom_raw={custom_raw}, got {resolved}"

    def test_standard_run_uses_global_raw_dir(self, tmp_kb_env, monkeypatch):
        """Branch 3: default wiki_dir + no raw_dir → fallback to RAW_DIR."""
        patched_raw = tmp_kb_env / "raw-global"
        monkeypatch.setattr(augment, "RAW_DIR", patched_raw)
        # Use the module's WIKI_DIR (default) so the lexical comparison
        # ``wiki_dir != WIKI_DIR`` is False and the else-branch fires.
        resolved = augment._resolve_raw_dir(augment.WIKI_DIR, None)
        assert resolved == patched_raw, f"expected RAW_DIR={patched_raw}, got {resolved}"

    def test_explicit_raw_equals_global_honoured(self, tmp_kb_env, monkeypatch):
        """Branch 4: explicit raw_dir literally equals RAW_DIR → still honoured.

        Proves the branch is ``raw_dir is None`` (None-check), NOT a value
        identity check (``raw_dir == RAW_DIR``). A future refactor that
        accidentally changes the condition to value-comparison would derive
        a sibling instead of using the explicit pass.
        """
        wiki = tmp_kb_env / "wiki"
        patched_raw = tmp_kb_env / "raw-global"
        monkeypatch.setattr(augment, "RAW_DIR", patched_raw)
        resolved = augment._resolve_raw_dir(wiki, patched_raw)
        # MUST be the explicit value, NOT wiki.parent / "raw".
        assert resolved == patched_raw, (
            f"expected explicit RAW_DIR pass={patched_raw}, "
            f"got {resolved} (sibling-derivation regression?)"
        )

    def test_run_augment_invokes_resolver(self, tmp_kb_env, monkeypatch):
        """Integration sanity: run_augment routes raw_dir through _resolve_raw_dir.

        Patches the helper to a sentinel-returning spy and confirms run_augment
        produces the early-return summary expected when no proposals file
        exists, proving the helper IS reached on a real call.
        """
        wiki = tmp_kb_env / "wiki"
        sentinel = tmp_kb_env / "spy-raw"
        sentinel.mkdir()

        calls: list[tuple] = []
        real = augment._resolve_raw_dir

        def _spy(wd, rd):
            calls.append((wd, rd))
            return real(wd, rd) if rd is not None else sentinel

        monkeypatch.setattr(augment, "_resolve_raw_dir", _spy)
        # mode="execute" + no proposals.md => early return; spy must fire first.
        augment.run_augment(wiki_dir=wiki, mode="execute")

        assert calls, "spy never called — run_augment did not route through _resolve_raw_dir"
        assert calls[0][0] == wiki, f"unexpected wiki_dir arg: {calls[0]}"
        assert calls[0][1] is None, f"unexpected raw_dir arg: {calls[0]}"
