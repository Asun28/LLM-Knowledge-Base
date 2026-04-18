from __future__ import annotations

import re
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from kb.config import PROJECT_ROOT


def test_extract_items_via_llm_uses_uuid_boundary_instead_of_static_fence(monkeypatch):
    from kb import capture

    token = "0123456789abcdef0123456789abcdef"
    prompt_seen = {}

    monkeypatch.setattr(capture._secrets, "token_hex", lambda _n: token)

    def fake_call_llm_json(prompt, *, tier, schema):
        prompt_seen["prompt"] = prompt
        return {"items": [], "filtered_out_count": 0}

    monkeypatch.setattr(capture, "call_llm_json", fake_call_llm_json)

    capture._extract_items_via_llm("benign content")

    prompt = prompt_seen["prompt"]
    assert f"<<<INPUT-{token}>>>" in prompt
    assert f"<<<END-INPUT-{token}>>>" in prompt
    assert "--- INPUT ---" not in prompt
    assert "--- END INPUT ---" not in prompt


def test_extract_items_via_llm_raises_on_boundary_collision_after_3_retries(monkeypatch):
    from kb import capture

    monkeypatch.setattr(capture._secrets, "token_hex", lambda _n: "abc")
    call_llm_json_spy = Mock(return_value={"items": [], "filtered_out_count": 0})
    monkeypatch.setattr(capture, "call_llm_json", call_llm_json_spy)

    with pytest.raises(ValueError, match="boundary collision after 3 retries"):
        capture._extract_items_via_llm("payload containing <<<INPUT-abc>>> collision")

    assert call_llm_json_spy.call_count == 0


def test_captured_at_reflects_submission_time_under_slow_llm(
    monkeypatch, tmp_captures_dir, reset_rate_limit
):
    from kb import capture
    from kb.capture import capture_items as kb_capture

    def slow_extract(_content):
        time.sleep(2)
        return {
            "items": [
                {
                    "title": "Slow decision",
                    "kind": "decision",
                    "body": "benign content",
                    "one_line_summary": "A slow decision was captured.",
                    "confidence": "stated",
                }
            ],
            "filtered_out_count": 0,
        }

    monkeypatch.setattr(capture, "_extract_items_via_llm", slow_extract)

    pre_llm = datetime.now(UTC)
    result = kb_capture("benign content")
    post_llm = datetime.now(UTC)

    assert result.rejected_reason is None
    assert len(result.items) == 1
    markdown = result.items[0].path.read_text(encoding="utf-8")
    match = re.search(r"^captured_at:\s*['\"]?([^'\"\s]+)['\"]?\s*$", markdown, re.MULTILINE)
    assert match is not None
    captured_at_iso = match.group(1)
    captured_at_dt = datetime.fromisoformat(captured_at_iso.replace("Z", "+00:00"))

    assert captured_at_dt - pre_llm <= timedelta(seconds=1)
    assert post_llm - captured_at_dt >= timedelta(seconds=1)


def test_claude_md_documents_raw_captures_exception():
    content = (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert "except raw/captures/" in content
    assert "deletion-pruning" in content
