"""Cross-process rate limiter for kb_lint --augment fetches."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from kb import config
from kb.config import PROJECT_ROOT
from kb.utils.io import atomic_json_write, file_lock

logger = logging.getLogger(__name__)

RATE_PATH = PROJECT_ROOT / ".data" / "augment_rate.json"


def _empty_state() -> dict:
    return {"schema": 1, "global": {"hour_window": []}, "per_host": {}}


def _get_rate_path() -> Path:
    return Path(RATE_PATH)


class RateLimiter:
    """Sliding-window rate limiter persisted to disk with file lock."""

    def __init__(self, data_dir: Path | None = None):
        if data_dir is None:
            self._rate_path = _get_rate_path()
        else:
            self._rate_path = Path(data_dir) / "augment_rate.json"
        self._rate_path.parent.mkdir(parents=True, exist_ok=True)
        self._this_run_total = 0

    def _read_state_locked(self) -> dict:
        """Read persisted state. Caller MUST hold file_lock(self._rate_path)."""
        if not self._rate_path.exists():
            return _empty_state()
        try:
            return json.loads(self._rate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Corrupt rate-limit file, resetting: %s", e)
            return _empty_state()

    def _purge_old(self, window: list[float], cutoff: float) -> list[float]:
        return [ts for ts in window if ts >= cutoff]

    def acquire(self, host: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        if self._this_run_total >= config.AUGMENT_FETCH_MAX_CALLS_PER_RUN:
            return False, 0

        with file_lock(self._rate_path):
            state = self._read_state_locked()
            now = datetime.now(UTC).timestamp()
            cutoff = now - 3600

            state["global"]["hour_window"] = self._purge_old(state["global"]["hour_window"], cutoff)
            if len(state["global"]["hour_window"]) >= config.AUGMENT_FETCH_MAX_CALLS_PER_HOUR:
                oldest = state["global"]["hour_window"][0]
                return False, max(1, int(oldest + 3600 - now) + 1)

            host_state = state["per_host"].setdefault(host, {"hour_window": []})
            host_state["hour_window"] = self._purge_old(host_state["hour_window"], cutoff)
            if len(host_state["hour_window"]) >= config.AUGMENT_FETCH_MAX_CALLS_PER_HOST_PER_HOUR:
                oldest = host_state["hour_window"][0]
                return False, max(1, int(oldest + 3600 - now) + 1)

            state["global"]["hour_window"].append(now)
            host_state["hour_window"].append(now)
            atomic_json_write(state, self._rate_path)

        self._this_run_total += 1
        return True, 0


def _sync_legacy_shim() -> None:
    legacy = sys.modules.get("kb.lint._augment_rate")
    if legacy is None:
        return
    legacy.__dict__.update({"RateLimiter": RateLimiter, "RATE_PATH": RATE_PATH})


_sync_legacy_shim()
