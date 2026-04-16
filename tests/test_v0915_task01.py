"""Tests for v0.9.15 Task 01 — Foundation: Utils, Config, Models.

Covers:
  1.1  yaml_escape control chars
  1.2  wiki_log newline injection
  1.3  normalize_sources dict/int/float guard
  1.4  extract_raw_refs URL false positive
  1.5  WIKILINK_PATTERN triple brackets + length cap
  1.6  load_all_pages null dates
  1.7  WIKI_SUBDIRS from config (single source of truth)
  1.8  _page_id lowercase
  1.9  atomic_json_write allow_nan=False
  1.10 content_hash streaming
  1.11 config.py MODEL_TIERS comment (verified by import, not a test)
  1.12 raw/assets/ confusing error
  1.13 validate_frontmatter date validation
  1.14 validate_frontmatter source items validation
  1.15 conftest.py fixture created parameter
"""

import json
from datetime import date

import frontmatter
import pytest

# ── Fix 1.1: yaml_escape control chars ──────────────────────────


class TestYamlEscapeControlChars:
    """Fix 1.1 — yaml_escape strips ASCII control characters."""

    def test_strips_bell_char(self):
        from kb.utils.text import yaml_escape

        assert "\x07" not in yaml_escape("hello\x07world")

    def test_strips_backspace(self):
        from kb.utils.text import yaml_escape

        assert "\x08" not in yaml_escape("hello\x08world")

    def test_strips_vertical_tab(self):
        from kb.utils.text import yaml_escape

        assert "\x0b" not in yaml_escape("hello\x0bworld")

    def test_strips_form_feed(self):
        from kb.utils.text import yaml_escape

        assert "\x0c" not in yaml_escape("hello\x0cworld")

    def test_strips_range_0x0e_to_0x1f(self):
        from kb.utils.text import yaml_escape

        for code in range(0x0E, 0x20):
            char = chr(code)
            result = yaml_escape(f"a{char}b")
            assert char not in result, f"0x{code:02x} not stripped"

    def test_strips_delete_char(self):
        from kb.utils.text import yaml_escape

        assert "\x7f" not in yaml_escape("hello\x7fworld")

    def test_preserves_normal_text(self):
        from kb.utils.text import yaml_escape

        assert yaml_escape("hello world") == "hello world"

    def test_preserves_existing_escapes(self):
        """Existing backslash/quote/newline escaping still works."""
        from kb.utils.text import yaml_escape

        result = yaml_escape('line1\nline2\t"quoted"')
        assert result == 'line1\\nline2\\t\\"quoted\\"'

    def test_strips_multiple_control_chars(self):
        from kb.utils.text import yaml_escape

        # Mix of control chars with normal text
        result = yaml_escape("\x01\x02hello\x0b\x7fworld")
        assert "hello" in result
        assert "world" in result
        for code in [0x01, 0x02, 0x0B, 0x7F]:
            assert chr(code) not in result


# ── Fix 1.2: wiki_log newline injection ─────────────────────────


class TestWikiLogNewlineInjection:
    """Fix 1.2 — newlines stripped from operation and message."""

    def test_newline_in_operation(self, tmp_path):
        from kb.utils.wiki_log import append_wiki_log

        log_path = tmp_path / "log.md"
        append_wiki_log("ingest\nevil", "normal message", log_path=log_path)
        content = log_path.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        # Should be 3 lines: header, blank, entry — not more
        assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}: {lines}"

    def test_newline_in_message(self, tmp_path):
        from kb.utils.wiki_log import append_wiki_log

        log_path = tmp_path / "log.md"
        append_wiki_log("ingest", "line1\nline2\nline3", log_path=log_path)
        content = log_path.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 3

    def test_carriage_return_stripped(self, tmp_path):
        from kb.utils.wiki_log import append_wiki_log

        log_path = tmp_path / "log.md"
        append_wiki_log("op\r\n", "msg\r\n", log_path=log_path)
        content = log_path.read_text(encoding="utf-8")
        assert "\r" not in content.split("\n")[-2]  # check the entry line


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
        from kb.utils.markdown import extract_wikilinks

        long_target = "a" * 201
        result = extract_wikilinks(f"[[{long_target}]]")
        assert result == []

    def test_length_exactly_200_accepted(self):
        from kb.utils.markdown import extract_wikilinks

        target = "a" * 200
        result = extract_wikilinks(f"[[{target}]]")
        assert len(result) == 1

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


