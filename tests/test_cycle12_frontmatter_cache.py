import time

import yaml

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
