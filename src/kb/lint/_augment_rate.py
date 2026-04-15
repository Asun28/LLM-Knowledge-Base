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


class RateLimiter:
    """Sliding-window rate limiter persisted to disk with file lock."""

    def __init__(self):
        RATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()
        self._this_run_total = 0  # in-process; resets per RateLimiter instance

    def _load(self) -> dict:
        if not RATE_PATH.exists():
            return {"schema": 1, "global": {"hour_window": []}, "per_host": {}}
        try:
            with file_lock(RATE_PATH):
                return json.loads(RATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Corrupt rate-limit file, resetting: %s", e)
            return {"schema": 1, "global": {"hour_window": []}, "per_host": {}}

    def _save(self) -> None:
        with file_lock(RATE_PATH):
            atomic_json_write(self._state, RATE_PATH)

    def _purge_old(self, window: list[float], cutoff: float) -> list[float]:
        return [ts for ts in window if ts >= cutoff]

    def acquire(self, host: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds).

        Increments the relevant counters when allowed; leaves state unchanged
        when blocked.
        """
        now = datetime.now(UTC).timestamp()
        cutoff = now - 3600

        # Per-run cap (in-process)
        if self._this_run_total >= config.AUGMENT_FETCH_MAX_CALLS_PER_RUN:
            return False, 0

        # Global hourly cap
        self._state["global"]["hour_window"] = self._purge_old(
            self._state["global"]["hour_window"], cutoff
        )
        if (
            len(self._state["global"]["hour_window"])
            >= config.AUGMENT_FETCH_MAX_CALLS_PER_HOUR
        ):
            oldest = self._state["global"]["hour_window"][0]
            return False, max(1, int(oldest + 3600 - now) + 1)

        # Per-host hourly cap
        host_state = self._state["per_host"].setdefault(host, {"hour_window": []})
        host_state["hour_window"] = self._purge_old(host_state["hour_window"], cutoff)
        if (
            len(host_state["hour_window"])
            >= config.AUGMENT_FETCH_MAX_CALLS_PER_HOST_PER_HOUR
        ):
            oldest = host_state["hour_window"][0]
            return False, max(1, int(oldest + 3600 - now) + 1)

        # All good - append + persist
        self._state["global"]["hour_window"].append(now)
        host_state["hour_window"].append(now)
        self._this_run_total += 1
        self._save()
        return True, 0
