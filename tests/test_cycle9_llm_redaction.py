"""Cycle 9 AC27 regression tests for LLM error secret redaction."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest

from kb.utils import llm


def _stub_http_response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code,
        request=httpx.Request("POST", "http://x"),
    )


def _install_raising_client(monkeypatch, error: Exception):
    messages = MagicMock()
    messages.create.side_effect = error
    monkeypatch.setattr(llm, "get_client", lambda: SimpleNamespace(messages=messages))
    monkeypatch.setattr(llm.time, "sleep", lambda _delay: None)
    return messages


def _minimal_kwargs() -> dict:
    return {"model": "claude-test", "max_tokens": 1, "messages": []}


def _bad_request_error(message: str) -> anthropic.BadRequestError:
    return anthropic.BadRequestError(
        message=message,
        response=_stub_http_response(400),
        body={"error": {"type": "invalid_request_error"}},
    )


def _api_status_error(status_code: int, message: str) -> anthropic.APIStatusError:
    return anthropic.APIStatusError(
        message=message,
        response=_stub_http_response(status_code),
        body={"error": {"type": "api_error"}},
    )


class _StringSecretRetryError(Exception):
    pass


def _api_status_503_every_attempt(monkeypatch, message: str):
    return _install_raising_client(monkeypatch, _api_status_error(503, message))


def _generic_retry_error_every_attempt(monkeypatch, message: str):
    original_timeout_error = llm.anthropic.APITimeoutError
    error = _StringSecretRetryError(message)
    messages = _install_raising_client(monkeypatch, error)
    monkeypatch.setattr(llm.anthropic, "APITimeoutError", _StringSecretRetryError)

    def warning_side_effect(*args, **kwargs):
        rendered = args[0] % args[1:] if args else ""
        if "giving up" in rendered:
            monkeypatch.setattr(llm.anthropic, "APITimeoutError", original_timeout_error)

    monkeypatch.setattr(llm.logger, "warning", warning_side_effect)
    return messages


@pytest.mark.parametrize(
    ("error_factory", "secret", "label", "expected_calls"),
    [
        (
            lambda monkeypatch, message: _install_raising_client(
                monkeypatch, _bad_request_error(message)
            ),
            "sk" + "-ant-" + "abcdefghijklmnopqrstuvwxyz0123456789",
            "ANTHROPIC_KEY",
            1,
        ),
        (
            lambda monkeypatch, message: _install_raising_client(
                monkeypatch, _api_status_error(418, message)
            ),
            "Bear" + "er " + "abcdefghijklmnopqrstuvwxyz0123456789.foo",
            "BEARER_TOKEN",
            1,
        ),
        (
            _api_status_503_every_attempt,
            "sk" + "-proj-" + "abcdefghijklmnopqrstuvwxyz0123456789",
            "OPENAI_KEY",
            llm.MAX_RETRIES + 1,
        ),
        (
            _generic_retry_error_every_attempt,
            "abcdef0123456789abcdef0123456789",
            "LONG_HEX",
            llm.MAX_RETRIES + 1,
        ),
    ],
)
def test_make_api_call_redacts_secrets_at_all_truncation_sites(
    monkeypatch,
    error_factory,
    secret,
    label,
    expected_calls,
):
    messages = error_factory(monkeypatch, f"upstream leaked {secret} in payload")

    with pytest.raises(llm.LLMError) as exc_info:
        llm._make_api_call(_minimal_kwargs(), "claude-test")

    rendered = str(exc_info.value)
    assert f"[REDACTED:{label}]" in rendered
    assert secret not in rendered
    assert messages.create.call_count == expected_calls


def test_redact_before_truncate_ordering(monkeypatch):
    secret = "sk" + "-ant-" + "abcdefghijklmnopqrstuvwxyz0123456789"
    message = f"{'x' * 485}{secret}{'y' * 150}"
    messages = _install_raising_client(monkeypatch, _bad_request_error(message))

    with pytest.raises(llm.LLMError) as exc_info:
        llm._make_api_call(_minimal_kwargs(), "claude-test")

    rendered = str(exc_info.value)
    assert "[REDACTED:ANTHROPIC_KEY]" in rendered
    assert secret not in rendered
    assert messages.create.call_count == 1
