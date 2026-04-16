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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kb.config import PROJECT_ROOT
from kb.utils.io import atomic_json_write, file_lock

logger = logging.getLogger(__name__)

MANIFEST_DIR = PROJECT_ROOT / ".data"

TERMINAL_STATES = frozenset({"done", "abstained", "failed", "cooldown"})
# States considered "complete enough" to skip on resume. Includes true terminal
# states plus late-stage in-progress states (ingested, verdict) where re-running
# the upstream work would be wasteful or duplicative.
RESUME_COMPLETE_STATES = TERMINAL_STATES | frozenset({"ingested", "verdict"})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _resolve_data_dir(data_dir: Path | None) -> Path:
    """B2 (Phase 5 three-round MEDIUM): honor caller-supplied data_dir so
    custom-project runs (kb_lint --augment --wiki-dir /tmp/x/wiki) do not
    leak manifests into the main repo's .data/.
    """
    return data_dir if data_dir is not None else MANIFEST_DIR


def _runs_index_path(data_dir: Path | None = None) -> Path:
    """Derive the runs-index path. See B2 — lazy resolution plus data_dir
    override prevent cross-project state bleed.
    """
    return _resolve_data_dir(data_dir) / "augment_runs.jsonl"


@dataclass
class Manifest:
    """Augment run state. Use Manifest.start() or Manifest.resume(); never instantiate directly."""

    run_id: str
    path: Path
    data: dict
    data_dir: Path = field(default_factory=lambda: MANIFEST_DIR)

    # ---- factories ----

    @classmethod
    def start(
        cls,
        *,
        run_id: str,
        mode: str,
        max_gaps: int,
        stubs: list[dict[str, Any]],
        data_dir: Path | None = None,
    ) -> Manifest:
        resolved = _resolve_data_dir(data_dir)
        resolved.mkdir(parents=True, exist_ok=True)
        path = resolved / f"augment-run-{run_id[:8]}.json"
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
        return cls(run_id=run_id, path=path, data=data, data_dir=resolved)

    @classmethod
    def resume(
        cls, *, run_id_prefix: str, data_dir: Path | None = None
    ) -> Manifest | None:
        resolved = _resolve_data_dir(data_dir)
        if not resolved.exists():
            return None
        for f in resolved.glob(f"augment-run-{run_id_prefix}*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Skipping corrupt manifest %s: %s", f, e)
                continue
            if data.get("ended_at"):
                continue  # already complete
            return cls(run_id=data["run_id"], path=f, data=data, data_dir=resolved)
        return None

    # ---- mutators ----

    def advance(self, page_id: str, state: str, payload: dict[str, Any] | None = None) -> None:
        """Transition a gap to a new state under file lock.

        Re-reads the manifest inside the lock so a concurrent process
        resuming the same run cannot clobber each other's transitions.
        The in-memory self.data is refreshed to match.
        """
        ts = _now_iso()
        with file_lock(self.path):
            try:
                latest = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                # If the on-disk file is unreadable, fall back to our in-memory
                # snapshot — preserves the previous non-concurrent behavior.
                latest = self.data
            for gap in latest["gaps"]:
                if gap["page_id"] == page_id:
                    gap["state"] = state
                    transition: dict[str, Any] = {"state": state, "ts": ts}
                    if payload is not None:
                        transition["payload"] = payload
                    gap["transitions"].append(transition)
                    atomic_json_write(latest, self.path)
                    self.data = latest
                    return
        raise KeyError(f"Gap not found in manifest: {page_id}")

    def close(self) -> None:
        with file_lock(self.path):
            try:
                latest = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                latest = self.data
            latest["ended_at"] = _now_iso()
            atomic_json_write(latest, self.path)
            self.data = latest
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
        runs_index = _runs_index_path(self.data_dir)
        runs_index.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(runs_index):
            with runs_index.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")

    # ---- queries ----

    def incomplete_gaps(self) -> list[dict[str, Any]]:
        return [g for g in self.data["gaps"] if g["state"] not in RESUME_COMPLETE_STATES]

    def gap_state(self, page_id: str) -> str | None:
        for gap in self.data["gaps"]:
            if gap["page_id"] == page_id:
                return gap["state"]
        return None
