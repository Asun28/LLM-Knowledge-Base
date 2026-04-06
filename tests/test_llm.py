"""Tests for kb.utils.llm — retry logic, error handling, model tiering."""

from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest

from kb.config import MODEL_TIERS
from kb.utils.llm import LLMError, call_llm

# ── Helpers ──────────────────────────────────────────────────────


def _make_response(text: str) -> MagicMock:
    """Build a mock Anthropic Message with content[0].text."""
    block = MagicMock()
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
    """call_llm raises LLMError when API returns an empty content list."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_empty_response()
    mock_get_client.return_value = mock_client

    with pytest.raises(LLMError, match="Empty response"):
        call_llm("Say hello")


# ── Invalid tier ─────────────────────────────────────────────────


@patch("kb.utils.llm.get_client")
def test_call_llm_invalid_tier(mock_get_client):
    """call_llm raises KeyError for an unknown model tier."""
    mock_get_client.return_value = MagicMock()

    with pytest.raises(KeyError):
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
    """call_llm raises LLMError after exhausting all 3 retry attempts."""
    mock_client = MagicMock()
    rate_limit_err = _make_rate_limit_error()
    mock_client.messages.create.side_effect = [rate_limit_err] * 3
    mock_get_client.return_value = mock_client

    with pytest.raises(LLMError, match="Failed after 3 retries"):
        call_llm("Say hello")

    assert mock_client.messages.create.call_count == 3
    assert mock_sleep.call_count == 3


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


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 529])
@patch("time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_retryable_status_codes(mock_get_client, mock_sleep, status_code):
    """call_llm retries on retryable APIStatusError codes (429, 500, 502, 503, 529)."""
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
    """call_llm uses exponential backoff: 1s, 2s, 4s on successive retries."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [_make_rate_limit_error()] * 3
    mock_get_client.return_value = mock_client

    with pytest.raises(LLMError):
        call_llm("Say hello")

    # Verify the exponential backoff delays: 1*2^0=1, 1*2^1=2, 1*2^2=4
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [1.0, 2.0, 4.0]


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
    mock_client.messages.create.side_effect = [original_err] * 3
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
