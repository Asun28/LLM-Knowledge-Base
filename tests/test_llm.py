"""Tests for kb.utils.llm — retry logic, error handling, model tiering."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest

from kb.config import MODEL_TIERS
from kb.utils import llm
from kb.utils.llm import LLMError, call_llm

# ── Helpers ──────────────────────────────────────────────────────


def _make_response(text: str) -> MagicMock:
    """Build a mock Anthropic Message with a text content block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def _make_empty_response() -> MagicMock:
    """Build a mock Anthropic Message with empty content list."""
    response = MagicMock()
    response.content = []
    return response


def _make_api_status_error(status_code: int, message: str = "error") -> anthropic.APIStatusError:
    """Construct a real APIStatusError with the given status code."""
    resp = httpx.Response(status_code, request=httpx.Request("POST", "https://api.anthropic.com"))
    return anthropic.APIStatusError(message=message, response=resp, body=None)


def _make_rate_limit_error(message: str = "rate limited") -> anthropic.RateLimitError:
    """Construct a real RateLimitError (status 429)."""
    resp = httpx.Response(429, request=httpx.Request("POST", "https://api.anthropic.com"))
    return anthropic.RateLimitError(message=message, response=resp, body=None)


def _make_connection_error(message: str = "Connection error.") -> anthropic.APIConnectionError:
    """Construct a real APIConnectionError."""
    req = httpx.Request("POST", "https://api.anthropic.com")
    return anthropic.APIConnectionError(message=message, request=req)


def _make_timeout_error() -> anthropic.APITimeoutError:
    """Construct a real APITimeoutError."""
    req = httpx.Request("POST", "https://api.anthropic.com")
    return anthropic.APITimeoutError(request=req)


class _TelemetryFakeMessages:
    """Cycle 8 telemetry helper — captures kwargs passed to messages.create.

    Renamed from cycle-8 source `_FakeMessages` per cycle-50 Step-5 Q1
    decision (telemetry-scoped, prevents future helper-name collisions per
    R1 amendment). Used only by the telemetry tests in this file.
    """

    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _install_telemetry_client(monkeypatch, response):
    """Cycle 8 telemetry helper — install a fake Anthropic client.

    Renamed from cycle-8 source `_install_client` per cycle-50 Step-5 Q1.
    """
    messages = _TelemetryFakeMessages(response)
    monkeypatch.setattr(llm, "get_client", lambda: SimpleNamespace(messages=messages))
    return messages


# ── Success path ─────────────────────────────────────────────────


@patch("kb.utils.llm.get_client")
def test_call_llm_success(mock_get_client):
    """call_llm returns response text on successful API call."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_response("Hello from Claude")
    mock_get_client.return_value = mock_client

    result = call_llm("Say hello", tier="write")

    assert result == "Hello from Claude"
    mock_client.messages.create.assert_called_once()


# ── Empty response ───────────────────────────────────────────────


@patch("kb.utils.llm.get_client")
def test_call_llm_empty_response(mock_get_client):
    """call_llm raises LLMError when API returns no text content block."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_empty_response()
    mock_get_client.return_value = mock_client

    with pytest.raises(LLMError, match="No text content block"):
        call_llm("Say hello")


# ── Invalid tier ─────────────────────────────────────────────────


@patch("kb.utils.llm.get_client")
def test_call_llm_invalid_tier(mock_get_client):
    """call_llm raises ValueError for an unknown model tier."""
    mock_get_client.return_value = MagicMock()

    with pytest.raises(ValueError, match="Invalid tier"):
        call_llm("Say hello", tier="invalid")


# ── RateLimitError retry + success ───────────────────────────────


