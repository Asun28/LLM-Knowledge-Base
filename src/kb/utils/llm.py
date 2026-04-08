"""Anthropic API wrapper with model tiering, retry, and timeout."""

import logging
import threading
import time

import anthropic

from kb.config import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT,
    LLM_RETRY_BASE_DELAY,
    LLM_RETRY_MAX_DELAY,
    MODEL_TIERS,
)

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility (tests import these from this module)
MAX_RETRIES = LLM_MAX_RETRIES
RETRY_BASE_DELAY = LLM_RETRY_BASE_DELAY
RETRY_MAX_DELAY = LLM_RETRY_MAX_DELAY
REQUEST_TIMEOUT = LLM_REQUEST_TIMEOUT

_client: anthropic.Anthropic | None = None
_client_lock = threading.Lock()


def get_client() -> anthropic.Anthropic:
    """Get a reusable Anthropic client (uses ANTHROPIC_API_KEY env var)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:  # double-check locking
                _client = anthropic.Anthropic(timeout=REQUEST_TIMEOUT, max_retries=0)
    return _client


def _resolve_model(tier: str) -> str:
    """Validate tier and return the model ID."""
    if tier not in MODEL_TIERS:
        raise ValueError(f"Invalid tier '{tier}'. Valid tiers: {', '.join(MODEL_TIERS)}")
    return MODEL_TIERS[tier]


def _backoff_delay(attempt: int) -> float:
    """Compute capped exponential backoff delay for a given attempt number."""
    return min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY)


def _make_api_call(kwargs: dict, model: str):
    """Execute an API call with retry logic on transient errors.

    Retries up to MAX_RETRIES on rate limits, overload, connection errors,
    and timeouts with exponential backoff. Returns the raw API response.
    """
    client = get_client()
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return client.messages.create(**kwargs)

        except anthropic.RateLimitError as e:
            last_error = e
            delay = _backoff_delay(attempt)
            logger.warning(
                "Rate limited by %s (attempt %d/%d), retrying in %.1fs",
                model,
                attempt + 1,
                MAX_RETRIES + 1,
                delay,
            )
            time.sleep(delay)

        except anthropic.APIStatusError as e:
            if e.status_code in (500, 502, 503, 529):
                last_error = e
                delay = _backoff_delay(attempt)
                logger.warning(
                    "API error %d from %s (attempt %d/%d), retrying in %.1fs",
                    e.status_code,
                    model,
                    attempt + 1,
                    MAX_RETRIES + 1,
                    delay,
                )
                time.sleep(delay)
            else:
                raise LLMError(f"API error from {model}: {e.status_code} — {e.message}") from e

        except anthropic.APIConnectionError as e:
            last_error = e
            delay = _backoff_delay(attempt)
            logger.warning(
                "Connection error to %s (attempt %d/%d), retrying in %.1fs",
                model,
                attempt + 1,
                MAX_RETRIES + 1,
                delay,
            )
            time.sleep(delay)

        except anthropic.APITimeoutError as e:
            last_error = e
            delay = _backoff_delay(attempt)
            logger.warning(
                "Timeout calling %s (attempt %d/%d), retrying in %.1fs",
                model,
                attempt + 1,
                MAX_RETRIES + 1,
                delay,
            )
            time.sleep(delay)

    # Unreachable with valid config (MAX_RETRIES >= 0): range(MAX_RETRIES + 1)
    # ensures the loop always runs at least once and sets last_error.
    # Guards against programmatic misuse (e.g. MAX_RETRIES = -1).
    if last_error is None:
        raise LLMError(f"No call was attempted for {model}")

    # Provide a specific error message based on the last error type
    if isinstance(last_error, anthropic.APITimeoutError):
        msg = f"Timeout after {MAX_RETRIES} retries calling {model} (timeout={REQUEST_TIMEOUT}s)"
    elif isinstance(last_error, anthropic.RateLimitError):
        msg = f"Rate limited after {MAX_RETRIES} retries calling {model}"
    elif isinstance(last_error, anthropic.APIConnectionError):
        msg = f"Connection failed after {MAX_RETRIES} retries calling {model}"
    elif isinstance(last_error, anthropic.APIStatusError):
        msg = (
            f"API error {last_error.status_code} after {MAX_RETRIES} retries "
            f"calling {model}: {last_error.message}"
        )
    else:
        msg = f"Failed after {MAX_RETRIES} retries calling {model}: {last_error}"
    raise LLMError(msg) from last_error


def call_llm(
    prompt: str,
    *,
    tier: str = "write",
    system: str = "",
    max_tokens: int = 4096,
) -> str:
    """Call Claude with the appropriate model tier.

    Tiers: "scan" (Haiku), "write" (Sonnet), "orchestrate" (Opus).

    Retries up to MAX_RETRIES times on transient errors (rate limits,
    overload, network) with exponential backoff. Wraps API errors in
    a descriptive LLMError.
    """
    model = _resolve_model(tier)

    messages = [{"role": "user", "content": prompt}]
    kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        kwargs["system"] = system

    response = _make_api_call(kwargs, model)
    # Find the first text content block (API may return thinking blocks first)
    text_block = next(
        (block for block in response.content if getattr(block, "type", None) == "text"),
        None,
    )
    if text_block is None:
        raise LLMError(f"No text content block in response from {model}")
    return text_block.text


def call_llm_json(
    prompt: str,
    *,
    tier: str = "write",
    system: str = "",
    schema: dict,
    tool_name: str = "extract",
    tool_description: str = "Extract structured data from the source document.",
    max_tokens: int = 4096,
) -> dict:
    """Call Claude with forced tool_use for guaranteed structured JSON output.

    Uses the Anthropic API's tool_use feature to get guaranteed valid JSON
    matching the provided schema, eliminating JSON parsing errors.

    Args:
        prompt: The user message prompt.
        tier: Model tier — "scan", "write", or "orchestrate".
        system: Optional system message.
        schema: JSON Schema for the expected output structure.
        tool_name: Name for the virtual tool definition.
        tool_description: Description for the virtual tool.
        max_tokens: Maximum output tokens.

    Returns:
        Dict matching the provided schema.

    Raises:
        LLMError: On API failures after retries or missing tool_use block.
        ValueError: On invalid tier.
    """
    model = _resolve_model(tier)

    tool_def = {
        "name": tool_name,
        "description": tool_description,
        "input_schema": schema,
    }
    messages = [{"role": "user", "content": prompt}]
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "tools": [tool_def],
        "tool_choice": {"type": "tool", "name": tool_name},
    }
    if system:
        kwargs["system"] = system

    response = _make_api_call(kwargs, model)
    for block in response.content:
        if block.type == "tool_use":
            if block.name != tool_name:
                raise LLMError(
                    f"Wrong tool in response from {model}: "
                    f"expected '{tool_name}', got '{block.name}'"
                )
            return block.input
    raise LLMError(f"No tool_use block in response from {model}")


class LLMError(Exception):
    """Raised when LLM calls fail after retries or with non-retryable errors."""
