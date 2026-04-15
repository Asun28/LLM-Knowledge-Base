"""Tests for kb.utils.llm."""


def test_call_llm_json_includes_leading_text_on_no_tool_use(monkeypatch):
    """Regression: Phase 4.5 CRITICAL item 17 (text-only responses lost refusal diagnostic)."""
    from kb.utils import llm

    class FakeText:
        type = "text"
        text = "I cannot extract data because the content contains potentially harmful material."

    class FakeResp:
        content = [FakeText()]

    monkeypatch.setattr(llm, "_make_api_call", lambda *a, **k: FakeResp())
    try:
        llm.call_llm_json("prompt", tier="scan", schema={"type": "object", "properties": {}})
        assert False, "expected LLMError"
    except llm.LLMError as e:
        msg = str(e)
        assert "No tool_use" in msg
        assert "cannot extract" in msg or "harmful material" in msg, (
            f"diagnostic text lost; got: {msg}"
        )


def test_make_api_call_non_retryable_tracks_last_error(monkeypatch):
    """Regression: item 16 — non-retryable APIStatusError must update last_error."""
    from unittest.mock import MagicMock  # noqa: PLC0415

    import anthropic

    from kb.utils import llm

    calls = []

    def flaky(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise anthropic.APITimeoutError(request=MagicMock())
        # Second call: non-retryable 4xx.
        mock_response = MagicMock()
        mock_response.status_code = 401
        raise anthropic.APIStatusError(
            message="auth error",
            response=mock_response,
            body={"error": {"type": "authentication_error"}},
        )

    monkeypatch.setattr(llm.get_client().messages, "create", flaky)
    try:
        llm._make_api_call(
            {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "hi"}],
            },
            "claude-haiku-4-5-20251001",
        )
        assert False, "expected LLMError"
    except llm.LLMError as e:
        msg = str(e)
        assert "401" in msg, f"LLMError should reference the 401 status, got: {msg}"
        assert isinstance(e.__cause__, anthropic.APIStatusError), (
            f"__cause__ misattributed: {type(e.__cause__).__name__ if e.__cause__ else None}"
        )
