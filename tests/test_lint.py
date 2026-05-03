"""Tests for the lint module."""

from datetime import date, timedelta
from pathlib import Path

import frontmatter.default_handlers

from kb.lint import runner
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


def test_check_source_coverage_parses_yaml_once_per_page(tmp_project, monkeypatch):
    """check_source_coverage parses each page's YAML frontmatter exactly once.

    Cycle 9 contract: spy on `frontmatter.default_handlers.yaml.load` and
    assert the call count equals the number of wiki pages (3). A revert that
    re-opens frontmatter in a downstream loop would push the count > 3 and
    fail this test (cycle 50 fold from `test_cycle9_lint_checks.py`).
    """
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    articles_dir = raw_dir / "articles"

    for name in ("a", "b", "c"):
        (articles_dir / f"{name}.md").write_text(f"{name} source\n", encoding="utf-8")
        (wiki_dir / "concepts" / f"{name}.md").write_text(
            (
                "---\n"
                f'title: "{name.upper()}"\n'
                "source:\n"
                f'  - "raw/articles/{name}.md"\n'
                "created: 2026-04-18\n"
                "updated: 2026-04-18\n"
                "type: concept\n"
                "confidence: stated\n"
                "---\n\n"
                f"{name.upper()} references raw/articles/{name}.md in body text.\n"
            ),
            encoding="utf-8",
        )

    original_load = frontmatter.default_handlers.yaml.load

    def spy_load(*args, **kwargs):
        spy_load.call_count += 1
        return original_load(*args, **kwargs)

    spy_load.call_count = 0
    monkeypatch.setattr(frontmatter.default_handlers.yaml, "load", spy_load)

    issues = check_source_coverage(wiki_dir=wiki_dir, raw_dir=raw_dir)

    assert spy_load.call_count == 3
    orphan_sources = {issue["source"] for issue in issues if issue["check"] == "source_coverage"}
    assert orphan_sources == set()


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


