"""Safe-call helper — Cycle 7 AC27.

Wraps a thunk so operational failures surface as labelled error strings in a
lint / health report rather than silently degrading. Previously six sites
across ``lint/runner.py``, ``mcp/health.py``, ``mcp/core.py``, and
``mcp/quality.py`` each open-coded ``except Exception as e: logger.warning(
...); return None`` — the caller could not distinguish "no data yet" from
"store corrupt" and end-users saw an empty report rather than an error
indicator. This helper centralizes that pattern.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from kb.mcp.app import _sanitize_error_str

logger = logging.getLogger(__name__)


def _safe_call[T](
    fn: Callable[[], T],
    *,
    fallback: T | None = None,
    label: str,
    log: logging.Logger | None = None,
) -> tuple[T | None, str | None]:
    """Call ``fn()``; on exception log + return ``(fallback, error_str)``.

    Args:
        fn: Zero-argument callable.
        fallback: Value to return on failure.
        label: Short identifier used in the error string (e.g.,
            ``"verdict_history"`` or ``"feedback_flagged_pages"``).
        log: Optional logger; defaults to this module's logger.

    Returns:
        ``(result, None)`` on success or ``(fallback, "<label>_error: <type>: <msg>")``
        on failure. Callers merge the error_str into the report dict so the
        surface visibly shows the degradation.
    """
    active_log = log or logger
    try:
        return fn(), None
    except Exception as exc:  # noqa: BLE001 — _safe_call IS the guard
        msg = f"{label}_error: {type(exc).__name__}: {_sanitize_error_str(exc)}"
        active_log.warning("safe_call(%s) failed: %s", label, exc)
        return fallback, msg
