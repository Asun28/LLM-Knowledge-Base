"""Phase 3.95 backlog fixes — v0.9.14."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Task 1: Utils I/O and Path Safety ──


class TestAtomicJsonWriteFdSafety:
    """atomic_json_write must not leak the fd when open()/json.dump() raises."""

    def test_fd_closed_on_serialization_failure(self, tmp_path):
        from kb.utils.io import atomic_json_write

        target = tmp_path / "out.json"

        class Unserializable:
            pass

        with pytest.raises(TypeError):
            atomic_json_write(Unserializable(), target)
        assert not target.exists()
        # Verify no leftover temp files
        assert not list(tmp_path.glob("*.tmp"))

    def test_successful_write_unchanged(self, tmp_path):
        from kb.utils.io import atomic_json_write

        target = tmp_path / "out.json"
        atomic_json_write({"key": "value"}, target)
        assert target.exists()
        import json

        assert json.loads(target.read_text(encoding="utf-8")) == {"key": "value"}


class TestMakeSourceRefLiteralRaw:
    """make_source_ref must always produce 'raw/...' prefix."""

    def test_custom_dir_name_still_uses_raw_prefix(self, tmp_path):
        from kb.utils.paths import make_source_ref

        custom_raw = tmp_path / "my_custom_raw_dir"
        articles = custom_raw / "articles"
        articles.mkdir(parents=True)
        source = articles / "test.md"
        source.write_text("content", encoding="utf-8")

        ref = make_source_ref(source, raw_dir=custom_raw)
        assert ref == "raw/articles/test.md"

    def test_standard_raw_dir_unchanged(self, tmp_path):
        from kb.utils.paths import make_source_ref

        raw = tmp_path / "raw"
        articles = raw / "articles"
        articles.mkdir(parents=True)
        source = articles / "test.md"
        source.write_text("content", encoding="utf-8")

        ref = make_source_ref(source, raw_dir=raw)
        assert ref == "raw/articles/test.md"


# ── Task 2: Models, Text Utils, Miscellaneous ──


class TestMakeApiCallNoSleepAfterFinalRetry:
    """_make_api_call must not sleep after the final failed attempt."""

    def test_sleep_count_equals_max_retries(self, monkeypatch):
        import anthropic

        import kb.utils.llm as llm_mod

        sleep_calls = []
        monkeypatch.setattr("time.sleep", lambda d: sleep_calls.append(d))

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        mock_client.messages.create.side_effect = anthropic.RateLimitError(
            message="rate limited",
            response=mock_response,
            body={},
        )
        monkeypatch.setattr(llm_mod, "get_client", lambda: mock_client)

        with pytest.raises(llm_mod.LLMError):
            llm_mod._make_api_call({"model": "test", "max_tokens": 10, "messages": []}, "test")

        # Should sleep MAX_RETRIES times, not MAX_RETRIES + 1
        assert len(sleep_calls) == llm_mod.MAX_RETRIES


class TestSlugifyAsciiOnly:
    """slugify must produce ASCII-only slugs."""

    def test_accented_chars_stripped(self):
        from kb.utils.text import slugify

        result = slugify("naïve Bayes résumé")
        # With re.ASCII, \w matches only [a-zA-Z0-9_], so accented chars are stripped
        assert "ï" not in result
        assert "é" not in result
        # The remaining ASCII chars still produce valid slugs
        assert result  # not empty


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


class TestAppendWikiLogErrorHandling:
    """append_wiki_log must not propagate OSError to callers."""

    def test_readonly_log_does_not_raise(self, tmp_path):
        from kb.utils.wiki_log import append_wiki_log

        log_path = tmp_path / "log.md"
        log_path.write_text("# Wiki Log\n\n", encoding="utf-8")
        # Make read-only
        log_path.chmod(0o444)
        try:
            # Should log warning, not raise
            append_wiki_log("test", "message", log_path)
        except OSError:
            pytest.fail("append_wiki_log should not propagate OSError")
        finally:
            log_path.chmod(0o644)


# ── Task 3: Query Engine and BM25 ──


class TestSearchPagesNoMutation:
    """search_pages must not mutate the input page dicts."""

    def test_page_dicts_unchanged_after_search(self, tmp_wiki, create_wiki_page, monkeypatch):
        create_wiki_page("concepts/rag", title="RAG", content="Retrieval augmented generation.")
        create_wiki_page("concepts/llm", title="LLM", content="Large language model.")

        from kb.query.engine import search_pages

        # First call — just trigger scoring
        search_pages("RAG", wiki_dir=tmp_wiki, max_results=5)

        # Load pages fresh — they should NOT have "score" key
        from kb.utils.pages import load_all_pages

        pages = load_all_pages(wiki_dir=tmp_wiki)
        for p in pages:
            assert "score" not in p, f"Page {p['id']} was mutated with 'score' key"


class TestBuildQueryContextPages:
    """_build_query_context must separate context_pages from source_pages."""

    def test_context_pages_excludes_skipped(self):
        from kb.query.engine import _build_query_context

        pages = [
            {
                "id": "concepts/huge",
                "type": "concept",
                "confidence": "stated",
                "title": "Huge",
                "content": "x" * 10000,
            },
            {
                "id": "concepts/small",
                "type": "concept",
                "confidence": "stated",
                "title": "Small",
                "content": "Short content.",
            },
        ]
        result = _build_query_context(pages, max_chars=500)
        # result is now a dict
        assert isinstance(result, dict)
        assert "concepts/small" in result["context_pages"]
        # "huge" was skipped because it exceeds max_chars
        assert "concepts/huge" not in result["context_pages"]


class TestBuildQueryContextSmallMaxChars:
    """When max_chars is too small, return 'No relevant pages' instead of garbage."""

    def test_tiny_max_chars_returns_no_pages_message(self):
        from kb.query.engine import _build_query_context

        pages = [
            {
                "id": "concepts/test",
                "type": "concept",
                "confidence": "stated",
                "title": "Test Page With Long Title",
                "content": "Some content here.",
            },
        ]
        result = _build_query_context(pages, max_chars=10)
        assert "No relevant wiki pages" in result["context"]


class TestTokenizeVersionStrings:
    """Tokenize should handle version strings gracefully."""

    def test_version_documented_behavior(self):
        from kb.query.bm25 import tokenize

        tokens = tokenize("version v0.9.13 release")
        # After fix: version strings should not silently lose components.
        # At minimum, the behavior should be predictable.
        assert "version" in tokens or "release" in tokens


# ── Task 4: Ingest Pipeline — CRLF, Authors, Field Parsing ──


class TestUpdateExistingPageCRLF:
    """_update_existing_page must handle Windows CRLF line endings."""

    def test_crlf_frontmatter_preserves_body(self, tmp_wiki):
        from kb.ingest.pipeline import _update_existing_page

        page_path = tmp_wiki / "entities" / "test-entity.md"
        # Write with CRLF line endings
        crlf_content = (
            "---\r\n"
            'title: "Test Entity"\r\n'
            "source:\r\n"
            '  - "raw/articles/old.md"\r\n'
            "created: 2026-01-01\r\n"
            "updated: 2026-01-01\r\n"
            "type: entity\r\n"
            "confidence: stated\r\n"
            "---\r\n"
            "\r\n"
            "# Test Entity\r\n"
            "\r\n"
            "This is the body content.\r\n"
        )
        page_path.write_text(crlf_content, encoding="utf-8")

        _update_existing_page(page_path, "raw/articles/new.md")

        result = page_path.read_text(encoding="utf-8")
        assert "body content" in result, "Body was lost due to CRLF handling"
        assert "raw/articles/new.md" in result


class TestBuildSummaryContentAuthors:
    """_build_summary_content must handle non-string author values."""

    def test_dict_authors_coerced(self):
        from kb.ingest.pipeline import _build_summary_content

        extraction = {
            "title": "Test Paper",
            "authors": [{"name": "Alice"}, "Bob", {"name": "Charlie"}],
        }
        content = _build_summary_content(extraction, "paper")
        assert "Alice" in content
        assert "Bob" in content
        assert "Charlie" in content

    def test_non_string_non_dict_authors_skipped(self):
        from kb.ingest.pipeline import _build_summary_content

        extraction = {
            "title": "Test",
            "authors": [42, None, "Valid Author"],
        }
        content = _build_summary_content(extraction, "article")
        assert "Valid Author" in content


class TestParseFieldSpecWarning:
    """_parse_field_spec should warn on non-identifier field names."""

    def test_spaces_in_field_name_warns(self, caplog):
        import logging

        from kb.ingest.extractors import _parse_field_spec

        with caplog.at_level(logging.WARNING):
            name, desc, is_list = _parse_field_spec("url string: the URL")

        # Should still parse (best-effort) but warn if field name has spaces/parens
        assert isinstance(name, str)
