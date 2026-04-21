"""Anthropic API wrapper with model tiering, retry, and timeout."""

import logging
import random
import re
import threading
import time

import anthropic

from kb import __version__
from kb.config import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT,
    LLM_RETRY_BASE_DELAY,
    LLM_RETRY_MAX_DELAY,
    MODEL_TIERS,
    get_cli_backend,
    get_cli_model,
)
from kb.errors import KBError
from kb.utils.text import truncate

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility (tests import these from this module)
MAX_RETRIES = LLM_MAX_RETRIES
RETRY_BASE_DELAY = LLM_RETRY_BASE_DELAY
RETRY_MAX_DELAY = LLM_RETRY_MAX_DELAY
REQUEST_TIMEOUT = LLM_REQUEST_TIMEOUT

_LLM_ERROR_REDACT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ANTHROPIC_KEY", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OPENAI_KEY", re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}")),
    ("GENERIC_SK_KEY", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("BEARER_TOKEN", re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}")),
    ("LONG_HEX", re.compile(r"[A-Fa-f0-9]{32,}")),
    ("LONG_B64", re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")),
]

_client: anthropic.Anthropic | None = None
_client_lock = threading.Lock()


def _redact_secrets(msg: str) -> str:
    if not msg:
        return msg
    for label, pat in _LLM_ERROR_REDACT_PATTERNS:
        msg = pat.sub(f"[REDACTED:{label}]", msg)
    return msg


def get_client() -> anthropic.Anthropic:
    """Get a reusable Anthropic client (uses ANTHROPIC_API_KEY env var)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:  # double-check locking
                _client = anthropic.Anthropic(
                    timeout=REQUEST_TIMEOUT,
                    max_retries=0,
                    default_headers={"User-Agent": f"llm-wiki-flywheel/{__version__}"},
                )
    return _client


def _resolve_model(tier: str) -> str:
    """Validate tier and return the model ID."""
    if tier not in MODEL_TIERS:
        raise ValueError(f"Invalid tier '{tier}'. Valid tiers: {', '.join(MODEL_TIERS)}")
    return MODEL_TIERS[tier]


def _backoff_delay(attempt: int) -> float:
    """Compute capped exponential backoff delay with jitter.

    Item 6 (cycle 2): prior deterministic `min(BASE * 2**attempt, MAX)` caused
    thundering-herd retries under concurrent 429s (two MCP processes, or
    autoresearch loop + interactive user). Adds 0.5-1.5× jitter BEFORE the cap
    so worst-case delay never exceeds RETRY_MAX_DELAY. Single jitter per call;
    callers MUST NOT re-jitter the return value.
    """
    raw = RETRY_BASE_DELAY * (2**attempt)
    jittered = raw * random.uniform(0.5, 1.5)
    return min(jittered, RETRY_MAX_DELAY)


def _make_api_call(kwargs: dict, model: str):
    """Execute an API call with retry logic on transient errors.

    Retries up to MAX_RETRIES on rate limits, overload, connection errors,
    and timeouts with exponential backoff. Returns the raw API response.
    """
    client = get_client()
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            start = time.monotonic()
            response = client.messages.create(**kwargs)
            usage = getattr(response, "usage", None)
            tokens_in = getattr(usage, "input_tokens", 0)
            tokens_out = getattr(usage, "output_tokens", 0)
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "llm.call_ok model=%s attempt=%d tokens_in=%s tokens_out=%s latency_ms=%d",
                model,
                attempt + 1,
                tokens_in,
                tokens_out,
                latency_ms,
            )
            return response

        except anthropic.RateLimitError as e:
            last_error = e
            delay = _backoff_delay(attempt)
            will_retry = attempt < MAX_RETRIES
            if will_retry:
                logger.warning(
                    "Rate limited by %s (attempt %d/%d), retrying in %.1fs",
                    model,
                    attempt + 1,
                    MAX_RETRIES + 1,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "Rate limited by %s (attempt %d/%d), giving up after %d attempts",
                    model,
                    attempt + 1,
                    MAX_RETRIES + 1,
                    MAX_RETRIES + 1,
                )

        except (
            anthropic.BadRequestError,
            anthropic.AuthenticationError,
            anthropic.PermissionDeniedError,
        ) as e:
            # Cycle 3 H1: 4xx caller-bug classes are NEVER retried. Prior code
            # routed these through the generic `except APIStatusError` non-retry
            # branch but surfaced a generic `LLMError(f"API error from {model}...")`
            # that discarded the error-type classification. Surface a typed
            # `LLMError(kind=...)` so callers can branch: invalid_request (prompt
            # too long, invalid tool_choice), auth (bad key), permission (RBAC).
            # Raise immediately without incrementing `last_error` (cycle 3 L1).
            safe_msg = truncate(_redact_secrets(str(e.message)), limit=500)
            if isinstance(e, anthropic.BadRequestError):
                kind = "invalid_request"
            elif isinstance(e, anthropic.AuthenticationError):
                kind = "auth"
            else:
                kind = "permission"
            raise LLMError(
                f"Non-retryable {kind} error from {model} "
                f"({e.__class__.__name__}): {e.status_code} — {safe_msg}",
                kind=kind,
            ) from e

        except anthropic.APIStatusError as e:
            if e.status_code in (500, 502, 503, 529):
                last_error = e
                delay = _backoff_delay(attempt)
                will_retry = attempt < MAX_RETRIES
                if will_retry:
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
                    logger.warning(
                        "API error %d from %s (attempt %d/%d), giving up after %d attempts",
                        e.status_code,
                        model,
                        attempt + 1,
                        MAX_RETRIES + 1,
                        MAX_RETRIES + 1,
                    )
            else:
                # Cycle 3 L1: dead `last_error = e` removed — the branch raises
                # immediately, so the assignment had no consumer.
                # Item 7 (cycle 2): truncate e.message — Anthropic error bodies may
                # contain tens of KB of echoed prompt content (including sensitive
                # text). Preserve verbatim: exception class name, model, status code
                # (so callers can still branch on the structured fields).
                safe_msg = truncate(_redact_secrets(str(e.message)), limit=500)
                raise LLMError(
                    f"API error from {model} ({e.__class__.__name__}): "
                    f"{e.status_code} — {safe_msg}",
                    kind="status_error",
                ) from e

        except anthropic.APIConnectionError as e:
            last_error = e
            delay = _backoff_delay(attempt)
            will_retry = attempt < MAX_RETRIES
            if will_retry:
                logger.warning(
                    "Connection error to %s (attempt %d/%d), retrying in %.1fs",
                    model,
                    attempt + 1,
                    MAX_RETRIES + 1,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "Connection error to %s (attempt %d/%d), giving up after %d attempts",
                    model,
                    attempt + 1,
                    MAX_RETRIES + 1,
                    MAX_RETRIES + 1,
                )

        except anthropic.APITimeoutError as e:
            last_error = e
            delay = _backoff_delay(attempt)
            will_retry = attempt < MAX_RETRIES
            if will_retry:
                logger.warning(
                    "Timeout calling %s (attempt %d/%d), retrying in %.1fs",
                    model,
                    attempt + 1,
                    MAX_RETRIES + 1,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "Timeout calling %s (attempt %d/%d), giving up after %d attempts",
                    model,
                    attempt + 1,
                    MAX_RETRIES + 1,
                    MAX_RETRIES + 1,
                )

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
        # Item 7 (cycle 2): truncate message here as well — the retry-exhausted
        # path also carries `last_error.message` which may echo prompt content.
        safe_msg = truncate(_redact_secrets(str(last_error.message)), limit=500)
        msg = (
            f"API error {last_error.status_code} after {MAX_RETRIES} retries "
            f"calling {model} ({last_error.__class__.__name__}): {safe_msg}"
        )
    else:
        safe_msg = truncate(_redact_secrets(str(last_error)), limit=500)
        msg = f"Failed after {MAX_RETRIES} retries calling {model}: {safe_msg}"
    raise LLMError(msg) from last_error


def call_llm(
    prompt: str,
    *,
    tier: str = "write",
    system: str = "",
    max_tokens: int = 4096,
) -> str:
    """Call the LLM with the appropriate model tier.

    Routes to a CLI subprocess backend when KB_LLM_BACKEND is set to a
    non-anthropic value; otherwise uses the Anthropic SDK path unchanged.

    Tiers: "scan" (Haiku), "write" (Sonnet), "orchestrate" (Opus).

    Retries up to MAX_RETRIES times on transient errors (rate limits,
    overload, network) with exponential backoff. Wraps API errors in
    a descriptive LLMError.
    """
    # Validate tier up-front for both paths — consistent ValueError regardless of backend.
    _resolve_model(tier)
    backend = get_cli_backend()
    if backend != "anthropic":
        from kb.utils import cli_backend as _cli_backend  # AC16: lazy import

        merged = f"System: {system}\n\n{prompt}" if system else prompt
        cli_model = get_cli_model(tier)
        if max_tokens != 4096:
            logger.debug("call_llm: max_tokens=%d ignored for CLI backend %s", max_tokens, backend)
        return _cli_backend.call_cli(
            merged, backend=backend, model=cli_model, timeout=REQUEST_TIMEOUT
        )

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
    """Call the LLM with forced structured JSON output.

    Routes to a CLI subprocess backend when KB_LLM_BACKEND is set to a
    non-anthropic value; otherwise uses the Anthropic tool_use path.

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
    # Validate tier up-front for both paths — consistent ValueError regardless of backend.
    _resolve_model(tier)
    backend = get_cli_backend()
    if backend != "anthropic":
        from kb.utils import cli_backend as _cli_backend  # AC16: lazy import

        merged = f"System: {system}\n\n{prompt}" if system else prompt
        cli_model = get_cli_model(tier)
        _default_desc = "Extract structured data from the source document."
        if tool_name != "extract" or tool_description != _default_desc:
            logger.debug(
                "call_llm_json: tool_name=%r tool_description ignored for CLI backend %s",
                tool_name,
                backend,
            )
        return _cli_backend.call_cli_json(
            merged, backend=backend, model=cli_model, timeout=REQUEST_TIMEOUT, schema=schema
        )

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
    # Item 5 (cycle 2): collect ALL tool_use blocks before picking one.
    # Prior code returned the FIRST tool_use block even when the response
    # contained multiple — the second (a refusal or alternative tool call)
    # was silently discarded. Multi-block responses are an ambiguity signal:
    # surface them as an error listing every block name so the caller can
    # fix the prompt or tool_choice.
    tool_use_blocks = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
    if len(tool_use_blocks) > 1:
        names = [getattr(b, "name", "?") for b in tool_use_blocks]
        raise LLMError(
            f"Multiple tool_use blocks from {model}: {names}; "
            f"expected exactly one matching '{tool_name}'."
        )
    if tool_use_blocks:
        block = tool_use_blocks[0]
        if block.name != tool_name:
            raise LLMError(
                f"Wrong tool in response from {model}: expected '{tool_name}', got '{block.name}'"
            )
        return block.input
    # fix item 17: preserve refusal/diagnostic text in the error for debuggability
    text_preview = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text_preview = block.text[:300]
            break
    if text_preview:
        raise LLMError(f"No tool_use block from {model}; leading text: {text_preview!r}")
    raise LLMError(f"No tool_use block in response from {model}")


class LLMError(KBError):
    """Raised when LLM calls fail after retries or with non-retryable errors.

    Cycle 3 H1: carries an optional `kind` attribute that classifies the cause
    so callers can branch without string-matching the message:

      - ``"invalid_request"`` — 400, prompt too long / invalid tool_choice.
      - ``"auth"`` — 401, bad or missing API key.
      - ``"permission"`` — 403, RBAC / disabled model.
      - ``"status_error"`` — other non-retryable 4xx.
      - ``None`` (default) — retry-exhausted / connection / timeout / generic.

    Cycle 20 AC2: reparented from ``Exception`` to ``kb.errors.KBError`` so
    callers can catch the whole kb taxonomy with ``except KBError``. MRO
    preserves ``isinstance(err, Exception)`` — existing outer catches still fire.
    """

    def __init__(self, message: str, *, kind: str | None = None) -> None:
        super().__init__(message)
        self.kind = kind
