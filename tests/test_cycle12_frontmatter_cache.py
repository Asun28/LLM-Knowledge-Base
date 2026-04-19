import time
from datetime import date

import yaml

from kb.lint.checks import (
    check_frontmatter,
    check_frontmatter_staleness,
    check_staleness,
    check_stub_pages,
)
from kb.utils import pages


def _write_page(path, *, title="Test Page", body="Body text"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntitle: {title}\ntype: note\nconfidence: high\n---\n{body}\n",
        encoding="utf-8",
    )


def test_cache_hit_call_count(tmp_path, monkeypatch):
    pages.load_page_frontmatter.cache_clear()
    page_path = tmp_path / "page.md"
    _write_page(page_path)
    calls = 0
    real_load = pages.frontmatter.load

    def counting_load(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_load(*args, **kwargs)

    monkeypatch.setattr(pages.frontmatter, "load", counting_load)

    pages.load_page_frontmatter(page_path)
    pages.load_page_frontmatter(page_path)

    assert calls == 1


def test_mtime_invalidation(tmp_path, monkeypatch):
    pages.load_page_frontmatter.cache_clear()
    page_path = tmp_path / "page.md"
    _write_page(page_path)
    calls = 0
    real_load = pages.frontmatter.load

    def counting_load(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_load(*args, **kwargs)

    monkeypatch.setattr(pages.frontmatter, "load", counting_load)

    pages.load_page_frontmatter(page_path)
    original_mtime_ns = page_path.stat().st_mtime_ns
    for _ in range(10):
        page_path.touch()
        if page_path.stat().st_mtime_ns != original_mtime_ns:
            break
        time.sleep(0.01)
    pages.load_page_frontmatter(page_path)

    assert calls == 2


def test_parse_error_reraise_and_not_cached(tmp_path, monkeypatch):
    pages.load_page_frontmatter.cache_clear()
    page_path = tmp_path / "bad.md"
    page_path.write_text("---\ntitle: [unterminated\n---\nBody\n", encoding="utf-8")
    calls = 0
    real_load = pages.frontmatter.load

    def counting_load(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_load(*args, **kwargs)

    monkeypatch.setattr(pages.frontmatter, "load", counting_load)

    try:
        pages.load_page_frontmatter(page_path)
    except yaml.YAMLError:
        pass
    else:
        raise AssertionError("expected malformed frontmatter to raise yaml.YAMLError")

    try:
        pages.load_page_frontmatter(page_path)
    except yaml.YAMLError:
        pass
    else:
        raise AssertionError("expected malformed frontmatter to raise yaml.YAMLError")

    assert calls == 2


def test_load_all_pages_regression(tmp_path):
    pages.load_page_frontmatter.cache_clear()
    wiki_dir = tmp_path / "wiki"
    _write_page(wiki_dir / "concepts" / "alpha.md", title="Alpha", body="Alpha Body")
    _write_page(wiki_dir / "concepts" / "beta.md", title="Beta", body="Beta Body")
    (wiki_dir / "concepts" / "bad.md").write_text(
        "---\ntitle: [unterminated\n---\nBad Body\n",
        encoding="utf-8",
    )
    (wiki_dir / "concepts" / "notes.txt").write_text("skip me", encoding="utf-8")

    result = pages.load_all_pages(wiki_dir=wiki_dir)

    assert len(result) == 2
    by_title = {page["title"]: page for page in result}
    assert set(by_title) == {"Alpha", "Beta"}
    assert by_title["Alpha"]["content_lower"] == "alpha body"
    assert by_title["Alpha"]["path"] == str(wiki_dir / "concepts" / "alpha.md")
    assert by_title["Beta"]["content_lower"] == "beta body"
    assert by_title["Beta"]["path"] == str(wiki_dir / "concepts" / "beta.md")


def _write_valid_lint_page(path, *, title, body="Substantial body. " * 10):
    path.parent.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    path.write_text(
        f'---\ntitle: "{title}"\nsource:\n  - raw/articles/test.md\n'
        f"created: {today}\nupdated: {today}\ntype: concept\n"
        f"confidence: stated\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_batch_lint_frontmatter_load_uses_shared_cache(tmp_path, monkeypatch):
    pages.load_page_frontmatter.cache_clear()
    wiki_dir = tmp_path / "wiki"
    page_paths = [
        wiki_dir / "concepts" / "alpha.md",
        wiki_dir / "concepts" / "beta.md",
        wiki_dir / "concepts" / "gamma.md",
    ]
    for page_path in page_paths:
        _write_valid_lint_page(page_path, title=page_path.stem.title())

    calls = 0
    real_load = pages.frontmatter.load

    def counting_load(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_load(*args, **kwargs)

    monkeypatch.setattr(pages.frontmatter, "load", counting_load)

    check_staleness(wiki_dir=wiki_dir, pages=page_paths)
    check_frontmatter_staleness(wiki_dir=wiki_dir, pages=page_paths)
    check_frontmatter(wiki_dir=wiki_dir, pages=page_paths)
    check_stub_pages(wiki_dir=wiki_dir, pages=page_paths)

    assert calls == 3


def test_check_frontmatter_reports_malformed_page(tmp_path):
    pages.load_page_frontmatter.cache_clear()
    wiki_dir = tmp_path / "wiki"
    page_path = wiki_dir / "concepts" / "bad.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text("---\ntitle: [unterminated\n---\nBad body\n", encoding="utf-8")

    issues = check_frontmatter(wiki_dir=wiki_dir)

    assert any(
        issue["severity"] == "error"
        and (
            "Failed to parse frontmatter" in issue["message"] or "parse" in issue["message"].lower()
        )
        for issue in issues
    )
