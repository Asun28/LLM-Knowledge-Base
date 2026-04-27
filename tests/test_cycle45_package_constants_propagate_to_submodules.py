"""Cycle 45 AC33: package-level checks monkeypatches reach split submodules."""

from __future__ import annotations

from pathlib import Path


def _write_page(path: Path, body: str = "body") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: Test\nupdated: 2026-01-01\n---\n{body}\n", encoding="utf-8")


def test_wiki_dir_patch_reaches_frontmatter_submodule(monkeypatch, tmp_path):
    import kb.lint.checks as checks
    from kb.lint.checks.frontmatter import check_frontmatter

    wiki_dir = tmp_path / "patched-wiki"
    bad_page = wiki_dir / "concepts" / "bad.md"
    bad_page.parent.mkdir(parents=True, exist_ok=True)
    bad_page.write_text("---\ntitle: [unterminated\n---\nBody\n", encoding="utf-8")

    monkeypatch.setattr(checks, "WIKI_DIR", wiki_dir)

    issues = check_frontmatter()

    assert issues
    assert issues[0]["page"] == "concepts/bad"


def test_raw_dir_and_source_type_dirs_patch_reaches_source_coverage(monkeypatch, tmp_path):
    from kb.lint import checks
    from kb.lint.checks.consistency import check_source_coverage

    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "concepts").mkdir(parents=True)
    raw_dir = tmp_path / "raw"
    article_dir = raw_dir / "articles"
    article_dir.mkdir(parents=True)
    (article_dir / "dangling.md").write_text("raw", encoding="utf-8")

    monkeypatch.setattr(checks, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(checks, "RAW_DIR", raw_dir)
    monkeypatch.setattr(checks, "SOURCE_TYPE_DIRS", {"article": article_dir})

    issues = check_source_coverage()

    assert [issue["source"] for issue in issues] == ["raw/articles/dangling.md"]


def test_resolve_wikilinks_patch_reaches_dead_links_submodule(monkeypatch, tmp_path):
    import kb.lint.checks as checks
    from kb.lint.checks.dead_links import check_dead_links

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    monkeypatch.setattr(checks, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(
        checks,
        "resolve_wikilinks",
        lambda _wiki_dir: {"broken": [{"source": "concepts/a", "target": "missing"}]},
    )

    issues = check_dead_links()

    assert issues[0]["target"] == "missing"


def test_atomic_text_write_patch_reaches_dead_link_fix_submodule(monkeypatch, tmp_path):
    import kb.lint.checks as checks
    from kb.lint.checks.dead_links import fix_dead_links

    wiki_dir = tmp_path / "wiki"
    page = wiki_dir / "concepts" / "a.md"
    _write_page(page, "See [[missing]].")
    writes: list[tuple[str, Path]] = []

    def fake_write(content: str, path: Path) -> None:
        writes.append((content, path))

    monkeypatch.setattr(checks, "atomic_text_write", fake_write)

    fixes = fix_dead_links(wiki_dir, broken_links=[{"source": "concepts/a", "target": "missing"}])

    assert fixes
    assert writes == [(page.read_text(encoding="utf-8").replace("[[missing]]", "missing"), page)]


def test_parse_inline_callouts_patch_reaches_inline_submodule(monkeypatch, tmp_path):
    import kb.lint.checks as checks
    from kb.lint.checks.inline_callouts import check_inline_callouts

    wiki_dir = tmp_path / "wiki"
    page = wiki_dir / "concepts" / "a.md"
    _write_page(page, "plain body")

    monkeypatch.setattr(
        checks,
        "parse_inline_callouts",
        lambda _content: [{"marker": "gap", "line": 7, "text": "> [!gap] patched"}],
    )

    out = check_inline_callouts(wiki_dir, pages=[page])

    assert out == [
        {
            "page_id": "concepts/a",
            "marker": "gap",
            "line": 7,
            "text": "> [!gap] patched",
        }
    ]
