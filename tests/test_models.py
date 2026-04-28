"""Tests for data models and frontmatter validation."""

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
from kb.utils.hashing import content_hash
from kb.utils.markdown import extract_raw_refs, extract_wikilinks


def test_extract_wikilinks():
    text = "See [[concepts/rag]] and [[entities/karpathy|Karpathy]] for details."
    links = extract_wikilinks(text)
    assert links == ["concepts/rag", "entities/karpathy"]


def test_extract_wikilinks_empty():
    assert extract_wikilinks("No links here.") == []


def test_extract_raw_refs():
    text = "Source: raw/articles/example.md and raw/papers/paper.pdf"
    refs = extract_raw_refs(text)
    assert "raw/articles/example.md" in refs
    assert "raw/papers/paper.pdf" in refs


def test_content_hash(tmp_path):
    f = tmp_path / "test.md"
    f.write_text("hello world")
    h = content_hash(f)
    assert isinstance(h, str)
    assert len(h) == 32
    # Same content → same hash
    assert content_hash(f) == h


# ── Cycle 12: load_page_frontmatter cache + lint integration (cycle 43 fold) ─


def _write_page_cycle12(path, *, title="Test Page", body="Body text"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntitle: {title}\ntype: note\nconfidence: high\n---\n{body}\n",
        encoding="utf-8",
    )


def test_cache_hit_call_count(tmp_path, monkeypatch):
    pages.load_page_frontmatter.cache_clear()
    page_path = tmp_path / "page.md"
    _write_page_cycle12(page_path)
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
    _write_page_cycle12(page_path)
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
    _write_page_cycle12(wiki_dir / "concepts" / "alpha.md", title="Alpha", body="Alpha Body")
    _write_page_cycle12(wiki_dir / "concepts" / "beta.md", title="Beta", body="Beta Body")
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


def _write_valid_lint_page_cycle12(path, *, title, body="Substantial body. " * 10):
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
        _write_valid_lint_page_cycle12(page_path, title=page_path.stem.title())

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


# ── Cycle 14 TASK 3: save_page_frontmatter wrapper (cycle 47 fold per AC9) ─
# Source: tests/test_cycle14_save_frontmatter.py (deleted in same commit).
# Per Step-5 design Condition 3: NO test calls load_page_frontmatter (read
# path); frontmatter.Post construction stays function-local; renamed source
# class TestAtomicWriteProof to TestSaveFrontmatterAtomicWrite per N1.
# Pinning save_page_frontmatter insertion-order + atomic-write contract per
# cycle-7 L1 (frontmatter sort_keys=False).

import frontmatter  # noqa: E402  # post-existing imports, fold-site

from kb.utils.pages import save_page_frontmatter  # noqa: E402  # fold-site


class TestSaveFrontmatterInsertionOrder:
    """Cycle 14 AC17(a) — 4+ non-alphabetical keys round-trip in insertion order."""

    def test_six_required_fields_order_preserved(self, tmp_path):
        target = tmp_path / "page.md"
        post = frontmatter.Post(content="body content\n")
        # Insertion order: title → source → created → updated → type → confidence
        post.metadata["title"] = "Hello"
        post.metadata["source"] = "raw/articles/hi.md"
        post.metadata["created"] = "2026-04-20"
        post.metadata["updated"] = "2026-04-20"
        post.metadata["type"] = "entity"
        post.metadata["confidence"] = "stated"

        save_page_frontmatter(target, post)

        text = target.read_text(encoding="utf-8")
        lines = text.splitlines()
        # Lines 1-6 inside frontmatter are keys in INSERTION order.
        assert lines[0] == "---"
        key_lines = [line.split(":", 1)[0] for line in lines[1:7]]
        assert key_lines == ["title", "source", "created", "updated", "type", "confidence"]

    def test_nonalphabetical_insertion_order(self, tmp_path):
        target = tmp_path / "weird.md"
        post = frontmatter.Post(content="weird\n")
        # Deliberately non-alphabetical insertion
        for key, value in [
            ("zebra", 1),
            ("apple", 2),
            ("mango", 3),
            ("banana", 4),
        ]:
            post.metadata[key] = value
        save_page_frontmatter(target, post)
        text = target.read_text(encoding="utf-8")
        keys_in_order = []
        in_fm = False
        for line in text.splitlines():
            if line == "---":
                if in_fm:
                    break
                in_fm = True
                continue
            if in_fm and ":" in line:
                keys_in_order.append(line.split(":", 1)[0])
        assert keys_in_order == ["zebra", "apple", "mango", "banana"]