def test_lint_runner_enumeration_order_unchanged(monkeypatch, tmp_path):
    """Cycle 45 AC34: run_all_checks emits checks in a stable contract order.

    Reverting the runner's check enumeration to a different sequence (e.g.,
    moving status_mature_stale before authored_by_drift) flips the asserted
    list and fails the test (cycle 50 fold from
    `test_cycle45_lint_runner_order_invariant.py`).
    """
    expected_check_order = [
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

    assert [check["name"] for check in report["checks_run"]] == expected_check_order


# ── augment._resolve_raw_dir branch coverage (cycle 43 AC11 fold) ─


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


# ── Test-suite lint guards (cycle 52 fold) ─
# Source: tests/test_cycle19_lint_redundant_patches.py (deleted in same commit).
# Cycle 19 AC18 — forward-looking lint guard. A test method that takes
# tmp_kb_env as a parameter MUST NOT also call
# monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", ...) because the
# fixture (cycle-18 D6 extension) already redirects HASH_MANIFEST under the
# tmp project. Method-scope detection (NOT file-scope) avoids the false
# positive where a sibling test class in the same file uses tmp_project.
# AC17 (cleanup of existing redundant patches) was DROPPED at plan-gate per
# cycle-17 L3 scope-narrowing rule.
# Per cycle-52 design-gate Q1 decision (b), the self-exclusion guard uses
# Path(__file__).resolve() so future receiver renames do not break exclusion.

import ast as _ast  # noqa: E402  — imported at fold site to keep above tests independent

_TESTS_DIR = Path(__file__).parent


def _method_uses_tmp_kb_env(node: _ast.FunctionDef) -> bool:
    return any(arg.arg == "tmp_kb_env" for arg in node.args.args)


def _method_body_text(source: str, node: _ast.FunctionDef) -> str:
    lines = source.splitlines()
    return "\n".join(lines[node.lineno - 1 : node.end_lineno])


def test_no_redundant_hash_manifest_patch_inside_tmp_kb_env_method() -> None:
    """A test method that takes tmp_kb_env MUST NOT also patch kb.compile.compiler.HASH_MANIFEST.

    Method-scope detection: walks each test file's AST, finds every
    ``def test_*(...tmp_kb_env...)`` function, and checks the function's
    own source body (NOT the whole file) for a literal HASH_MANIFEST patch.
    File-scope grep produces false positives when a sibling test class uses
    ``tmp_project`` and patches HASH_MANIFEST inside its own helper.
    """
    offenders: list[str] = []
    _self = Path(__file__).resolve()
    for py in _TESTS_DIR.glob("test_*.py"):
        if py.resolve() == _self:
            continue
        source = py.read_text(encoding="utf-8")
        try:
            tree = _ast.parse(source)
        except SyntaxError:
            continue
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.FunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            if not _method_uses_tmp_kb_env(node):
                continue
            body = _method_body_text(source, node)
            if "kb.compile.compiler.HASH_MANIFEST" in body and "monkeypatch.setattr" in body:
                offenders.append(f"{py.name}::{node.name}")
    assert not offenders, (
        "Test methods using tmp_kb_env must not also monkeypatch "
        "kb.compile.compiler.HASH_MANIFEST; the fixture (cycle-18 D6) already "
        f"redirects it. Offenders: {offenders}"
    )


# === Cycle 54 — folded from tests/test_cycle15_lint_status_mature.py ===
# Cycle 15 AC5/AC24 — check_status_mature_stale flags mature pages >90d stale.
from kb.lint.checks import check_status_mature_stale  # noqa: E402  — fold-site


def _write_status_mature_page(
    wiki_dir: Path,
    pid: str,
    updated_days_ago: int,
    status: str | None,
    page_type: str = "concept",
) -> Path:
    updated = (date.today() - timedelta(days=updated_days_ago)).isoformat()
    subdir = {
        "summary": "summaries",
        "concept": "concepts",
        "entity": "entities",
    }[page_type]
    path = wiki_dir / subdir / f"{pid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    status_line = f"status: {status}\n" if status is not None else ""
    path.write_text(
        f"""---
title: {pid}
source:
  - raw/articles/{pid}.md
created: 2026-01-01
updated: {updated}
type: {page_type}
confidence: stated
{status_line}---
body
""",
        encoding="utf-8",
    )
    return path


class TestMatureStale:
    def test_mature_91d_flagged(self, tmp_path):
        _write_status_mature_page(tmp_path, "cap-theorem", 91, status="mature")
        issues = check_status_mature_stale(wiki_dir=tmp_path)
        assert len(issues) == 1
        assert issues[0]["check"] == "status_mature_stale"
        assert issues[0]["severity"] == "warning"
        assert "cap-theorem" in issues[0]["page"]

    def test_mature_89d_not_flagged(self, tmp_path):
        _write_status_mature_page(tmp_path, "rag", 89, status="mature")
        issues = check_status_mature_stale(wiki_dir=tmp_path)
        assert issues == []

    def test_mature_365d_flagged(self, tmp_path):
        _write_status_mature_page(tmp_path, "very-old", 365, status="mature")
        issues = check_status_mature_stale(wiki_dir=tmp_path)
        assert len(issues) == 1
        assert "365" in issues[0]["message"]


class TestStatusMatureStaleOtherStatusesIgnored:
    """AC24 — only status=mature fires this check."""

    def test_seed_91d_not_flagged(self, tmp_path):
        _write_status_mature_page(tmp_path, "seedling", 91, status="seed")
        assert check_status_mature_stale(wiki_dir=tmp_path) == []

    def test_developing_91d_not_flagged(self, tmp_path):
        _write_status_mature_page(tmp_path, "developing", 91, status="developing")
        assert check_status_mature_stale(wiki_dir=tmp_path) == []

    def test_evergreen_91d_not_flagged(self, tmp_path):
        _write_status_mature_page(tmp_path, "evergreen", 91, status="evergreen")
        assert check_status_mature_stale(wiki_dir=tmp_path) == []

    def test_missing_status_not_flagged(self, tmp_path):
        _write_status_mature_page(tmp_path, "no-status", 91, status=None)
        assert check_status_mature_stale(wiki_dir=tmp_path) == []


class TestStatusMatureStaleTodayOverride:
    """AC24 — deterministic testing via `today` kwarg."""

    def test_today_kwarg_controls_cutoff(self, tmp_path):
        # Page updated 2026-01-01; today forced to 2026-04-30 → 119d delta.
        p = tmp_path / "concepts" / "fixed.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            """---
title: fixed
source:
  - raw/articles/x.md
created: 2026-01-01
updated: 2026-01-01
type: concept
confidence: stated
status: mature
---
body
""",
            encoding="utf-8",
        )
        issues = check_status_mature_stale(wiki_dir=tmp_path, today=date(2026, 4, 30))
        assert len(issues) == 1
        # 2026-04-30 - 2026-01-01 = 119 days
        assert "119" in issues[0]["message"]


# === Cycle 54 — folded from tests/test_cycle45_package_constants_propagate_to_submodules.py ===
# Cycle 45 AC33 — package-level checks monkeypatches reach split submodules.


def _write_pkg_const_fold_page(path: Path, body: str = "body") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: Test\nupdated: 2026-01-01\n---\n{body}\n", encoding="utf-8")


def test_wiki_dir_patch_reaches_frontmatter_submodule(monkeypatch, tmp_path):
    import kb.lint.checks as _checks_mod
    from kb.lint.checks.frontmatter import check_frontmatter as _check_frontmatter

    wiki_dir = tmp_path / "patched-wiki"
    bad_page = wiki_dir / "concepts" / "bad.md"
    bad_page.parent.mkdir(parents=True, exist_ok=True)
    bad_page.write_text("---\ntitle: [unterminated\n---\nBody\n", encoding="utf-8")

    monkeypatch.setattr(_checks_mod, "WIKI_DIR", wiki_dir)

    issues = _check_frontmatter()

    assert issues
    assert issues[0]["page"] == "concepts/bad"


def test_raw_dir_and_source_type_dirs_patch_reaches_source_coverage(monkeypatch, tmp_path):
    from kb.lint import checks as _checks_mod
    from kb.lint.checks.consistency import check_source_coverage as _check_source_coverage

    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "concepts").mkdir(parents=True)
    raw_dir = tmp_path / "raw"
    article_dir = raw_dir / "articles"
    article_dir.mkdir(parents=True)
    (article_dir / "dangling.md").write_text("raw", encoding="utf-8")

    monkeypatch.setattr(_checks_mod, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(_checks_mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(_checks_mod, "SOURCE_TYPE_DIRS", {"article": article_dir})

    issues = _check_source_coverage()

    assert [issue["source"] for issue in issues] == ["raw/articles/dangling.md"]


def test_resolve_wikilinks_patch_reaches_dead_links_submodule(monkeypatch, tmp_path):
    import kb.lint.checks as _checks_mod
    from kb.lint.checks.dead_links import check_dead_links as _check_dead_links

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    monkeypatch.setattr(_checks_mod, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(
        _checks_mod,
        "resolve_wikilinks",
        lambda _wiki_dir: {"broken": [{"source": "concepts/a", "target": "missing"}]},
    )

    issues = _check_dead_links()

    assert issues[0]["target"] == "missing"


def test_atomic_text_write_patch_reaches_dead_link_fix_submodule(monkeypatch, tmp_path):
    import kb.lint.checks as _checks_mod
    from kb.lint.checks.dead_links import fix_dead_links as _fix_dead_links

    wiki_dir = tmp_path / "wiki"
    page = wiki_dir / "concepts" / "a.md"
    _write_pkg_const_fold_page(page, "See [[missing]].")
    writes: list[tuple[str, Path]] = []

    def fake_write(content: str, path: Path) -> None:
        writes.append((content, path))

    monkeypatch.setattr(_checks_mod, "atomic_text_write", fake_write)

    fixes = _fix_dead_links(wiki_dir, broken_links=[{"source": "concepts/a", "target": "missing"}])

    assert fixes
    assert writes == [(page.read_text(encoding="utf-8").replace("[[missing]]", "missing"), page)]


def test_parse_inline_callouts_patch_reaches_inline_submodule(monkeypatch, tmp_path):
    import kb.lint.checks as _checks_mod
    from kb.lint.checks.inline_callouts import check_inline_callouts as _check_inline_callouts

    wiki_dir = tmp_path / "wiki"
    page = wiki_dir / "concepts" / "a.md"
    _write_pkg_const_fold_page(page, "plain body")

    monkeypatch.setattr(
        _checks_mod,
        "parse_inline_callouts",
        lambda _content: [{"marker": "gap", "line": 7, "text": "> [!gap] patched"}],
    )

    out = _check_inline_callouts(wiki_dir, pages=[page])

    assert out == [
        {
            "page_id": "concepts/a",
            "marker": "gap",
            "line": 7,
            "text": "> [!gap] patched",
        }
    ]


# ── Duplicate-slug allowlist file load (cycle 61) ─


class TestDuplicateSlugAllowlistFileLoad:
    """Test _get_duplicate_slug_allowlist() loader with file-present, file-missing, and malformed cases."""

    def test_file_present_custom_takes_precedence(self, monkeypatch, tmp_kb_env):
        """Custom allowlist from file overrides in-code default."""
        import json
        import logging

        from kb.config import _get_duplicate_slug_allowlist
        from kb.lint.checks.duplicate_slug import check_duplicate_slugs

        # Write a custom allowlist file
        config_dir = tmp_kb_env / "config"
        config_dir.mkdir(exist_ok=True)
        allowlist_file = config_dir / "lint_allowlist.json"
        allowlist_file.write_text(
            json.dumps({
                "version": 1,
                "duplicate_slugs": [["a/x", "a/y"]],
            }),
            encoding="utf-8",
        )

        # Monkeypatch PROJECT_ROOT to use tmp_kb_env
        monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_kb_env)
        # Clear the lru_cache so it re-reads
        _get_duplicate_slug_allowlist.cache_clear()

        # Create wiki pages with those slugs
        wiki_dir = tmp_kb_env / "wiki"
        _create_page(wiki_dir / "a" / "x.md", "X", "content")
        _create_page(wiki_dir / "a" / "y.md", "Y", "content")

        # Check that the pair is allowlisted (no duplicate-slug issue)
        issues = check_duplicate_slugs(wiki_dir)
        dup_issues = [i for i in issues if i.get("check") == "duplicate_slug"]
        assert len(dup_issues) == 0, f"Pair should be allowlisted but got issues: {dup_issues}"

    def test_file_missing_fallback(self, monkeypatch, tmp_kb_env):
        """When file is missing, fallback to in-code default."""
        from kb.config import DUPLICATE_SLUG_ALLOWLIST, _get_duplicate_slug_allowlist

        monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_kb_env)
        _get_duplicate_slug_allowlist.cache_clear()

        result = _get_duplicate_slug_allowlist()
        assert result == DUPLICATE_SLUG_ALLOWLIST

    def test_malformed_json_fallback(self, monkeypatch, tmp_kb_env, caplog):
        """Malformed JSON falls back to in-code default and logs WARNING."""
        import logging

        from kb.config import DUPLICATE_SLUG_ALLOWLIST, _get_duplicate_slug_allowlist

        # Write invalid JSON
        config_dir = tmp_kb_env / "config"
        config_dir.mkdir(exist_ok=True)
        allowlist_file = config_dir / "lint_allowlist.json"
        allowlist_file.write_text("{not valid json", encoding="utf-8")

        monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_kb_env)
        _get_duplicate_slug_allowlist.cache_clear()

        with caplog.at_level(logging.WARNING):
            result = _get_duplicate_slug_allowlist()

        # Should fall back to default
        assert result == DUPLICATE_SLUG_ALLOWLIST

        # Should have logged a warning
        assert any("Could not load/parse allowlist file" in r.message for r in caplog.records)
