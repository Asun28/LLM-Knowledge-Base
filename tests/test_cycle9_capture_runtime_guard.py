"""Regression for AC21 R1 M1 — runtime pre-flight inside `_extract_items_via_llm`.

Design condition for AC21 specified both (a) module-level
`assert CAPTURE_MAX_BYTES <= MAX_PROMPT_CHARS` AND (b) a runtime check inside
`_extract_items_via_llm`'s body so a legitimately-sized content combined with
an oversize template still raises before the LLM call. The module-level
`assert` vanishes under `python -O`; this test exercises the runtime guard.
"""

import pytest


def test_extract_items_via_llm_rejects_oversize_prompt(monkeypatch):
    """AC21 R1 M1: runtime pre-flight inside _extract_items_via_llm."""
    from kb import capture as capture_mod

    # Force the post-template prompt over MAX_PROMPT_CHARS without needing
    # actual CAPTURE_MAX_BYTES of content — patch the template. The placeholder
    # braces keep .format() happy; the rest is padding.
    oversize_template = "A" * (capture_mod.MAX_PROMPT_CHARS + 100) + "\n{max_items}{content}"
    monkeypatch.setattr(capture_mod, "_PROMPT_TEMPLATE", oversize_template)

    # Also stub call_llm_json so we fail loudly if the guard doesn't fire
    # (we should never reach the LLM call for an oversize prompt).
    def _should_not_be_called(*_args, **_kwargs):
        raise AssertionError("call_llm_json reached — runtime pre-flight did not fire")

    monkeypatch.setattr(capture_mod, "call_llm_json", _should_not_be_called)

    with pytest.raises(capture_mod.CaptureError) as exc:
        capture_mod._extract_items_via_llm("short body")
    msg = str(exc.value).lower()
    assert "too long" in msg or "max_prompt" in msg