# ── Fix 1.7: WIKI_SUBDIRS from config ──────────────────────────


class TestWikiSubdirsFromConfig:
    """Fix 1.7 — WIKI_SUBDIRS derived from config, not hardcoded."""

    def test_pages_subdirs_match_config(self):
        from kb.config import WIKI_SUBDIR_TO_TYPE
        from kb.utils.pages import WIKI_SUBDIRS

        assert set(WIKI_SUBDIRS) == set(WIKI_SUBDIR_TO_TYPE.keys())

    def test_graph_builder_uses_shared_subdirs(self):
        """graph/builder.py imports WIKI_SUBDIRS from utils.pages."""
        import inspect

        from kb.graph import builder

        # Should NOT contain a hardcoded tuple of subdirs
        assert "WIKI_SUBDIRS" in inspect.getsource(builder), (
            "graph/builder.py should import WIKI_SUBDIRS"
        )

    def test_evolve_analyzer_uses_shared_subdirs(self):
        """evolve/analyzer.py imports WIKI_SUBDIRS from utils.pages."""
        import inspect

        from kb.evolve import analyzer

        # The hardcoded dict should reference WIKI_SUBDIRS or WIKI_SUBDIR_TO_TYPE
        analyzer_src = inspect.getsource(analyzer)
        assert "WIKI_SUBDIRS" in analyzer_src or "WIKI_SUBDIR_TO_TYPE" in analyzer_src, (
            "evolve/analyzer.py should use WIKI_SUBDIRS from config"
        )


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


# ── Fix 1.9: atomic_json_write allow_nan=False ──────────────────


class TestAtomicJsonWriteNaN:
    """Fix 1.9 — NaN/Infinity rejected by atomic_json_write."""

    def test_nan_raises(self, tmp_path):
        from kb.utils.io import atomic_json_write

        with pytest.raises(ValueError):
            atomic_json_write({"score": float("nan")}, tmp_path / "test.json")

    def test_infinity_raises(self, tmp_path):
        from kb.utils.io import atomic_json_write

        with pytest.raises(ValueError):
            atomic_json_write({"score": float("inf")}, tmp_path / "test.json")

    def test_neg_infinity_raises(self, tmp_path):
        from kb.utils.io import atomic_json_write

        with pytest.raises(ValueError):
            atomic_json_write({"score": float("-inf")}, tmp_path / "test.json")

    def test_normal_values_still_work(self, tmp_path):
        from kb.utils.io import atomic_json_write

        out = tmp_path / "test.json"
        atomic_json_write({"score": 1.5, "name": "test"}, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["score"] == 1.5


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


# ── Fix 1.12: raw/assets/ confusing error ───────────────────────


class TestRawAssetsError:
    """Fix 1.12 — raw/assets/ gives a clear error."""

    def test_assets_dir_clear_error(self, tmp_path):
        from kb.ingest.pipeline import detect_source_type

        raw = tmp_path / "raw"
        assets = raw / "assets"
        assets.mkdir(parents=True)
        test_file = assets / "image.png"
        test_file.write_bytes(b"\x89PNG")

        # We need to patch RAW_DIR to use our tmp dir
        import kb.ingest.pipeline as pipeline

        orig = pipeline.RAW_DIR
        try:
            pipeline.RAW_DIR = raw
            with pytest.raises(ValueError, match="(?i)assets"):
                detect_source_type(test_file)
        finally:
            pipeline.RAW_DIR = orig


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
