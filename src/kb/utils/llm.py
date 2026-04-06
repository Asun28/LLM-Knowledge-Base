"""Anthropic API wrapper with model tiering, retry, and timeout."""

import logging
import threading
import time

import anthropic

from kb.config import MODEL_TIERS

logger = logging.getLogger(__name__)

# Retry settings
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds
RETRY_MAX_DELAY = 30.0  # seconds
REQUEST_TIMEOUT = 120.0  # seconds

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
    client = get_client()
    if tier not in MODEL_TIERS:
        raise ValueError(f"Invalid tier '{tier}'. Valid tiers: {', '.join(MODEL_TIERS)}")
    model = MODEL_TIERS[tier]

    messages = [{"role": "user", "content": prompt}]
    kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        kwargs["system"] = system

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(**kwargs)
            if not response.content:
                raise LLMError(f"Empty response from {model} — check API key and quota")
            return response.content[0].text

        except anthropic.RateLimitError as e:
            last_error = e
            delay = min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY)
            logger.warning(
                "Rate limited by %s (attempt %d/%d), retrying in %.1fs",
                model, attempt + 1, MAX_RETRIES, delay,
            )
            time.sleep(delay)

        except anthropic.APIStatusError as e:
            if e.status_code in (429, 500, 502, 503, 529):
                last_error = e
                delay = min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY)
                logger.warning(
                    "API error %d from %s (attempt %d/%d), retrying in %.1fs",
                    e.status_code, model, attempt + 1, MAX_RETRIES, delay,
                )
                time.sleep(delay)
            else:
                raise LLMError(
                    f"API error from {model}: {e.status_code} — {e.message}"
                ) from e

        except anthropic.APIConnectionError as e:
            last_error = e
            delay = min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY)
            logger.warning(
                "Connection error to %s (attempt %d/%d), retrying in %.1fs",
                model, attempt + 1, MAX_RETRIES, delay,
            )
            time.sleep(delay)

        except anthropic.APITimeoutError as e:
            last_error = e
            delay = min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY)
            logger.warning(
                "Timeout calling %s (attempt %d/%d), retrying in %.1fs",
                model, attempt + 1, MAX_RETRIES, delay,
            )
            time.sleep(delay)

    raise LLMError(
        f"Failed after {MAX_RETRIES} retries calling {model}: {last_error}"
    ) from last_error


class LLMError(Exception):
    """Raised when LLM calls fail after retries or with non-retryable errors."""
