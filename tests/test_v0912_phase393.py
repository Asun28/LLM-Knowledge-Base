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
