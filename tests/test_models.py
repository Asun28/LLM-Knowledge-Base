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
    """Cycle 14 AC17(b) — body content verbatim including trailing newline.

    Cycle-48 AC2: upgraded from substring-only to exact-byte body equality
    per C40-L3. Substring asserts would pass even if production stripped
    trailing newlines or blank lines; exact equality catches that revert.
    """

    def test_body_content_with_trailing_newline(self, tmp_path):
        target = tmp_path / "body.md"
        body = "Line 1\nLine 2\n\nLine 4\n"
        post = frontmatter.Post(content=body)
        post.metadata["title"] = "T"
        save_page_frontmatter(target, post)
        text = target.read_text(encoding="utf-8")
        # Cycle-48 AC2: pin exact body region so a production revert that
        # collapses internal blank lines or rewrites trailing-newline policy
        # fails the test. frontmatter.dumps inserts a blank line before the
        # body and strips trailing newlines (python-frontmatter convention),
        # so the expected region is "\n\n" + body.rstrip("\n").
        body_region = text.split("---", 2)[2]
        assert body_region == "\n\n" + body.rstrip("\n"), (
            f"body interior must round-trip; got {body_region!r}"
        )
        # Verify the meaningful content (interior blank line + every line)
        # round-trips — the contract this test pins.
        assert "Line 1\nLine 2\n\nLine 4" in body_region

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
    Cycle-48 AC3: upgraded to spy on `kb.utils.io.atomic_text_write` per
    C40-L3. The original assertion (no .tmp sibling) would also pass for a
    direct `open(target, "w").write(...)` revert; the spy directly pins the
    contract that `save_page_frontmatter` IS the atomic_text_write path.
    """

    def test_no_tmp_sibling_left_after_success(self, tmp_path, monkeypatch):
        target = tmp_path / "atomic.md"
        post = frontmatter.Post(content="body\n")
        post.metadata["title"] = "T"

        # Spy on the production atomic-write helper as bound in utils.pages.
        from kb.utils import pages as _pages_mod

        calls = []
        real_atomic = _pages_mod.atomic_text_write

        def _spy(content, path):
            calls.append((content, path))
            return real_atomic(content, path)

        monkeypatch.setattr(_pages_mod, "atomic_text_write", _spy)
        save_page_frontmatter(target, post)

        # Cycle-48 AC3: pin the contract that atomic_text_write IS the path.
        assert len(calls) == 1, (
            f"save_page_frontmatter must delegate to atomic_text_write exactly "
            f"once; got {len(calls)} calls"
        )
        assert calls[0][1] == target

        # Cycle 14 AC17(e) original contract: post-success, no .tmp sibling.
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


# === Cycle 54 — folded from tests/test_cycle8_models_validation.py ===
# Cycle 8 WikiPage / RawSource validation coverage; canonical home is
# tests/test_models.py for the data-model invariants.
import json as _json_cycle54  # noqa: E402  — fold-site imports per receiver convention
from pathlib import Path as _Path_cycle54  # noqa: E402
from types import SimpleNamespace as _SimpleNamespace_cycle54  # noqa: E402

import pytest as _pytest_cycle54  # noqa: E402

from kb.models import RawSource as _RawSource_cycle54  # noqa: E402
from kb.models import WikiPage as _WikiPage_cycle54  # noqa: E402


def _page_cycle54(**overrides):
    kwargs = {
        "path": _Path_cycle54("wiki/concepts/rag.md"),
        "title": "Retrieval Augmented Generation",
        "page_type": "concept",
        "sources": ["raw/articles/rag.md"],
        "confidence": "stated",
        "created": date(2026, 4, 1),
        "updated": date(2026, 4, 2),
        "wikilinks": ["concepts/llm"],
        "content_hash": "abc123",
    }
    kwargs.update(overrides)
    return _WikiPage_cycle54(**kwargs)


def test_wiki_page_rejects_invalid_page_type():
    with _pytest_cycle54.raises(ValueError, match="page_type"):
        _page_cycle54(page_type="bogus")


def test_wiki_page_rejects_invalid_confidence():
    with _pytest_cycle54.raises(ValueError, match="confidence"):
        _page_cycle54(confidence="certain")


def test_raw_source_rejects_invalid_source_type():
    with _pytest_cycle54.raises(ValueError, match="source_type"):
        _RawSource_cycle54(path=_Path_cycle54("raw/unknown/input.md"), source_type="unknown")


def test_wiki_page_to_dict_is_json_wire_shape():
    payload = _page_cycle54().to_dict()

    assert payload == {
        "path": str(_Path_cycle54("wiki/concepts/rag.md")),
        "title": "Retrieval Augmented Generation",
        "type": "concept",
        "sources": ["raw/articles/rag.md"],
        "confidence": "stated",
        "created": "2026-04-01",
        "updated": "2026-04-02",
        "wikilinks": ["concepts/llm"],
        "content_hash": "abc123",
    }
    _json_cycle54.dumps(payload)


def test_from_post_roundtrips_known_frontmatter_fields():
    post = _SimpleNamespace_cycle54(
        metadata={
            "title": "RAG",
            "type": "concept",
            "source": ["raw/articles/rag.md"],
            "confidence": "inferred",
            "created": "2026-04-03",
            "updated": date(2026, 4, 4),
            "wikilinks": ["concepts/retrieval"],
            "content_hash": "def456",
            "ignored": "metadata",
        }
    )

    page = _WikiPage_cycle54.from_post(post, _Path_cycle54("wiki/concepts/rag.md"))

    assert page.to_dict() == {
        "path": str(_Path_cycle54("wiki/concepts/rag.md")),
        "title": "RAG",
        "type": "concept",
        "sources": ["raw/articles/rag.md"],
        "confidence": "inferred",
        "created": "2026-04-03",
        "updated": "2026-04-04",
        "wikilinks": ["concepts/retrieval"],
        "content_hash": "def456",
    }


def test_from_post_requires_core_metadata():
    post = _SimpleNamespace_cycle54(metadata={"title": "RAG", "type": "concept"})

    with _pytest_cycle54.raises(ValueError, match="missing required metadata"):
        _WikiPage_cycle54.from_post(post, _Path_cycle54("wiki/concepts/rag.md"))


def test_from_post_strips_title_controls_and_traversal_sources():
    post = _SimpleNamespace_cycle54(
        metadata={
            "title": "‮RAG\x00 Notes⁩",
            "type": "concept",
            "source": ["../../../etc/passwd", "/tmp/secret.md", "raw/articles/rag.md"],
            "confidence": "stated",
        }
    )

    page = _WikiPage_cycle54.from_post(post, _Path_cycle54("wiki/concepts/rag.md"))

    assert page.title == "RAG Notes"
    assert page.sources == ["raw/articles/rag.md"]


# ═══════════════════════════════════════════════════════════════════════
# Cycle 78 freeze-and-fold — moved verbatim from tests/test_v0916_task02.py
# (models/frontmatter.py + models/page.py parts). Only deviation:
# fold-site `Path` import (receiver only has the _Path_cycle54 alias).
# ═══════════════════════════════════════════════════════════════════════

from pathlib import Path  # noqa: E402  — fold-site import (cycle 78)


class TestIsValidDate:
    """_is_valid_date must reject non-ISO strings."""

    def test_valid_iso_date_string(self):
        from kb.models.frontmatter import _is_valid_date

        assert _is_valid_date("2026-04-11") is True

    def test_empty_string_invalid(self):
        from kb.models.frontmatter import _is_valid_date

        assert _is_valid_date("") is False

    def test_non_date_string_invalid(self):
        from kb.models.frontmatter import _is_valid_date

        assert _is_valid_date("not-a-date") is False

    def test_date_object_valid(self):
        from kb.models.frontmatter import _is_valid_date

        assert _is_valid_date(date(2026, 4, 11)) is True

    def test_integer_invalid(self):
        from kb.models.frontmatter import _is_valid_date

        assert _is_valid_date(2024) is False


class TestPageModelConsistency:
    """RawSource and WikiPage content_hash must use same sentinel."""

    def test_raw_source_default_hash_is_none(self):
        from kb.models.page import RawSource

        rs = RawSource(path=Path("test"), source_type="article")
        assert rs.content_hash is None

    def test_wiki_page_default_hash_is_none(self):
        from kb.models.page import WikiPage

        wp = WikiPage(path=Path("test"), title="T", page_type="entity")
        assert wp.content_hash is None


# -- Cycle 92 fold from test_v0915_task01.py (pages/markdown/hashing/frontmatter subset) --
# ── Fix 1.3: normalize_sources dict/int/float guard ─────────────


class TestNormalizeSourcesDictGuard:
    """Fix 1.3 — normalize_sources rejects non-list iterables."""

    def test_dict_returns_empty_list(self):
        from kb.utils.pages import normalize_sources

        assert normalize_sources({"key": "value"}) == []

    def test_int_returns_empty_list(self):
        from kb.utils.pages import normalize_sources

        assert normalize_sources(42) == []

    def test_float_returns_empty_list(self):
        from kb.utils.pages import normalize_sources

        assert normalize_sources(3.14) == []

    def test_bool_returns_empty_list(self):
        from kb.utils.pages import normalize_sources

        assert normalize_sources(True) == []

    def test_list_still_works(self):
        from kb.utils.pages import normalize_sources

        assert normalize_sources(["raw/articles/a.md"]) == ["raw/articles/a.md"]

    def test_string_still_works(self):
        from kb.utils.pages import normalize_sources

        assert normalize_sources("raw/articles/a.md") == ["raw/articles/a.md"]

    def test_none_still_works(self):
        from kb.utils.pages import normalize_sources

        assert normalize_sources(None) == []


# ── Fix 1.4: extract_raw_refs URL false positive ────────────────


class TestExtractRawRefsUrlFalsePositive:
    """Fix 1.4 — word-boundary lookbehind rejects mid-URL matches."""

    def test_url_false_positive_rejected(self):
        from kb.utils.markdown import extract_raw_refs

        text = "See https://example.com/raw/articles/test.md for details"
        result = extract_raw_refs(text)
        assert result == []

    def test_standalone_raw_ref_kept(self):
        from kb.utils.markdown import extract_raw_refs

        text = "Source: raw/articles/test.md"
        assert "raw/articles/test.md" in extract_raw_refs(text)

    def test_line_start_raw_ref_kept(self):
        from kb.utils.markdown import extract_raw_refs

        text = "raw/papers/paper.pdf is the source."
        assert "raw/papers/paper.pdf" in extract_raw_refs(text)

    def test_quoted_raw_ref_kept(self):
        from kb.utils.markdown import extract_raw_refs

        text = 'source: "raw/articles/example.md"'
        assert "raw/articles/example.md" in extract_raw_refs(text)

    def test_parenthesized_raw_ref_kept(self):
        from kb.utils.markdown import extract_raw_refs

        text = "see (raw/videos/demo.md) for details"
        assert "raw/videos/demo.md" in extract_raw_refs(text)


# ── Fix 1.5: WIKILINK_PATTERN triple brackets + length cap ──────


class TestWikilinkPatternTripleBrackets:
    """Fix 1.5 — triple brackets not matched; length capped at 200."""

    def test_triple_bracket_not_matched(self):
        from kb.utils.markdown import extract_wikilinks

        result = extract_wikilinks("[[[not-a-wikilink]]]")
        assert result == []

    def test_normal_wikilink_still_works(self):
        from kb.utils.markdown import extract_wikilinks

        result = extract_wikilinks("See [[concepts/rag]] for details")
        assert "concepts/rag" in result

    def test_display_text_wikilink_still_works(self):
        from kb.utils.markdown import extract_wikilinks

        result = extract_wikilinks("[[concepts/rag|RAG pattern]]")
        assert "concepts/rag" in result

    def test_length_cap_200(self):
        # Q_K_b fix (Phase 4.5 HIGH): cap raised from 200 to 500 chars.
        # A 201-char target now passes (accepted). Kept test name for traceability.
        from kb.utils.markdown import extract_wikilinks

        long_target = "a" * 201
        result = extract_wikilinks(f"[[{long_target}]]")
        assert len(result) == 1, "201-char target should be accepted (cap is now 500)"

    def test_length_exactly_200_accepted(self):
        from kb.utils.markdown import extract_wikilinks

        target = "a" * 200
        result = extract_wikilinks(f"[[{target}]]")
        assert len(result) == 1

    def test_length_exactly_500_accepted(self):
        # Q_K_b fix (Phase 4.5 HIGH): 500-char target accepted (at cap boundary).
        from kb.utils.markdown import extract_wikilinks

        target = "a" * 500
        result = extract_wikilinks(f"[[{target}]]")
        assert len(result) == 1, "500-char target should be accepted (at cap boundary)"

    def test_length_501_rejected(self):
        # Q_K_b fix (Phase 4.5 HIGH): 501-char target rejected.
        from kb.utils.markdown import extract_wikilinks

        target = "a" * 501
        result = extract_wikilinks(f"[[{target}]]")
        assert result == [], "501-char target should be rejected (exceeds 500-char cap)"

    def test_quadruple_bracket_not_matched(self):
        from kb.utils.markdown import extract_wikilinks

        result = extract_wikilinks("[[[[foo]]]]")
        assert result == []


# ── Fix 1.6: load_all_pages null dates ──────────────────────────


class TestLoadAllPagesNullDates:
    """Fix 1.6 — null dates yield '' not 'None'."""

    def test_null_updated_not_none_string(self, tmp_wiki):
        page = tmp_wiki / "concepts" / "test.md"
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2025-01-01\nupdated:\ntype: concept\nconfidence: stated\n---\n\nContent.",
            encoding="utf-8",
        )
        from kb.utils.pages import load_all_pages

        pages = load_all_pages(tmp_wiki)
        assert len(pages) == 1
        assert pages[0]["updated"] != "None"
        assert pages[0]["updated"] == ""

    def test_null_created_not_none_string(self, tmp_wiki):
        page = tmp_wiki / "concepts" / "test.md"
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created:\nupdated: 2025-01-01\ntype: concept\nconfidence: stated\n---\n\nContent.",
            encoding="utf-8",
        )
        from kb.utils.pages import load_all_pages

        pages = load_all_pages(tmp_wiki)
        assert len(pages) == 1
        assert pages[0]["created"] != "None"
        assert pages[0]["created"] == ""


# ── Fix 1.8: _page_id lowercase ─────────────────────────────────


class TestPageIdLowercase:
    """Fix 1.8 — _page_id lowercases to match graph/builder.py."""

    def test_lowercase_page_id(self, tmp_path):
        from kb.utils.pages import _page_id

        wiki = tmp_path / "wiki"
        page = wiki / "concepts" / "RAG-Pattern.md"
        result = _page_id(page, wiki)
        assert result == "concepts/rag-pattern"

    def test_already_lowercase(self, tmp_path):
        from kb.utils.pages import _page_id

        wiki = tmp_path / "wiki"
        page = wiki / "entities" / "openai.md"
        result = _page_id(page, wiki)
        assert result == "entities/openai"


# ── Fix 1.10: content_hash streaming ────────────────────────────


class TestContentHashStreaming:
    """Fix 1.10 — content_hash uses streaming (correctness test)."""

    def test_hash_same_result(self, tmp_path):
        """Hash value should be the same regardless of implementation."""
        import hashlib

        from kb.utils.hashing import content_hash

        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"hello world" * 10000)
        expected = hashlib.sha256(test_file.read_bytes()).hexdigest()[:32]
        assert content_hash(test_file) == expected

    def test_hash_small_file(self, tmp_path):
        from kb.utils.hashing import content_hash

        test_file = tmp_path / "small.txt"
        test_file.write_bytes(b"tiny")
        result = content_hash(test_file)
        assert len(result) == 32
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_empty_file(self, tmp_path):
        from kb.utils.hashing import content_hash

        test_file = tmp_path / "empty.txt"
        test_file.write_bytes(b"")
        result = content_hash(test_file)
        assert len(result) == 32


# ── Fix 1.13: validate_frontmatter date validation ──────────────


class TestValidateFrontmatterDates:
    """Fix 1.13 — date fields validated for type."""

    def test_invalid_created_date_type(self):
        from kb.models.frontmatter import validate_frontmatter

        post = frontmatter.Post(
            "",
            **{
                "title": "Test",
                "source": ["raw/articles/a.md"],
                "created": [2025, 1, 1],
                "updated": "2025-01-01",
                "type": "concept",
                "confidence": "stated",
            },
        )
        errors = validate_frontmatter(post)
        assert any("created" in e.lower() for e in errors)

    def test_invalid_updated_date_type(self):
        from kb.models.frontmatter import validate_frontmatter

        post = frontmatter.Post(
            "",
            **{
                "title": "Test",
                "source": ["raw/articles/a.md"],
                "created": "2025-01-01",
                "updated": {"year": 2025},
                "type": "concept",
                "confidence": "stated",
            },
        )
        errors = validate_frontmatter(post)
        assert any("updated" in e.lower() for e in errors)

    def test_valid_date_string_accepted(self):
        from kb.models.frontmatter import validate_frontmatter

        post = frontmatter.Post(
            "",
            **{
                "title": "Test",
                "source": ["raw/articles/a.md"],
                "created": "2025-01-01",
                "updated": "2025-01-01",
                "type": "concept",
                "confidence": "stated",
            },
        )
        errors = validate_frontmatter(post)
        assert not errors

    def test_valid_date_object_accepted(self):
        from kb.models.frontmatter import validate_frontmatter

        post = frontmatter.Post(
            "",
            **{
                "title": "Test",
                "source": ["raw/articles/a.md"],
                "created": date(2025, 1, 1),
                "updated": date(2025, 1, 1),
                "type": "concept",
                "confidence": "stated",
            },
        )
        errors = validate_frontmatter(post)
        assert not errors


# ── Fix 1.14: validate_frontmatter source items ─────────────────


class TestValidateFrontmatterSourceItems:
    """Fix 1.14 — source list items must all be strings."""

    def test_non_string_source_item(self):
        from kb.models.frontmatter import validate_frontmatter

        post = frontmatter.Post(
            "",
            **{
                "title": "Test",
                "source": ["raw/articles/a.md", 42],
                "created": "2025-01-01",
                "updated": "2025-01-01",
                "type": "concept",
                "confidence": "stated",
            },
        )
        errors = validate_frontmatter(post)
        assert any("string" in e.lower() for e in errors)

    def test_all_string_source_items_ok(self):
        from kb.models.frontmatter import validate_frontmatter

        post = frontmatter.Post(
            "",
            **{
                "title": "Test",
                "source": ["raw/articles/a.md", "raw/papers/b.pdf"],
                "created": "2025-01-01",
                "updated": "2025-01-01",
                "type": "concept",
                "confidence": "stated",
            },
        )
        errors = validate_frontmatter(post)
        assert not errors


# ── Fix 1.15: conftest.py fixture created parameter ─────────────


class TestConfestCreatedParameter:
    """Fix 1.15 — create_wiki_page fixture supports separate created date."""

    def test_created_parameter_in_frontmatter(self, create_wiki_page, tmp_wiki):
        page_path = create_wiki_page(
            "concepts/test",
            created="2024-01-01",
            updated="2025-06-15",
            wiki_dir=tmp_wiki,
        )
        post = frontmatter.load(str(page_path))
        assert str(post.metadata["created"]) == "2024-01-01"
        assert str(post.metadata["updated"]) == "2025-06-15"

    def test_created_defaults_to_updated(self, create_wiki_page, tmp_wiki):
        """When created is not specified, it should default to updated date."""
        page_path = create_wiki_page(
            "concepts/test2",
            updated="2025-06-15",
            wiki_dir=tmp_wiki,
        )
        post = frontmatter.load(str(page_path))
        # Both should be the same when only updated is specified
        assert str(post.metadata["created"]) == "2025-06-15"
        assert str(post.metadata["updated"]) == "2025-06-15"

    def test_created_defaults_to_today_when_neither_specified(self, create_wiki_page, tmp_wiki):
        """When neither is specified, both default to today."""
        page_path = create_wiki_page(
            "concepts/test3",
            wiki_dir=tmp_wiki,
        )
        post = frontmatter.load(str(page_path))
        today = date.today().isoformat()
        assert str(post.metadata["created"]) == today
        assert str(post.metadata["updated"]) == today

    def test_h9_create_wiki_page_requires_wiki_dir(self, create_wiki_page):
        """Regression: Phase 4.5 HIGH item H9 (create_wiki_page had optional wiki_dir default)."""
        import pytest

        with pytest.raises(TypeError):
            create_wiki_page("concepts/x", title="X", content="body.")


# -- Cycle 93 fold from test_v0913_phase394.py (utils.pages) --


class TestNormalizeSourcesTypeCheck:
    """utils/pages.py normalize_sources: non-string list elements filtered."""

    def test_none_in_list_filtered_out(self):
        """None elements in source list must be filtered."""
        from kb.utils.pages import normalize_sources

        result = normalize_sources([None, "raw/articles/a.md", None, "raw/articles/b.md"])
        assert result == ["raw/articles/a.md", "raw/articles/b.md"]

    def test_non_string_converted(self):
        """Non-string elements must be converted to str or dropped."""
        from kb.utils.pages import normalize_sources

        # At minimum, no AttributeError or TypeError
        result = normalize_sources(["raw/articles/a.md", 42])
        assert all(isinstance(s, str) for s in result)


class TestContentLowerFieldName:
    """utils/pages.py load_all_pages: field is named 'content_lower', not 'raw_content'."""

    def test_content_lower_key_present(self, tmp_wiki, create_wiki_page):
        """load_all_pages must return 'content_lower' key (not 'raw_content')."""
        from kb.utils.pages import load_all_pages

        create_wiki_page(
            page_id="concepts/rename-test",
            title="Rename Test",
            content="Hello World",
            wiki_dir=tmp_wiki,
        )
        pages = load_all_pages(tmp_wiki)
        assert len(pages) == 1
        assert "content_lower" in pages[0], "'content_lower' key missing"
        assert "raw_content" not in pages[0], "'raw_content' key must not be present"
        assert pages[0]["content_lower"] == "hello world"


# -- Cycle 93 fold from test_v0914_phase395.py (frontmatter + page model) --


class TestValidateFrontmatterSourceType:
    """validate_frontmatter must flag non-list and null source fields."""

    def test_source_null_flagged(self):
        import frontmatter as fm

        from kb.models.frontmatter import validate_frontmatter

        post = fm.Post("")
        post.metadata = {
            "title": "Test",
            "source": None,
            "created": "2026-01-01",
            "updated": "2026-01-01",
            "type": "concept",
            "confidence": "stated",
        }
        errors = validate_frontmatter(post)
        assert any("source" in e.lower() for e in errors)

    def test_source_integer_flagged(self):
        import frontmatter as fm

        from kb.models.frontmatter import validate_frontmatter

        post = fm.Post("")
        post.metadata = {
            "title": "Test",
            "source": 42,
            "created": "2026-01-01",
            "updated": "2026-01-01",
            "type": "concept",
            "confidence": "stated",
        }
        errors = validate_frontmatter(post)
        assert any("source" in e.lower() for e in errors)

    def test_valid_source_passes(self):
        import frontmatter as fm

        from kb.models.frontmatter import validate_frontmatter

        post = fm.Post("")
        post.metadata = {
            "title": "Test",
            "source": ["raw/articles/test.md"],
            "created": "2026-01-01",
            "updated": "2026-01-01",
            "type": "concept",
            "confidence": "stated",
        }
        errors = validate_frontmatter(post)
        assert not any("source" in e.lower() for e in errors)


class TestWikiPageContentHashDefault:
    """WikiPage.content_hash should default to None, not empty string."""

    def test_default_is_none(self):
        from kb.models.page import WikiPage

        page = WikiPage(path=Path("test.md"), title="Test", page_type="concept")
        assert page.content_hash is None


# -- Cycle 94 fold from test_v070.py (case-insensitive wikilinks + package export curation) --


# ── 2. Case-Insensitive Wikilinks ───────────────────────────────


def test_wikilinks_lowercase():
    """Wikilinks are normalized to lowercase."""
    from kb.utils.markdown import extract_wikilinks

    links = extract_wikilinks("See [[Concepts/RAG]] and [[ENTITIES/OpenAI]]")
    assert links == ["concepts/rag", "entities/openai"]


def test_wikilinks_with_label_lowercase():
    """Wikilinks with labels normalize the target to lowercase."""
    from kb.utils.markdown import extract_wikilinks

    links = extract_wikilinks("[[Concepts/RAG|Retrieval Augmented Gen]]")
    assert links == ["concepts/rag"]


def test_wikilinks_already_lowercase():
    """Lowercase wikilinks pass through unchanged."""
    from kb.utils.markdown import extract_wikilinks

    links = extract_wikilinks("[[concepts/rag]]")
    assert links == ["concepts/rag"]


# ── 10. Package export curation (cycle 51 fold from test_cycle8_package_exports.py) ─


def _run_export_import_probe(code: str):
    """Helper: run an `import` probe in a fresh subprocess against repo src/.

    Renamed from `_run_import_probe` per cycle-51 design Q2 (helper-name uniqueness
    in receiver). The 6 callers below use this helper.
    """
    import os
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(src_dir) if not existing else f"{src_dir}{os.pathsep}{existing}"
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_kb_top_level_exports_importable_in_fresh_subprocess():
    result = _run_export_import_probe(
        "from kb import ("
        "ingest_source, compile_wiki, query_wiki, build_graph, "
        "WikiPage, RawSource, LLMError, __version__"
        ")"
    )

    assert result.returncode == 0, result.stderr


def test_kb_top_level_all_is_curated():
    import kb

    # Cycle 20 AC3 — kb.errors taxonomy exports added: KBError + 5 subclasses.
    assert kb.__all__ == [
        "ingest_source",
        "compile_wiki",
        "query_wiki",
        "build_graph",
        "WikiPage",
        "RawSource",
        "LLMError",
        "KBError",
        "IngestError",
        "CompileError",
        "QueryError",
        "ValidationError",
        "StorageError",
        "__version__",
    ]


def test_utils_exports_importable_in_fresh_subprocess():
    result = _run_export_import_probe(
        "from kb.utils import ("
        "slugify, yaml_escape, yaml_sanitize, STOPWORDS, atomic_json_write, "
        "atomic_text_write, file_lock, content_hash, extract_wikilinks, "
        "extract_raw_refs, FRONTMATTER_RE, append_wiki_log, load_all_pages, "
        "normalize_sources, make_source_ref"
        ")"
    )

    assert result.returncode == 0, result.stderr


def test_utils_all_is_curated():
    import kb.utils as utils

    assert utils.__all__ == [
        "slugify",
        "yaml_escape",
        "yaml_sanitize",
        "STOPWORDS",
        "atomic_json_write",
        "atomic_text_write",
        "file_lock",
        "content_hash",
        "extract_wikilinks",
        "extract_raw_refs",
        "FRONTMATTER_RE",
        "append_wiki_log",
        "load_all_pages",
        "normalize_sources",
        "make_source_ref",
    ]


def test_models_exports_importable_in_fresh_subprocess():
    result = _run_export_import_probe("from kb.models import WikiPage, RawSource")

    assert result.returncode == 0, result.stderr


def test_models_all_is_curated():
    import kb.models as models

    assert models.__all__ == ["WikiPage", "RawSource"]


# -- Cycle 94 fold from test_v090.py (extract_wikilinks normalization) --


# ── 10. Wikilink Normalization Consistency (Context7) ─────────────


def test_extract_wikilinks_already_strips_md():
    """extract_wikilinks strips .md suffix — linker/graph should not double-strip."""
    from kb.utils.markdown import extract_wikilinks

    text = "See [[concepts/rag.md]] and [[entities/openai]]"
    links = extract_wikilinks(text)
    assert "concepts/rag" in links
    assert "entities/openai" in links
    # Verify .md is already stripped (no double stripping needed)
    assert all(not link.endswith(".md") for link in links)


def test_extract_wikilinks_lowercases():
    """extract_wikilinks lowercases targets for case-insensitive matching."""
    from kb.utils.markdown import extract_wikilinks

    text = "See [[Concepts/RAG]] and [[Entities/OpenAI]]"
    links = extract_wikilinks(text)
    assert "concepts/rag" in links
    assert "entities/openai" in links
