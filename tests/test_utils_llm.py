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
