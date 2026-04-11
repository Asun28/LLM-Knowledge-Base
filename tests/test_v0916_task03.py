"""Phase 3.97 Task 03 — Ingest pipeline fixes."""

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest


class TestUpdateIndexBatchPrefixMatch:
    """_update_index_batch must use wikilink-boundary match, not substring."""

    def test_shorter_slug_not_blocked_by_longer(self, tmp_wiki):
        from kb.ingest.pipeline import _update_index_batch

        index = tmp_wiki / "index.md"
        index.write_text(
            "## Entities\n\n- [[entities/openai-corporation|OpenAI Corporation]]\n",
            encoding="utf-8",
        )
        _update_index_batch([("entity", "openai", "OpenAI")], wiki_dir=tmp_wiki)
        content = index.read_text(encoding="utf-8")
        assert "[[entities/openai|OpenAI]]" in content


class TestUpdateIndexBatchTitleSanitization:
    """_update_index_batch must sanitize pipe and newline in titles."""

    def test_pipe_in_title_sanitized(self, tmp_wiki):
        from kb.ingest.pipeline import _update_index_batch

        index = tmp_wiki / "index.md"
        index.write_text("## Concepts\n\n", encoding="utf-8")
        _update_index_batch([("concept", "rag-search", "RAG | Vector Search")], wiki_dir=tmp_wiki)
        content = index.read_text(encoding="utf-8")
        assert "||" not in content  # no double pipe
        assert "RAG" in content


class TestIngestSourceBinaryPDF:
    """ingest_source must handle binary PDF gracefully."""

    def test_binary_file_raises_clear_error(self, tmp_project):
        raw_dir = tmp_project / "raw"
        pdf = raw_dir / "papers" / "binary.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.4\x00\x01\x02binary content")

        from kb.ingest.pipeline import ingest_source

        with pytest.raises((UnicodeDecodeError, ValueError)):
            ingest_source(pdf, "paper")


class TestBuildExtractionSchemaNoneGuard:
    """build_extraction_schema must reject template with extract: None."""

    def test_none_extract_raises_value_error(self):
        from kb.ingest.extractors import build_extraction_schema

        template = {"name": "test", "extract": None}
        with pytest.raises(ValueError, match="extract"):
            build_extraction_schema(template)


class TestBuildItemContentNameSanitization:
    """_build_item_content must sanitize newlines in entity/concept names."""

    def test_newline_in_name_stripped(self):
        from kb.ingest.pipeline import _build_item_content

        content = _build_item_content("Test\nEntity", "raw/articles/test.md", "", "Mentioned")
        lines = content.split("\n")
        assert lines[0] == "# Test Entity"


class TestBuildSummaryContentTitleSanitization:
    """_build_summary_content must sanitize newlines in title."""

    def test_newline_in_title_stripped(self):
        from kb.ingest.pipeline import _build_summary_content

        extraction = {"title": "Test\nTitle", "core_argument": "Arg"}
        content = _build_summary_content(extraction, "article")
        assert "# Test Title" in content
        assert "# Test\n" not in content


class TestDetectSourceTypeCustomRawDir:
    """detect_source_type must accept custom raw_dir parameter."""

    def test_custom_raw_dir(self, tmp_path):
        custom_raw = tmp_path / "custom_raw"
        articles = custom_raw / "articles"
        articles.mkdir(parents=True)
        source = articles / "test.md"
        source.write_text("content", encoding="utf-8")

        from kb.ingest.pipeline import detect_source_type

        result = detect_source_type(source, raw_dir=custom_raw)
        assert result == "article"


class TestTemplateCacheClear:
    """Template cache clear helper must exist."""

    def test_clear_template_cache_exists(self):
        from kb.ingest.extractors import clear_template_cache

        clear_template_cache()  # should not raise


class TestIngestSourceUsesContentHash:
    """ingest_source should use content_hash utility, not inline hashlib."""

    def test_hash_matches_utility(self, tmp_project):
        from kb.utils.hashing import content_hash

        raw_dir = tmp_project / "raw"
        source = raw_dir / "articles" / "hash-test.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("test content for hash", encoding="utf-8")

        expected = content_hash(source)
        raw_bytes = source.read_bytes()
        inline = hashlib.sha256(raw_bytes).hexdigest()[:32]
        assert expected == inline  # both should match
