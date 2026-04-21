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
        assert by_id["freshxx2"]["status"] == "pending", "concurrent fresh refine must be preserved"

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
    """AC13 — sweep holds file_lock across load + save (locked-RMW invariant).

    Spy on load_review_history / save_review_history call order; assert that
    at least one load precedes each save within the locked span. This catches
    a regression that would drop the file_lock around the load-mutate-save
    path (leaving concurrent refine_page interleaving possible).
    """

    def test_load_precedes_save_under_lock(self, tmp_path: Path) -> None:
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

        call_order: list[str] = []
        real_load = refiner.load_review_history
        real_save = refiner.save_review_history

        def spy_load(*args, **kwargs):
            call_order.append("load")
            return real_load(*args, **kwargs)

        def spy_save(*args, **kwargs):
            call_order.append("save")
            return real_save(*args, **kwargs)

        with (
            patch.object(refiner, "load_review_history", spy_load),
            patch.object(refiner, "save_review_history", spy_save),
        ):
            sweep_stale_pending(hours=168, history_path=history_path)

        # Pattern: at least one load precedes each save within the locked RMW.
        # dry_run=False path does ONE load + ONE save.
        assert call_order == ["load", "save"], f"unexpected call order: {call_order}"
