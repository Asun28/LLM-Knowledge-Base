"""Cycle 8 LLM success telemetry coverage."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from kb.utils import llm


class _FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _install_client(monkeypatch, response):
    messages = _FakeMessages(response)
    monkeypatch.setattr(llm, "get_client", lambda: SimpleNamespace(messages=messages))
    return messages


def test_make_api_call_success_logs_info_record_without_prompt_leak(monkeypatch, caplog):
    usage = SimpleNamespace(input_tokens=123, output_tokens=45)
    response = SimpleNamespace(usage=usage, content=[])
    fake_messages = _install_client(monkeypatch, response)
    prompt = "sensitive prompt text that must not appear in logs"
    system = "sensitive system text that must not appear in logs"
    kwargs = {
        "model": "claude-test",
        "max_tokens": 64,
        "messages": [{"role": "user", "content": prompt}],
        "system": system,
    }

    with caplog.at_level(logging.INFO, logger="kb.utils.llm"):
        returned = llm._make_api_call(kwargs, "claude-test")

    assert returned is response
    assert fake_messages.calls == [kwargs]
    records = [r for r in caplog.records if r.name == "kb.utils.llm" and r.levelno == logging.INFO]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "model=claude-test" in message
    assert "attempt=1" in message
    assert "tokens_in=123" in message
    assert "tokens_out=45" in message
    assert "latency_ms=" in message
    assert prompt[:30] not in message
    assert system[:30] not in message


def test_make_api_call_missing_usage_logs_zero_tokens(monkeypatch, caplog):
    response = SimpleNamespace(content=[])
    _install_client(monkeypatch, response)

    with caplog.at_level(logging.INFO, logger="kb.utils.llm"):
        llm._make_api_call({"model": "claude-test", "messages": []}, "claude-test")

    message = next(r.getMessage() for r in caplog.records if r.name == "kb.utils.llm")
    assert "tokens_in=0" in message
    assert "tokens_out=0" in message