class TestSaveFrontmatterBodyVerbatim:
    """Cycle 14 AC17(b) — body content verbatim including trailing newline."""

    def test_body_content_with_trailing_newline(self, tmp_path):
        target = tmp_path / "body.md"
        post = frontmatter.Post(content="Line 1\nLine 2\n\nLine 4\n")
        post.metadata["title"] = "T"
        save_page_frontmatter(target, post)
        text = target.read_text(encoding="utf-8")
        # The body follows the second `---` delimiter.
        assert "Line 1" in text
        assert "Line 4" in text

    def test_body_preserved_with_special_chars(self, tmp_path):
        target = tmp_path / "special.md"
        body = "body with > quote and `code` and [[wikilink]]\n"
        post = frontmatter.Post(content=body)
        post.metadata["title"] = "T"
        save_page_frontmatter(target, post)
        text = target.read_text(encoding="utf-8")
        assert "[[wikilink]]" in text
        assert "`code`" in text
        assert "> quote" in text


class TestSaveFrontmatterListValuedMetadataOrder:
    """Cycle 14 AC17(c) — list-valued metadata order preserved."""

    def test_source_list_order(self, tmp_path):
        target = tmp_path / "list.md"
        post = frontmatter.Post(content="x\n")
        post.metadata["title"] = "T"
        post.metadata["source"] = ["z.md", "a.md", "m.md"]
        save_page_frontmatter(target, post)
        loaded = frontmatter.load(str(target))
        assert loaded.metadata["source"] == ["z.md", "a.md", "m.md"]


class TestSaveFrontmatterExtraKeysPreserved:
    """Cycle 14 AC17(d) — custom metadata keys preserved."""

    def test_custom_keys_survive_roundtrip(self, tmp_path):
        target = tmp_path / "custom.md"
        post = frontmatter.Post(content="body\n")
        post.metadata["title"] = "T"
        post.metadata["type"] = "entity"
        post.metadata["last_augment_attempted"] = "2026-04-20T12:34:56Z"
        post.metadata["wikilinks"] = ["a", "b"]
        save_page_frontmatter(target, post)
        loaded = frontmatter.load(str(target))
        assert loaded.metadata["last_augment_attempted"] == "2026-04-20T12:34:56Z"
        assert loaded.metadata["wikilinks"] == ["a", "b"]


class TestSaveFrontmatterAtomicWrite:
    """Cycle 14 AC17(e) — writes atomically; no partial .tmp sibling on success.

    Renamed from source TestAtomicWriteProof per Step-5 N1 + Condition 3.
    """

    def test_no_tmp_sibling_left_after_success(self, tmp_path):
        target = tmp_path / "atomic.md"
        post = frontmatter.Post(content="body\n")
        post.metadata["title"] = "T"
        save_page_frontmatter(target, post)

        # atomic_text_write creates a .tmp file then renames it to target.
        # Post-success, no .tmp sibling should remain.
        siblings = list(tmp_path.glob(f"{target.name}.tmp*"))
        assert siblings == []
        assert target.exists()

    def test_write_overwrites_existing(self, tmp_path):
        target = tmp_path / "overwrite.md"
        target.write_text("old content", encoding="utf-8")
        post = frontmatter.Post(content="new body\n")
        post.metadata["title"] = "T"
        save_page_frontmatter(target, post)
        text = target.read_text(encoding="utf-8")
        assert "new body" in text
        assert "old content" not in text
