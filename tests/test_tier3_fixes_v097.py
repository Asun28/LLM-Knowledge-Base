"""Tests for v0.9.7 tier-3 fixes: query fallback logging, affected_pages log level,
LLM error messages."""

import logging
from unittest.mock import MagicMock, patch

import anthropic


# ===========================================================================
# Fix 15 — Query returns [] for stopword-only queries (no fallback)
# ===========================================================================
class TestQueryStopwordFallbackLogging:
    """search_pages should return [] for stopword-only queries (no raw fallback)."""

    def test_returns_empty_on_stopword_only_query(self, caplog):
        """When all tokens are stopwords, search_pages returns [] with no fallback."""
        from kb.query.engine import search_pages

        fake_page = {
            "id": "concepts/test",
            "type": "concept",
            "confidence": "stated",
            "title": "Test Page",
            "content": "Some content here",
            "raw_content": "Some content here",
            "sources": [],
            "path": "wiki/concepts/test.md",
            "created": "2026-01-01",
            "updated": "2026-01-01",
        }

        with (
            patch("kb.query.engine.load_all_pages", return_value=[fake_page]),
            caplog.at_level(logging.DEBUG, logger="kb.query.engine"),
        ):
            # "the" and "is" and "a" are all stopwords
            result = search_pages("the is a")

        assert result == [], f"Expected [] for stopword-only query, got {result}"

    def test_no_log_on_normal_query(self, caplog):
        """Normal queries with non-stopword terms don't trigger fallback log."""
        from kb.query.engine import search_pages

        with (
            patch("kb.query.engine.load_all_pages", return_value=[]),
            caplog.at_level(logging.DEBUG, logger="kb.query.engine"),
        ):
            search_pages("machine learning transformers")

        assert not any("stopwords" in r.message for r in caplog.records)


# ===========================================================================
# Fix 16 — kb_affected_pages uses debug for expected failure
# ===========================================================================
class TestAffectedPagesLogLevel:
    """kb_affected_pages should use debug, not warning, for expected failures."""

    def test_shared_sources_failure_logs_debug(self, caplog):
        """When shared sources computation fails, it's logged at debug level."""
        from kb.mcp.quality import kb_affected_pages

        with (
            patch("kb.mcp.quality.load_all_pages", side_effect=RuntimeError("no data")),
            patch(
                "kb.compile.linker.build_backlinks",
                return_value={"concepts/test": ["entities/a"]},
            ),
            caplog.at_level(logging.DEBUG),
        ):
            result = kb_affected_pages("concepts/test")

        # Should still return backlinks even though shared sources failed
        assert "entities/a" in result
        # The failure should be logged at DEBUG, not WARNING
        shared_source_logs = [r for r in caplog.records if "shared sources" in r.message.lower()]
        for record in shared_source_logs:
            assert record.levelno == logging.DEBUG, (
                f"Expected DEBUG but got {record.levelname}: {record.message}"
            )


# ===========================================================================
# Fix 17 — LLM error messages distinguish error types
# ===========================================================================
class TestLlmErrorMessages:
    """LLMError should contain specific context about the failure type."""

    def _mock_client(self):
        """Create a mock Anthropic client."""
        client = MagicMock()
        return client

    def test_timeout_error_message(self):
        """Timeout errors should mention 'Timeout' in the message."""
        from kb.utils.llm import LLMError, call_llm

        with patch("kb.utils.llm.get_client") as mock_get:
            client = self._mock_client()
            mock_get.return_value = client
            client.messages.create.side_effect = anthropic.APITimeoutError(request=MagicMock())

            try:
                call_llm("test prompt", tier="scan")
                assert False, "Should have raised LLMError"
            except LLMError as e:
                assert "Timeout" in str(e)
                assert "scan" not in str(e) or "haiku" in str(e).lower() or "retries" in str(e)

    def test_rate_limit_error_message(self):
        """Rate limit errors should mention 'Rate limited' in the message."""
        from kb.utils.llm import LLMError, call_llm

        with patch("kb.utils.llm.get_client") as mock_get:
            client = self._mock_client()
            mock_get.return_value = client
            response = MagicMock()
            response.status_code = 429
            response.headers = {}
            client.messages.create.side_effect = anthropic.RateLimitError(
                message="rate limited",
                response=response,
                body=None,
            )

            try:
                call_llm("test prompt", tier="scan")
                assert False, "Should have raised LLMError"
            except LLMError as e:
                assert "Rate limited" in str(e)

    def test_connection_error_message(self):
        """Connection errors should mention 'Connection failed' in the message."""
        from kb.utils.llm import LLMError, call_llm

        with patch("kb.utils.llm.get_client") as mock_get:
            client = self._mock_client()
            mock_get.return_value = client
            client.messages.create.side_effect = anthropic.APIConnectionError(request=MagicMock())

            try:
                call_llm("test prompt", tier="scan")
                assert False, "Should have raised LLMError"
            except LLMError as e:
                assert "Connection failed" in str(e)

    def test_server_error_message(self):
        """Server errors (500/502/503) should include the status code."""
        from kb.utils.llm import LLMError, call_llm

        with patch("kb.utils.llm.get_client") as mock_get:
            client = self._mock_client()
            mock_get.return_value = client
            response = MagicMock()
            response.status_code = 503
            response.headers = {}
            client.messages.create.side_effect = anthropic.APIStatusError(
                message="overloaded",
                response=response,
                body=None,
            )

            try:
                call_llm("test prompt", tier="scan")
                assert False, "Should have raised LLMError"
            except LLMError as e:
                assert "503" in str(e)
                assert "API error" in str(e)
