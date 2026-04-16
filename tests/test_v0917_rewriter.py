"""Tests for multi-turn query rewriting (Phase 4)."""

from unittest.mock import patch

from kb.query.rewriter import rewrite_query


class TestRewriteQuery:
    def test_standalone_query_unchanged(self):
        result = rewrite_query("What is a transformer?", conversation_context="")
        assert result == "What is a transformer?"

    def test_returns_string(self):
        # Mock call_llm so this test does not require a real API key.
        # The question has a deictic word ("it") which triggers _should_rewrite.
        with patch("kb.query.rewriter.call_llm", return_value="How does attention work?"):
            result = rewrite_query(
                "How does it work?",
                conversation_context="User asked about attention mechanisms in transformers.",
            )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_no_context_returns_original(self):
        result = rewrite_query("Tell me more", conversation_context=None)
        assert result == "Tell me more"

    def test_empty_query(self):
        result = rewrite_query("", conversation_context="some context")
        assert result == ""