@patch("time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_rate_limit_retry(mock_get_client, mock_sleep):
    """call_llm retries on RateLimitError and succeeds on the third attempt."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _make_rate_limit_error(),
        _make_rate_limit_error(),
        _make_response("Success after retries"),
    ]
    mock_get_client.return_value = mock_client

    result = call_llm("Say hello")

    assert result == "Success after retries"
    assert mock_client.messages.create.call_count == 3
    assert mock_sleep.call_count == 2


# ── Max retries exceeded ─────────────────────────────────────────


@patch("time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_max_retries_exceeded(mock_get_client, mock_sleep):
    """call_llm raises LLMError after exhausting all 3 retries (4 total calls)."""
    mock_client = MagicMock()
    rate_limit_err = _make_rate_limit_error()
    mock_client.messages.create.side_effect = [rate_limit_err] * 4
    mock_get_client.return_value = mock_client

    with pytest.raises(LLMError, match="after 3 retries"):
        call_llm("Say hello")

    assert mock_client.messages.create.call_count == 4  # 1 initial + 3 retries
    assert mock_sleep.call_count == 3  # sleeps only between attempts, not after the final one


# ── Non-retryable APIStatusError ─────────────────────────────────


@patch("time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_non_retryable_error(mock_get_client, mock_sleep):
    """call_llm raises LLMError immediately on 401 without retrying."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = _make_api_status_error(401, "Unauthorized")
    mock_get_client.return_value = mock_client

    with pytest.raises(LLMError, match="API error.*401"):
        call_llm("Say hello")

    # Only one attempt — no retries for non-retryable status codes
    assert mock_client.messages.create.call_count == 1
    mock_sleep.assert_not_called()


# ── APIConnectionError retry + success ───────────────────────────


@patch("time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_connection_error_retry(mock_get_client, mock_sleep):
    """call_llm retries on APIConnectionError and succeeds."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _make_connection_error(),
        _make_response("Recovered from connection error"),
    ]
    mock_get_client.return_value = mock_client

    result = call_llm("Say hello")

    assert result == "Recovered from connection error"
    assert mock_client.messages.create.call_count == 2
    assert mock_sleep.call_count == 1


# ── Model tier selection ─────────────────────────────────────────


@pytest.mark.parametrize(
    "tier,expected_model",
    [
        ("scan", MODEL_TIERS["scan"]),
        ("write", MODEL_TIERS["write"]),
        ("orchestrate", MODEL_TIERS["orchestrate"]),
    ],
)
@patch("kb.utils.llm.get_client")
def test_call_llm_uses_correct_model(mock_get_client, tier, expected_model):
    """call_llm passes the correct model ID for each tier."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_response("ok")
    mock_get_client.return_value = mock_client

    call_llm("Say hello", tier=tier)

    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == expected_model


# ── APIStatusError retryable codes (500, 502, 503, 529) ─────────
# Note: 429 is handled by the RateLimitError handler, tested separately above.


@pytest.mark.parametrize("status_code", [500, 502, 503, 529])
@patch("time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_retryable_status_codes(mock_get_client, mock_sleep, status_code):
    """call_llm retries on retryable APIStatusError codes (500, 502, 503, 529)."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _make_api_status_error(status_code),
        _make_response("Recovered"),
    ]
    mock_get_client.return_value = mock_client

    result = call_llm("Say hello")

    assert result == "Recovered"
    assert mock_client.messages.create.call_count == 2
    assert mock_sleep.call_count == 1


# ── Non-retryable status codes raise immediately ─────────────────


@pytest.mark.parametrize("status_code", [400, 401, 403, 404])
@patch("time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_non_retryable_status_codes(mock_get_client, mock_sleep, status_code):
    """call_llm raises LLMError immediately on non-retryable status codes."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = _make_api_status_error(status_code)
    mock_get_client.return_value = mock_client

    with pytest.raises(LLMError, match="API error"):
        call_llm("Say hello")

    assert mock_client.messages.create.call_count == 1
    mock_sleep.assert_not_called()


# ── APITimeoutError retry ────────────────────────────────────────


@patch("time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_timeout_error_retry(mock_get_client, mock_sleep):
    """call_llm retries on APITimeoutError and succeeds."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _make_timeout_error(),
        _make_response("Recovered from timeout"),
    ]
    mock_get_client.return_value = mock_client

    result = call_llm("Say hello")

    assert result == "Recovered from timeout"
    assert mock_client.messages.create.call_count == 2
    assert mock_sleep.call_count == 1


# ── Exponential backoff delays ───────────────────────────────────


@patch("time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_exponential_backoff(mock_get_client, mock_sleep):
    """call_llm uses exponential backoff: 1s, 2s, 4s, 8s on successive retries."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [_make_rate_limit_error()] * 4
    mock_get_client.return_value = mock_client

    with pytest.raises(LLMError):
        call_llm("Say hello")

    # Cycle 2 item 6: delays now carry 0.5-1.5× jitter on top of the exponential
    # curve; assert each delay is within the jittered window and clamped to
    # RETRY_MAX_DELAY, not an exact value.
    from kb.utils.llm import RETRY_BASE_DELAY, RETRY_MAX_DELAY

    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert len(delays) == 3
    for i, d in enumerate(delays):
        raw = RETRY_BASE_DELAY * (2**i)
        lo = min(raw * 0.5, RETRY_MAX_DELAY)
        hi = min(raw * 1.5, RETRY_MAX_DELAY)
        assert lo <= d <= hi, f"attempt {i}: delay {d} outside jittered window [{lo}, {hi}]"


# ── System prompt forwarded ──────────────────────────────────────


@patch("kb.utils.llm.get_client")
def test_call_llm_system_prompt(mock_get_client):
    """call_llm includes system parameter when provided."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_response("ok")
    mock_get_client.return_value = mock_client

    call_llm("Say hello", system="You are helpful")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == "You are helpful"


@patch("kb.utils.llm.get_client")
def test_call_llm_no_system_prompt(mock_get_client):
    """call_llm does not include system parameter when empty string."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_response("ok")
    mock_get_client.return_value = mock_client

    call_llm("Say hello")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "system" not in call_kwargs


# ── LLMError chaining ────────────────────────────────────────────


@patch("time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_error_chaining_retryable(mock_get_client, mock_sleep):
    """LLMError raised after max retries chains the original exception."""
    mock_client = MagicMock()
    original_err = _make_rate_limit_error()
    mock_client.messages.create.side_effect = [original_err] * 4
    mock_get_client.return_value = mock_client

    with pytest.raises(LLMError) as exc_info:
        call_llm("Say hello")

    assert exc_info.value.__cause__ is original_err


@patch("kb.utils.llm.get_client")
def test_call_llm_error_chaining_non_retryable(mock_get_client):
    """LLMError raised on non-retryable error chains the original exception."""
    mock_client = MagicMock()
    original_err = _make_api_status_error(403, "Forbidden")
    mock_client.messages.create.side_effect = original_err
    mock_get_client.return_value = mock_client

    with pytest.raises(LLMError) as exc_info:
        call_llm("Say hello")

    assert exc_info.value.__cause__ is original_err


# ── max_tokens forwarded ─────────────────────────────────────────


@patch("kb.utils.llm.get_client")
def test_call_llm_max_tokens(mock_get_client):
    """call_llm forwards custom max_tokens to the API."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_response("ok")
    mock_get_client.return_value = mock_client

    call_llm("Say hello", max_tokens=8192)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["max_tokens"] == 8192


# ── Mixed error sequence ─────────────────────────────────────────


@patch("time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_mixed_transient_errors(mock_get_client, mock_sleep):
    """call_llm recovers from a mix of different transient error types."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _make_connection_error(),
        _make_timeout_error(),
        _make_response("Finally worked"),
    ]
    mock_get_client.return_value = mock_client

    result = call_llm("Say hello")

    assert result == "Finally worked"
    assert mock_client.messages.create.call_count == 3
    assert mock_sleep.call_count == 2


# ── _backoff_delay helper ────────────────────────────────────────


def test_backoff_delay_values():
    """_backoff_delay returns exponential values within the jitter window.

    Cycle 2 item 6: jitter adds 0.5-1.5× randomization; assert the window,
    not an exact value (the exact-value assertion broke with the jitter change
    and was a signature test, not a behaviour test per
    `feedback_test_behavior_over_signature`).
    """
    from kb.utils.llm import RETRY_BASE_DELAY, RETRY_MAX_DELAY, _backoff_delay

    for attempt in (0, 1, 2):
        raw = RETRY_BASE_DELAY * (2**attempt)
        lo = min(raw * 0.5, RETRY_MAX_DELAY)
        hi = min(raw * 1.5, RETRY_MAX_DELAY)
        d = _backoff_delay(attempt)
        assert lo <= d <= hi, f"attempt {attempt}: {d} outside [{lo}, {hi}]"


def test_backoff_delay_cap():
    """_backoff_delay never exceeds RETRY_MAX_DELAY regardless of attempt number."""
    from kb.utils.llm import RETRY_MAX_DELAY, _backoff_delay

    assert _backoff_delay(100) == RETRY_MAX_DELAY


# ── Telemetry: _make_api_call success path (cycle 50 fold) ──────


def test_make_api_call_success_logs_info_record_without_prompt_leak(monkeypatch, caplog):
    """Cycle 8 contract: _make_api_call emits a single INFO row with model,
    attempt, token counts, latency_ms — and NEVER includes the prompt or
    system text (cycle 50 fold from `test_cycle8_llm_telemetry.py`).
    """
    usage = SimpleNamespace(input_tokens=123, output_tokens=45)
    response = SimpleNamespace(usage=usage, content=[])
    fake_messages = _install_telemetry_client(monkeypatch, response)
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
    assert prompt not in message
    assert system not in message


def test_make_api_call_missing_usage_logs_zero_tokens(monkeypatch, caplog):
    """Cycle 8: when the SDK response has no `usage` attr, the telemetry row
    still emits with `tokens_in=0` / `tokens_out=0` (cycle 50 fold).
    """
    response = SimpleNamespace(content=[])
    _install_telemetry_client(monkeypatch, response)

    with caplog.at_level(logging.INFO, logger="kb.utils.llm"):
        llm._make_api_call({"model": "claude-test", "messages": []}, "claude-test")

    message = next(r.getMessage() for r in caplog.records if r.name == "kb.utils.llm")
    assert "tokens_in=0" in message
    assert "tokens_out=0" in message


# -- Cycle 93 fold from test_v0912_phase393.py (retry semantics subset) --
# Helper renamed _make_rate_limit_error -> _make_rate_limit_error_p393 (receiver collision).


def _make_rate_limit_error_p393():
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
            raise _make_rate_limit_error_p393()

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
            raise _make_rate_limit_error_p393()

        monkeypatch.setattr(client.messages, "create", fake_create)

        with pytest.raises(llm_mod.LLMError):
            llm_mod._make_api_call({"model": "x", "max_tokens": 10, "messages": []}, "x")


# -- Cycle 93 fold from test_phase4_audit_observability.py (LLM retry logging subset) --


def test_llm_last_retry_logs_giving_up(caplog):
    """On final attempt, log must say 'giving up', not 'retrying'."""
    from kb.utils import llm as llm_mod
    from kb.utils.llm import _make_api_call

    mock_resp = MagicMock(status_code=429, headers={})

    with patch.object(llm_mod, "get_client") as mock_client:
        mock_client.return_value.messages.create.side_effect = anthropic.RateLimitError(
            message="rate limited", response=mock_resp, body={}
        )
        with caplog.at_level(logging.WARNING, logger="kb.utils.llm"):
            with pytest.raises(Exception):
                _make_api_call({"model": "test", "messages": [], "max_tokens": 1}, "test-model")

    warning_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warning_messages, "No warnings were logged"
    last_warning = warning_messages[-1]
    assert "retrying" not in last_warning.lower(), (
        f"Last warning still says 'retrying': {last_warning!r}"
    )
    assert "giving up" in last_warning.lower(), (
        f"Last warning does not say 'giving up': {last_warning!r}"
    )


def test_llm_intermediate_retry_logs_retrying(caplog):
    """Before the final attempt, log must say 'retrying'."""
    from kb.utils import llm as llm_mod
    from kb.utils.llm import MAX_RETRIES, _make_api_call

    if MAX_RETRIES < 1:
        pytest.skip("Need at least 1 retry to test intermediate logs")

    call_count = [0]
    mock_resp = MagicMock(status_code=429, headers={})

    def side_effect(*args, **kwargs):
        call_count[0] += 1
        raise anthropic.RateLimitError(message="rate limited", response=mock_resp, body={})

    with patch.object(llm_mod, "get_client") as mock_client:
        with patch.object(llm_mod, "time") as mock_time:
            mock_time.sleep = MagicMock()
            mock_client.return_value.messages.create.side_effect = side_effect
            with caplog.at_level(logging.WARNING, logger="kb.utils.llm"):
                with pytest.raises(Exception):
                    _make_api_call({"model": "test", "messages": [], "max_tokens": 1}, "test-model")

    warning_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_messages) >= 2, "Expected at least 2 warnings (intermediate + final)"
    # First warning (not final attempt) must say retrying
    assert "retrying" in warning_messages[0].lower()


# -- Cycle 93 fold from test_v0914_phase395.py (llm retry) --


class TestMakeApiCallNoSleepAfterFinalRetry:
    """_make_api_call must not sleep after the final failed attempt."""

    def test_sleep_count_equals_max_retries(self, monkeypatch):
        import anthropic

        import kb.utils.llm as llm_mod

        sleep_calls = []
        monkeypatch.setattr("time.sleep", lambda d: sleep_calls.append(d))

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        mock_client.messages.create.side_effect = anthropic.RateLimitError(
            message="rate limited",
            response=mock_response,
            body={},
        )
        monkeypatch.setattr(llm_mod, "get_client", lambda: mock_client)

        with pytest.raises(llm_mod.LLMError):
            llm_mod._make_api_call({"model": "test", "max_tokens": 10, "messages": []}, "test")

        # Should sleep MAX_RETRIES times, not MAX_RETRIES + 1
        assert len(sleep_calls) == llm_mod.MAX_RETRIES
