"""Phase 3.97 Task 02 — Foundation: config, utils, models fixes."""

from datetime import date
from pathlib import Path

# ── config.py ──────────────────────────────────────────────────────────


class TestConfigConstants:
    """New config constants exist and have correct values."""

    def test_supported_source_extensions_exists(self):
        from kb.config import SUPPORTED_SOURCE_EXTENSIONS

        assert isinstance(SUPPORTED_SOURCE_EXTENSIONS, frozenset)
        assert ".md" in SUPPORTED_SOURCE_EXTENSIONS
        assert ".txt" in SUPPORTED_SOURCE_EXTENSIONS

    def test_valid_source_types_includes_comparison_synthesis(self):
        from kb.config import VALID_SOURCE_TYPES

        assert "comparison" in VALID_SOURCE_TYPES
        assert "synthesis" in VALID_SOURCE_TYPES
        assert "article" in VALID_SOURCE_TYPES

    def test_under_covered_type_threshold(self):
        from kb.config import UNDER_COVERED_TYPE_THRESHOLD

        assert UNDER_COVERED_TYPE_THRESHOLD == 3

    def test_stub_min_content_chars(self):
        from kb.config import STUB_MIN_CONTENT_CHARS

        assert STUB_MIN_CONTENT_CHARS == 100


# ── utils/text.py — slugify ────────────────────────────────────────────


class TestSlugifySpecialChars:
    """slugify must produce distinct slugs for C, C++, C#, .NET."""

    def test_c_plus_plus_distinct_from_c(self):
        from kb.utils.text import slugify

        assert slugify("C") != slugify("C++")

    def test_c_sharp_distinct_from_c(self):
        from kb.utils.text import slugify

        assert slugify("C") != slugify("C#")

    def test_dotnet_distinct_from_net(self):
        from kb.utils.text import slugify

        slug = slugify(".NET")
        assert slug and slug != "net"

    def test_fsharp_distinct_from_f(self):
        from kb.utils.text import slugify

        assert slugify("F#") != slugify("F")

    def test_normal_text_unchanged(self):
        from kb.utils.text import slugify

        assert slugify("OpenAI GPT-4") == "openai-gpt-4"


# ── utils/text.py — yaml_escape ────────────────────────────────────────


class TestYamlEscapeNEL:
    """yaml_escape must strip Unicode NEL (\\x85)."""

    def test_nel_stripped(self):
        from kb.utils.text import yaml_escape

        result = yaml_escape("hello\x85world")
        assert "\x85" not in result
        assert result == "helloworld"


# ── utils/io.py — CRLF fix ────────────────────────────────────────────


class TestAtomicWriteLF:
    """atomic_text_write must write LF line endings, not CRLF."""

    def test_atomic_text_write_uses_lf(self, tmp_path):
        from kb.utils.io import atomic_text_write

        test_file = tmp_path / "test.md"
        atomic_text_write("line1\nline2\n", test_file)
        raw = test_file.read_bytes()
        assert b"\r\n" not in raw
        assert b"\n" in raw

    def test_atomic_json_write_uses_lf(self, tmp_path):
        from kb.utils.io import atomic_json_write

        test_file = tmp_path / "test.json"
        atomic_json_write({"key": "value"}, test_file)
        raw = test_file.read_bytes()
        assert b"\r\n" not in raw


# ── utils/pages.py — load_all_pages int title ──────────────────────────


class TestLoadAllPagesIntTitle:
    """load_all_pages must coerce integer titles to strings."""

    def test_integer_title_coerced_to_string(self, tmp_wiki):
        page = tmp_wiki / "concepts" / "year-2024.md"
        page.write_text(
            "---\ntitle: 2024\nsource: []\ncreated: 2026-01-01\n"
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
            "Content about 2024.\n",
            encoding="utf-8",
        )

        from kb.utils.pages import load_all_pages

        pages = load_all_pages(tmp_wiki)
        assert len(pages) == 1
        assert isinstance(pages[0]["title"], str)
        assert pages[0]["title"] == "2024"


# ── utils/pages.py — normalize_sources ──────────────────────────────────


class TestNormalizeSources:
    """normalize_sources edge cases."""

    def test_empty_string_filtered(self):
        from kb.utils.pages import normalize_sources

        assert normalize_sources("") == []

    def test_list_with_empty_string_filtered(self):
        from kb.utils.pages import normalize_sources

        result = normalize_sources(["raw/a.md", "", "raw/b.md"])
        assert "" not in result
        assert len(result) == 2


# ── utils/markdown.py ──────────────────────────────────────────────────


class TestWikilinkPatternEmbedExclusion:
    """WIKILINK_PATTERN must not match ![[image.png]] embeds."""

    def test_embed_not_extracted(self):
        from kb.utils.markdown import extract_wikilinks

        text = "See ![[raw/assets/image.png]] for the diagram."
        links = extract_wikilinks(text)
        assert not links

    def test_normal_wikilink_still_works(self):
        from kb.utils.markdown import extract_wikilinks

        text = "See [[concepts/rag]] for details."
        links = extract_wikilinks(text)
        assert links == ["concepts/rag"]


class TestRawRefPatternCaseInsensitive:
    """_RAW_REF_PATTERN must match uppercase extensions."""

    def test_uppercase_pdf(self):
        from kb.utils.markdown import extract_raw_refs

        text = "See raw/papers/report.PDF for details."
        refs = extract_raw_refs(text)
        assert "raw/papers/report.PDF" in refs

    def test_mixed_case_csv(self):
        from kb.utils.markdown import extract_raw_refs

        text = "Data at raw/datasets/data.Csv is here."
        refs = extract_raw_refs(text)
        assert "raw/datasets/data.Csv" in refs


class TestExtractRawRefsHyphenLookbehind:
    """extract_raw_refs must not match raw/ preceded by hyphen."""

    def test_hyphen_before_raw_rejected(self):
        from kb.utils.markdown import extract_raw_refs

        text = "The slug is see-raw/articles/foo.md in compound."
        refs = extract_raw_refs(text)
        assert refs == []


# ── models/frontmatter.py — _is_valid_date ─────────────────────────────


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


# ── models/page.py ─────────────────────────────────────────────────────


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
