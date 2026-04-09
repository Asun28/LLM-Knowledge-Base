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
