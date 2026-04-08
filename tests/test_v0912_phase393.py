"""Tests for Phase 3.93 backlog fixes (v0.9.12)."""

import httpx
import pytest


def _make_rate_limit_error():
    import anthropic

    resp = httpx.Response(429, request=httpx.Request("POST", "https://api.anthropic.com"))
    return anthropic.RateLimitError(message="rate limited", response=resp, body=None)


class TestLLMRetrySemantics:
    """utils/llm.py retry count and last_error safety."""

    def test_max_retries_means_retries_not_attempts(self, monkeypatch):
        """MAX_RETRIES=2 should make 3 total calls (1 initial + 2 retries)."""
        from kb.utils import llm as llm_mod

        calls = []

        def fake_create(**kwargs):
            calls.append(1)
            raise _make_rate_limit_error()

        monkeypatch.setattr(llm_mod, "MAX_RETRIES", 2)
        monkeypatch.setattr(llm_mod, "RETRY_BASE_DELAY", 0)
        client = llm_mod.get_client()
        monkeypatch.setattr(client.messages, "create", fake_create)

        with pytest.raises(llm_mod.LLMError):
            llm_mod._make_api_call({"model": "x", "max_tokens": 10, "messages": []}, "x")

        assert len(calls) == 3, f"Expected 3 total calls (1+2 retries), got {len(calls)}"

    def test_max_retries_zero_makes_one_call_and_raises_llmerror(self, monkeypatch):
        """MAX_RETRIES=0 should make exactly 1 call (range(1)) then raise LLMError."""
        from kb.utils import llm as llm_mod

        monkeypatch.setattr(llm_mod, "MAX_RETRIES", 0)
        monkeypatch.setattr(llm_mod, "RETRY_BASE_DELAY", 0)
        client = llm_mod.get_client()

        def fake_create(**kwargs):
            raise _make_rate_limit_error()

        monkeypatch.setattr(client.messages, "create", fake_create)

        with pytest.raises(llm_mod.LLMError):
            llm_mod._make_api_call({"model": "x", "max_tokens": 10, "messages": []}, "x")


class TestQueryEngine:
    """query/engine.py correctness fixes."""

    def test_search_pages_clamps_negative_max_results(self, tmp_wiki, create_wiki_page):
        """search_pages with max_results=-1 must not use negative slice."""
        from kb.query.engine import search_pages

        create_wiki_page(page_id="concepts/rag", title="RAG", wiki_dir=tmp_wiki)
        create_wiki_page(page_id="concepts/llm", title="LLM", wiki_dir=tmp_wiki)

        # With -1 clamped to 1, we get at most 1 result (not all-but-last)
        results = search_pages("rag llm", wiki_dir=tmp_wiki, max_results=-1)
        assert len(results) <= 1, f"Expected ≤1 result with max_results=-1, got {len(results)}"

    def test_build_query_context_falls_back_to_truncated_top_page(self):
        """_build_query_context must not return empty string when all pages exceed limit."""
        from kb.query.engine import _build_query_context

        big_page = {
            "id": "concepts/big",
            "title": "Big Page",
            "type": "concept",
            "confidence": "stated",
            "content": "x" * 200,
        }
        # limit is 50 chars — smaller than the page section header alone
        result = _build_query_context([big_page], max_chars=50)
        assert result != "", "Must not return empty string when top page exceeds limit"
        assert "big" in result.lower(), "Truncated fallback should contain page content"

    def test_query_wiki_accepts_and_forwards_max_results(self, monkeypatch):
        """query_wiki must accept max_results and forward it to search_pages."""
        from kb.query import engine as eng

        searched_with = []

        def fake_search(question, wiki_dir=None, max_results=10):
            searched_with.append(max_results)
            return []

        monkeypatch.setattr(eng, "search_pages", fake_search)

        eng.query_wiki("test question", max_results=5)
        assert searched_with == [5], (
            f"Expected search called with max_results=5, got {searched_with}"
        )
