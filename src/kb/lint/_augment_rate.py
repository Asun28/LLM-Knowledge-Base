"""Cross-process rate limiter for kb_lint --augment fetches.

Sliding-window token bucket per host + global per-run cap, persisted to
.data/augment_rate.json with OS file lock (reuses kb.utils.io.file_lock).

State schema:
  {"schema": 1,
   "global":   {"hour_window": [ts, ts, ...]},
   "per_host": {"<host>": {"hour_window": [ts, ts, ...]}}}

The in-process per-run counter is NOT persisted; it resets with each
RateLimiter instance so a new `kb lint --augment` invocation gets its
own fresh allowance.

Concurrency: every `acquire()` reads, checks, and writes state INSIDE
a single file_lock acquisition. Two processes racing near a cap cannot
both pass the check — the loser re-reads the winner's incremented
window and is rejected.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from kb import config
from kb.config import PROJECT_ROOT
from kb.utils.io import atomic_json_write, file_lock

logger = logging.getLogger(__name__)

RATE_PATH = PROJECT_ROOT / ".data" / "augment_rate.json"


def _empty_state() -> dict:
    return {"schema": 1, "global": {"hour_window": []}, "per_host": {}}


class RateLimiter:
    """Sliding-window rate limiter persisted to disk with file lock."""

    def __init__(self):
        RATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._this_run_total = 0  # in-process; resets per RateLimiter instance

    def _read_state_locked(self) -> dict:
        """Read persisted state. Caller MUST hold file_lock(RATE_PATH)."""
        if not RATE_PATH.exists():
            return _empty_state()
        try:
            return json.loads(RATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Corrupt rate-limit file, resetting: %s", e)
            return _empty_state()

    def _purge_old(self, window: list[float], cutoff: float) -> list[float]:
        return [ts for ts in window if ts >= cutoff]

    def acquire(self, host: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds).

        On success, appends timestamps to the global + per-host windows and
        persists state atomically. On failure, leaves state unchanged.

        The in-process per-run cap is checked first (no file I/O needed) to
        skip the lock entirely when a run is already exhausted.
        """
        # Per-run cap (in-process, no lock needed)
        if self._this_run_total >= config.AUGMENT_FETCH_MAX_CALLS_PER_RUN:
            return False, 0

        # Full read-check-write critical section under a single lock so
        # two concurrent acquires near a cap boundary cannot both pass.
        with file_lock(RATE_PATH):
            state = self._read_state_locked()
            now = datetime.now(UTC).timestamp()
            cutoff = now - 3600

            # Global hourly cap
            state["global"]["hour_window"] = self._purge_old(
                state["global"]["hour_window"], cutoff
            )
            if (
                len(state["global"]["hour_window"])
                >= config.AUGMENT_FETCH_MAX_CALLS_PER_HOUR
            ):
                oldest = state["global"]["hour_window"][0]
                return False, max(1, int(oldest + 3600 - now) + 1)

            # Per-host hourly cap
            host_state = state["per_host"].setdefault(host, {"hour_window": []})
            host_state["hour_window"] = self._purge_old(host_state["hour_window"], cutoff)
            if (
                len(host_state["hour_window"])
                >= config.AUGMENT_FETCH_MAX_CALLS_PER_HOST_PER_HOUR
            ):
                oldest = host_state["hour_window"][0]
                return False, max(1, int(oldest + 3600 - now) + 1)

            # All gates passed — append + persist before releasing the lock.
            state["global"]["hour_window"].append(now)
            host_state["hour_window"].append(now)
            atomic_json_write(state, RATE_PATH)

        self._this_run_total += 1
        return True, 0
