"""Cycle 44 checks-package split regressions."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKS_DIR = ROOT / "src" / "kb" / "lint" / "checks"
SUBMODULES = (
    "frontmatter.py",
    "dead_links.py",
    "orphan.py",
    "cycles.py",
    "staleness.py",
    "duplicate_slug.py",
    "consistency.py",
    "inline_callouts.py",
)


def test_checks_package_structure_cycle44():
    assert CHECKS_DIR.is_dir()
    for name in SUBMODULES:
        path = CHECKS_DIR / name
        assert path.is_file(), f"missing {path}"
        assert "from kb.lint import checks" in path.read_text(encoding="utf-8")
    assert not (ROOT / "src" / "kb" / "lint" / "checks.py").exists()


def test_checks_package_reexports_match_former_flat_symbols_cycle44():
    from kb.lint import checks
    from kb.lint.checks.consistency import check_source_coverage

    expected = {
        "check_source_coverage",
        "check_dead_links",
        "fix_dead_links",
        "check_orphan_pages",
        "check_cycles",
        "check_staleness",
        "check_status_mature_stale",
        "check_authored_by_drift",
        "check_duplicate_slugs",
        "check_inline_callouts",
        "check_frontmatter",
        "check_frontmatter_staleness",
        "check_stub_pages",
        "parse_inline_callouts",
    }
    missing = {name for name in expected if not hasattr(checks, name)}
    assert not missing
    assert checks.check_source_coverage is check_source_coverage


def test_check_source_coverage_uses_patched_wiki_dir(tmp_path, monkeypatch):
    from kb.lint import checks
    from kb.lint.checks import consistency

    wiki = tmp_path / "wiki"
    page = wiki / "concepts" / "tmp-only.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        "---\n"
        "title: Tmp Only\n"
        "source: []\n"
        "created: 2026-01-01\n"
        "updated: 2026-01-01\n"
        "type: concept\n"
        "confidence: stated\n"
        "---\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    raw = tmp_path / "raw"
    raw.mkdir()

    seen_wiki_dirs: list[Path] = []
    processed_pages: list[Path] = []
    real_scan_wiki_pages = consistency.scan_wiki_pages

    def spy_scan_wiki_pages(wiki_dir: Path) -> list[Path]:
        seen_wiki_dirs.append(Path(wiki_dir))
        pages = real_scan_wiki_pages(wiki_dir)
        processed_pages.extend(pages)
        return pages

    monkeypatch.setattr(checks, "WIKI_DIR", wiki)
    monkeypatch.setattr(checks, "RAW_DIR", raw)
    monkeypatch.setattr(consistency, "scan_wiki_pages", spy_scan_wiki_pages)

    issues = checks.check_source_coverage()

    assert seen_wiki_dirs == [wiki]
    assert processed_pages == [page]
    assert issues == []
