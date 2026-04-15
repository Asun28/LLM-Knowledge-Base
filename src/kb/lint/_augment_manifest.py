"""Augment run-state manifest with atomic JSON writes + cross-process file lock.

One file per run at .data/augment-run-<run_id[:8]>.json. State machine per gap:
  pending → proposed → fetched → saved → extracted → ingested → verdict → done
Terminal non-success: abstained | failed | cooldown.

On Manifest.close(), one summary line is appended to .data/augment_runs.jsonl
for kb_stats / audit / rollback queries.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kb.config import PROJECT_ROOT
from kb.utils.io import atomic_json_write, file_lock

logger = logging.getLogger(__name__)

MANIFEST_DIR = PROJECT_ROOT / ".data"
RUNS_INDEX_PATH = MANIFEST_DIR / "augment_runs.jsonl"

TERMINAL_STATES = frozenset({"done", "abstained", "failed", "cooldown"})
# States considered "complete enough" to skip on resume. Includes true terminal
# states plus late-stage in-progress states (ingested, verdict) where re-running
# the upstream work would be wasteful or duplicative.
RESUME_COMPLETE_STATES = TERMINAL_STATES | frozenset({"ingested", "verdict"})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class Manifest:
    """Augment run state. Use Manifest.start() or Manifest.resume(); never instantiate directly."""

    run_id: str
    path: Path
    data: dict

    # ---- factories ----

    @classmethod
    def start(
        cls,
        *,
        run_id: str,
        mode: str,
        max_gaps: int,
        stubs: list[dict[str, Any]],
    ) -> Manifest:
        MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
        path = MANIFEST_DIR / f"augment-run-{run_id[:8]}.json"
        ts = _now_iso()
        data = {
            "schema": 1,
            "run_id": run_id,
            "started_at": ts,
            "ended_at": None,
            "mode": mode,
            "max_gaps": max_gaps,
            "gaps": [
                {
                    "page_id": stub["page_id"],
                    "title": stub.get("title", ""),
                    "state": "pending",
                    "transitions": [{"state": "pending", "ts": ts}],
                }
                for stub in stubs
            ],
        }
        with file_lock(path):
            atomic_json_write(data, path)
        return cls(run_id=run_id, path=path, data=data)

    @classmethod
    def resume(cls, *, run_id_prefix: str) -> Manifest | None:
        if not MANIFEST_DIR.exists():
            return None
        for f in MANIFEST_DIR.glob(f"augment-run-{run_id_prefix}*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Skipping corrupt manifest %s: %s", f, e)
                continue
            if data.get("ended_at"):
                continue  # already complete
            return cls(run_id=data["run_id"], path=f, data=data)
        return None

    # ---- mutators ----

    def advance(self, page_id: str, state: str, payload: dict[str, Any] | None = None) -> None:
        ts = _now_iso()
        for gap in self.data["gaps"]:
            if gap["page_id"] == page_id:
                gap["state"] = state
                transition: dict[str, Any] = {"state": state, "ts": ts}
                if payload is not None:
                    transition["payload"] = payload
                gap["transitions"].append(transition)
                with file_lock(self.path):
                    atomic_json_write(self.data, self.path)
                return
        raise KeyError(f"Gap not found in manifest: {page_id}")

    def close(self) -> None:
        self.data["ended_at"] = _now_iso()
        with file_lock(self.path):
            atomic_json_write(self.data, self.path)
        self._append_runs_index()

    def _append_runs_index(self) -> None:
        counts = {"done": 0, "abstained": 0, "failed": 0, "cooldown": 0}
        for gap in self.data["gaps"]:
            counts[gap["state"]] = counts.get(gap["state"], 0) + 1
        entry = {
            "run_id": self.run_id,
            "started_at": self.data["started_at"],
            "ended_at": self.data["ended_at"],
            "mode": self.data["mode"],
            "gaps_examined": len(self.data["gaps"]),
            "gaps_succeeded": counts["done"],
            "gaps_abstained": counts["abstained"],
            "gaps_failed": counts["failed"],
            "gaps_cooldown": counts["cooldown"],
        }
        RUNS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(RUNS_INDEX_PATH):
            with RUNS_INDEX_PATH.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")

    # ---- queries ----

    def incomplete_gaps(self) -> list[dict[str, Any]]:
        return [g for g in self.data["gaps"] if g["state"] not in RESUME_COMPLETE_STATES]

    def gap_state(self, page_id: str) -> str | None:
        for gap in self.data["gaps"]:
            if gap["page_id"] == page_id:
                return gap["state"]
        return None
