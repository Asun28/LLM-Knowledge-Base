"""Cycle 20 AC13/AC16 — sweep_stale_pending mutation tool.

Pins:
- mark_failed flips pending → failed with sweep metadata; attempt_id preserved.
- delete removes row AND writes wiki/log.md audit BEFORE mutation (T4).
- dry_run returns candidates without mutation.
- Under-cutoff rows untouched.
- Unknown action / hours<1 raises ValidationError.
- attempt_id matching — unrelated pending rows with different attempt_id preserved
  even when page_id matches (prevents concurrent-refine clobber).
- file_lock serialises load/save inside the sweep span.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from kb.errors import ValidationError
from kb.review.refiner import save_review_history, sweep_stale_pending


def _write_history(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    save_review_history(rows, path)


def _iso(delta_hours: float) -> str:
    return (datetime.now() - timedelta(hours=delta_hours)).isoformat()


def _iso_older_than(timestamp: str, hours: int) -> bool:
    """Inline timestamp-gate for the page_id-revert simulation test."""
    cutoff = datetime.now() - timedelta(hours=hours)
    try:
        ts = datetime.fromisoformat(timestamp)
    except ValueError:
        return False
    return ts < cutoff


class TestSweepValidation:
    """AC13 — unknown action / bad hours raise ValidationError."""

    def test_unknown_action_raises(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.json"
        _write_history(history_path, [])
        with pytest.raises(ValidationError, match="unknown sweep action"):
            sweep_stale_pending(action="nope", history_path=history_path)

    def test_hours_zero_raises(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.json"
        _write_history(history_path, [])
        with pytest.raises(ValidationError, match="hours must be"):
            sweep_stale_pending(hours=0, history_path=history_path)

    def test_hours_negative_raises(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.json"
        _write_history(history_path, [])
        with pytest.raises(ValidationError, match="hours must be"):
            sweep_stale_pending(hours=-5, history_path=history_path)


class TestSweepMarkFailed:
    """AC13 — mark_failed (default) flips status and preserves attempt_id."""

    def test_stale_pending_flipped_to_failed(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.json"
        _write_history(
            history_path,
            [
                {
                    "page_id": "entities/abandoned",
                    "attempt_id": "aaaaaaaa",
                    "status": "pending",
                    "timestamp": _iso(200),
                    "revision_notes": "crashy refine",
                },
            ],
        )
        result = sweep_stale_pending(hours=168, action="mark_failed", history_path=history_path)
        assert result == {
            "swept": 1,
            "action": "mark_failed",
            "sweep_id": result["sweep_id"],
            "dry_run": False,
        }
        assert result["sweep_id"] and len(result["sweep_id"]) == 8

        rows = json.loads(history_path.read_text(encoding="utf-8"))
        assert len(rows) == 1
        row = rows[0]
        assert row["status"] == "failed"
        assert row["error"] == "abandoned-by-sweep"
        assert row["sweep_id"] == result["sweep_id"]
        assert "sweep_at" in row
        # attempt_id preserved (AC13 / R2 — match by attempt_id, not page_id).
        assert row["attempt_id"] == "aaaaaaaa"
        # revision_notes preserved — mark_failed is reversible-by-inspection.
        assert row["revision_notes"] == "crashy refine"

    def test_under_cutoff_untouched(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.json"
        _write_history(
            history_path,
            [
                {
                    "page_id": "entities/fresh",
                    "attempt_id": "bbbbbbbb",
                    "status": "pending",
                    "timestamp": _iso(0.5),  # 30 min ago — inside 168h cutoff
                    "revision_notes": "recent",
                },
            ],
        )
        result = sweep_stale_pending(hours=168, history_path=history_path)
        assert result["swept"] == 0
        rows = json.loads(history_path.read_text(encoding="utf-8"))
        assert rows[0]["status"] == "pending"
        assert "sweep_id" not in rows[0]

    def test_applied_status_ignored(self, tmp_path: Path) -> None:
        """Already-completed rows are NOT swept even if timestamp is old."""
        history_path = tmp_path / "history.json"
        _write_history(
            history_path,
            [
                {
                    "page_id": "entities/done",
                    "attempt_id": "cccccccc",
                    "status": "applied",
                    "timestamp": _iso(500),
                    "revision_notes": "n/a",
                },
            ],
        )
        result = sweep_stale_pending(hours=168, history_path=history_path)
        assert result["swept"] == 0

    def test_idempotent_second_call(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.json"
        _write_history(
            history_path,
            [
                {
                    "page_id": "entities/x",
                    "attempt_id": "dddddddd",
                    "status": "pending",
                    "timestamp": _iso(200),
                },
            ],
        )
        first = sweep_stale_pending(hours=168, history_path=history_path)
        assert first["swept"] == 1
        second = sweep_stale_pending(hours=168, history_path=history_path)
        # Second run is a no-op — row is now status="failed", not pending.
        assert second["swept"] == 0


class TestSweepAttemptIdMatching:
    """AC13 / D-NEW R2 — sweep matches by attempt_id, never by page_id."""

    def test_same_page_id_different_attempt_id_is_not_clobbered(self, tmp_path: Path) -> None:
        """Cycle-20 R1 Sonnet BLOCKER-hardened — the mutation loop must match
        rows by ``attempt_id``, NEVER by ``page_id``. Fresh pending row is
        preserved via the timestamp filter (candidate exclusion) AND the
        attempt_id membership check in the mutation loop — a revert that
        swaps ``attempt_id`` for ``page_id`` in the mutation loop would flip
        the fresh row to ``failed`` too because its page_id matches the
        sweep target's page_id.
        """
        history_path = tmp_path / "history.json"
        _write_history(
            history_path,
            [
                # Stale row (abandoned concurrent refine) with attempt_id X
                {
                    "page_id": "entities/same",
                    "attempt_id": "stalexx1",
                    "status": "pending",
                    "timestamp": _iso(300),
                    "revision_notes": "abandoned",
                },
                # Fresh concurrent refine for SAME page_id with attempt_id Y.
                # Must NOT be swept even though the page_id matches.
                {
                    "page_id": "entities/same",
                    "attempt_id": "freshxx2",
                    "status": "pending",
                    "timestamp": _iso(0.1),
                    "revision_notes": "in flight",
                },
            ],
        )
        result = sweep_stale_pending(hours=168, history_path=history_path)
        assert result["swept"] == 1, "sweep must match by attempt_id, not page_id"

        rows = json.loads(history_path.read_text(encoding="utf-8"))
        by_id = {row["attempt_id"]: row for row in rows}
        assert by_id["stalexx1"]["status"] == "failed"
        assert by_id["freshxx2"]["status"] == "pending", (
            "concurrent fresh refine must be preserved — fresh row under "
            "cutoff should NOT be flipped to failed just because its page_id "
            "matches the swept row. A page_id-matching revert in the mutation "
            "loop would flip BOTH rows (same page_id + both pending), failing."
        )
        # Cycle-20 R1 Sonnet BLOCKER hardening: per-row sweep-metadata pin.
        # Under a revert where the mutation loop targets page_id, the fresh
        # row would receive the SAME sweep_id + sweep_at as the stale row.
        # Asserting their ABSENCE on the fresh row makes the
        # attempt_id-vs-page_id divergence unambiguous and defeats the
        # "test passed via timestamp filter alone" vacuity concern.
        assert by_id["stalexx1"].get("sweep_id") is not None
        assert by_id["stalexx1"].get("sweep_at") is not None
        assert by_id["stalexx1"].get("error") == "abandoned-by-sweep"
        assert "sweep_id" not in by_id["freshxx2"], (
            "fresh row must NOT carry sweep metadata; presence indicates the "
            "mutation loop touched it (page_id revert detected)"
        )
        assert "sweep_at" not in by_id["freshxx2"]
        assert "error" not in by_id["freshxx2"]

    def test_page_id_matching_revert_is_detectable_via_explicit_revert_sim(
        self, tmp_path: Path
    ) -> None:
        """Belt-and-braces — explicitly simulate a page_id-matching mutation
        loop and pin what such a revert would do. Combined with the test
        above, this shows the attempt_id assertion is NOT vacuous: under
        page_id-matching, the fresh row WOULD flip, and the above test
        WOULD fail.
        """
        from kb.review.refiner import load_review_history, save_review_history

        history_path = tmp_path / "history.json"
        rows_in = [
            {
                "page_id": "entities/revert-sim",
                "attempt_id": "revstale",
                "status": "pending",
                "timestamp": _iso(300),
            },
            {
                "page_id": "entities/revert-sim",
                "attempt_id": "revfresh",
                "status": "pending",
                "timestamp": _iso(0.1),
            },
        ]
        _write_history(history_path, rows_in)

        # Hand-rolled page_id-matching mutation loop — this is what the
        # production code DOES NOT do (and must never do).
        history = load_review_history(history_path)
        stale_page_ids = {
            row["page_id"]
            for row in history
            if row["status"] == "pending" and _iso_older_than(row["timestamp"], 168)
        }
        for row in history:
            if row["page_id"] in stale_page_ids and row["status"] == "pending":
                row["status"] = "failed"
        save_review_history(history, history_path)

        rows_out = json.loads(history_path.read_text(encoding="utf-8"))
        by_id = {r["attempt_id"]: r for r in rows_out}
        # Under page_id matching, BOTH rows flip to failed.
        assert by_id["revstale"]["status"] == "failed"
        assert by_id["revfresh"]["status"] == "failed", (
            "simulation of page_id-matching revert must flip the fresh row "
            "too — that is exactly the regression the attempt_id-matching "
            "test above guards against"
        )

    def test_unrelated_pending_row_different_page_untouched(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.json"
        _write_history(
            history_path,
            [
                {
                    "page_id": "entities/stale-a",
                    "attempt_id": "stalexxa",
                    "status": "pending",
                    "timestamp": _iso(300),
                },
                {
                    "page_id": "entities/unrelated-b",
                    "attempt_id": "freshxxb",
                    "status": "pending",
                    "timestamp": _iso(0.1),  # recent — under cutoff
                },
            ],
        )
        result = sweep_stale_pending(hours=168, history_path=history_path)
        assert result["swept"] == 1
        rows = json.loads(history_path.read_text(encoding="utf-8"))
        by_id = {row["attempt_id"]: row for row in rows}
        assert by_id["stalexxa"]["status"] == "failed"
        assert by_id["freshxxb"]["status"] == "pending"


class TestSweepDelete:
    """AC13 / T4 — delete writes wiki/log.md audit BEFORE removing rows."""

    def test_delete_audit_write_failure_aborts_without_mutation(
        self, tmp_project: Path, monkeypatch
    ) -> None:
        """Step-11 T4 fix — fail CLOSED when the audit log cannot be written.

        Regression for the PARTIAL gap Codex flagged: previously an OSError
        from `append_wiki_log` was swallowed and the delete proceeded,
        producing an irreversible audit-free deletion. Now the sweep raises
        `StorageError(kind="sweep_audit_failure")` BEFORE touching history.
        """
        from kb.review import refiner

        # Cycle-19 L2 defensive binding — under full-suite ordering,
        # `kb.errors` can be reloaded by cycle-15's `importlib.reload(kb.config)`
        # cascade, in which case the test-module-top `from kb.errors import
        # StorageError` captures a different class object than the one
        # `kb.review.refiner` imported at ITS module top. `pytest.raises`
        # compares by class identity, so mismatched reloads cause a silent
        # miss. Late-bind `StorageError` from `refiner`'s module-attribute
        # lookup so we catch whichever class `refiner` actually raises.
        StorageError = refiner.StorageError

        history_path = tmp_project / ".data" / "history.json"
        _write_history(
            history_path,
            [
                {
                    "page_id": "entities/abort",
                    "attempt_id": "abortaaa",
                    "status": "pending",
                    "timestamp": _iso(300),
                    "revision_notes": "would-be-deleted",
                }
            ],
        )
        prev_history = history_path.read_text(encoding="utf-8")

        def _boom_log(*args, **kwargs):
            raise OSError("simulated log disk failure")

        monkeypatch.setattr(refiner, "append_wiki_log", _boom_log)

        with pytest.raises(StorageError) as excinfo:
            refiner.sweep_stale_pending(
                hours=168,
                action="delete",
                history_path=history_path,
                wiki_dir=tmp_project / "wiki",
            )
        assert excinfo.value.kind == "sweep_audit_failure"

        # History file UNTOUCHED — fail-closed guarantee.
        assert history_path.read_text(encoding="utf-8") == prev_history

    def test_delete_removes_row_and_writes_audit_first(self, tmp_project: Path) -> None:
        history_path = tmp_project / ".data" / "history.json"
        _write_history(
            history_path,
            [
                {
                    "page_id": "entities/gone",
                    "attempt_id": "delxxaaa",
                    "status": "pending",
                    "timestamp": _iso(300),
                    "revision_notes": "delete-candidate",
                },
            ],
        )
        log_path = tmp_project / "wiki" / "log.md"
        prev_log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""

        result = sweep_stale_pending(
            hours=168,
            action="delete",
            history_path=history_path,
            wiki_dir=tmp_project / "wiki",
        )
        assert result == {
            "swept": 1,
            "action": "delete",
            "sweep_id": None,
            "dry_run": False,
        }

        # Row removed.
        rows = json.loads(history_path.read_text(encoding="utf-8"))
        assert rows == []

        # Audit entry in wiki/log.md mentions attempt_id and cutoff.
        log_text = log_path.read_text(encoding="utf-8")
        assert "sweep" in log_text.lower()
        assert "delxxaaa" in log_text
        assert log_text != prev_log, "audit log should have been appended"


class TestSweepDryRun:
    """AC13 — dry_run returns candidates without mutation."""

    def test_dry_run_returns_candidates_without_mutation(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.json"
        rows = [
            {
                "page_id": "entities/a",
                "attempt_id": "drystlea",
                "status": "pending",
                "timestamp": _iso(300),
            },
            {
                "page_id": "entities/b",
                "attempt_id": "drystleb",
                "status": "pending",
                "timestamp": _iso(0.1),  # under cutoff
            },
        ]
        _write_history(history_path, rows)
        original_text = history_path.read_text(encoding="utf-8")

        result = sweep_stale_pending(hours=168, dry_run=True, history_path=history_path)
        assert result["dry_run"] is True
        assert result["swept"] == 1
        assert result["sweep_id"] is None
        assert len(result["candidates"]) == 1
        assert result["candidates"][0]["attempt_id"] == "drystlea"

        # History file unchanged.
        assert history_path.read_text(encoding="utf-8") == original_text


class TestSweepLockSerialization:
    """AC13 — sweep holds ``file_lock(history_path)`` across load + save.

    Cycle-20 R1 Codex NIT hardening: the original version spied only on
    `load_review_history` / `save_review_history` and asserted `["load", "save"]`
    call order — which would still pass if the `with file_lock(...)` wrapper
    were removed (loads/saves still happen in order, just without lock).
    The hardened version spies on `file_lock` itself to record when the lock
    is held, and spies on load/save to record which calls occur INSIDE the
    lock span. A revert that drops the `with file_lock(...)` would produce
    load/save calls OUTSIDE the lock-held window and fail the assertion.
    """

    def test_load_save_happen_while_lock_is_held(self, tmp_path: Path) -> None:
        from contextlib import contextmanager

        from kb.review import refiner

        history_path = tmp_path / "history.json"
        _write_history(
            history_path,
            [
                {
                    "page_id": "entities/x",
                    "attempt_id": "lockxx01",
                    "status": "pending",
                    "timestamp": _iso(300),
                }
            ],
        )

        # State the spies share: whether we are currently inside the
        # production `with file_lock(...)` span.
        lock_held = {"active": False, "entered": 0, "exited": 0}
        events: list[tuple[str, bool]] = []
        real_load = refiner.load_review_history
        real_save = refiner.save_review_history
        real_file_lock = refiner.file_lock

        @contextmanager
        def spy_file_lock(path, *args, **kwargs):
            # Only treat the history_path acquisition as the sweep lock;
            # other call sites (wiki_log.append_wiki_log, etc.) don't count.
            is_history = str(path) == str(history_path)
            with real_file_lock(path, *args, **kwargs):
                if is_history:
                    lock_held["active"] = True
                    lock_held["entered"] += 1
                try:
                    yield
                finally:
                    if is_history:
                        lock_held["active"] = False
                        lock_held["exited"] += 1

        def spy_load(*args, **kwargs):
            events.append(("load", lock_held["active"]))
            return real_load(*args, **kwargs)

        def spy_save(*args, **kwargs):
            events.append(("save", lock_held["active"]))
            return real_save(*args, **kwargs)

        with (
            patch.object(refiner, "file_lock", spy_file_lock),
            patch.object(refiner, "load_review_history", spy_load),
            patch.object(refiner, "save_review_history", spy_save),
        ):
            sweep_stale_pending(hours=168, history_path=history_path)

        assert lock_held["entered"] == 1, (
            f"history file_lock must be acquired exactly once (got {lock_held['entered']})"
        )
        assert lock_held["exited"] == 1, "history file_lock must be released"
        # Filter to the load/save events that happened inside the locked span.
        locked_events = [ev for ev in events if ev[1]]
        assert [ev[0] for ev in locked_events] == ["load", "save"], (
            f"load + save must BOTH happen inside file_lock(history_path); got events={events}"
        )
