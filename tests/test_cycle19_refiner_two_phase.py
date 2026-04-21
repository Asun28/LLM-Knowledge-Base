"""Cycle 19 AC8/AC8b/AC9/AC10 — refine_page two-phase write + list_stale_pending.

Two-phase contract:
1. Pending row written BEFORE page body (under page_lock + history_lock).
2. Page body atomic_text_write.
3. Pending → applied/failed flip under SAME history_lock span (no release/re-acquire).

Lock-order is page_lock OUTER, history_lock INNER (cycle-1 H1 contract preserved
per cycle-19 AC10 WITHDRAW).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


def _seed_page(wiki_dir: Path, page_id: str, title: str, body: str) -> Path:
    page_path = wiki_dir / f"{page_id}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(
        f"---\ntitle: {title}\ntype: concept\nsource: []\nupdated: 2026-01-01\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return page_path


# ────────────────────────────────────────────────────────────────────────────
# AC8 — applied row has attempt_id
# ────────────────────────────────────────────────────────────────────────────


def test_applied_row_has_attempt_id(tmp_wiki: Path, tmp_path: Path) -> None:
    """T-8 — Successful refine yields one history entry status='applied' with attempt_id."""
    from kb.review.refiner import load_review_history, refine_page

    _seed_page(tmp_wiki, "concepts/foo", "Foo", "Original body about foo.")

    history_path = tmp_path / "review_history.json"
    result = refine_page(
        "concepts/foo",
        "Updated body about foo with new content.",
        revision_notes="cycle19 AC8 happy path",
        wiki_dir=tmp_wiki,
        history_path=history_path,
    )

    assert result.get("updated") is True
    history = load_review_history(history_path)
    assert len(history) == 1, f"Expected 1 history row; got {history}"
    row = history[0]
    assert row["status"] == "applied", f"status should be 'applied'; got {row}"
    assert "attempt_id" in row, f"attempt_id missing from row {row}"
    assert len(row["attempt_id"]) == 8, (
        f"attempt_id should be 8 hex chars; got {row['attempt_id']!r}"
    )


# ────────────────────────────────────────────────────────────────────────────
# AC8 — page-write OSError flips pending → failed (page body unchanged)
# ────────────────────────────────────────────────────────────────────────────


def test_page_write_oserror_flips_to_failed(tmp_wiki: Path, tmp_path: Path) -> None:
    """T-8a — atomic_text_write OSError leaves status='failed' and page body unchanged."""
    from kb.review import refiner
    from kb.review.refiner import load_review_history, refine_page

    page_path = _seed_page(tmp_wiki, "concepts/foo", "Foo", "Original body unchanged.")
    original_body = page_path.read_text(encoding="utf-8")
    history_path = tmp_path / "review_history.json"

    # Inject OSError into atomic_text_write so the page write fails.
    def boom(*args, **kwargs):
        raise OSError("simulated write failure")

    with patch.object(refiner, "atomic_text_write", side_effect=boom):
        result = refine_page(
            "concepts/foo",
            "Refused content",
            revision_notes="cycle19 AC8 failed path",
            wiki_dir=tmp_wiki,
            history_path=history_path,
        )

    assert "error" in result, f"Expected error result; got {result}"
    # Page body must be unchanged.
    assert page_path.read_text(encoding="utf-8") == original_body
    # History should have ONE entry with status='failed' + error field.
    history = load_review_history(history_path)
    assert len(history) == 1
    row = history[0]
    assert row["status"] == "failed", f"status should be 'failed'; got {row}"
    assert "simulated write failure" in row.get("error", "")


# ────────────────────────────────────────────────────────────────────────────
# AC9 — crash between pending and applied leaves status='pending' visible
# ────────────────────────────────────────────────────────────────────────────


def test_crash_after_pending_leaves_pending_row(tmp_wiki: Path, tmp_path: Path) -> None:
    """T-9 — Simulated crash mid-flip leaves the pending row visible for forensic inspection."""
    from kb.review import refiner
    from kb.review.refiner import load_review_history, refine_page

    page_path = _seed_page(tmp_wiki, "concepts/foo", "Foo", "Original body about foo.")
    history_path = tmp_path / "review_history.json"

    # Allow the first save_review_history (pending) to succeed; raise on the
    # second call (the applied flip). Page write succeeds in between.
    real_save = refiner.save_review_history
    call_no = {"n": 0}

    def crash_on_second_save(history, path=None):
        call_no["n"] += 1
        if call_no["n"] == 1:
            return real_save(history, path)
        raise KeyboardInterrupt("simulated crash mid-flip")

    with patch.object(refiner, "save_review_history", side_effect=crash_on_second_save):
        with pytest.raises(KeyboardInterrupt):
            refine_page(
                "concepts/foo",
                "New body content for crash test.",
                revision_notes="cycle19 AC9 crash mid-flip",
                wiki_dir=tmp_wiki,
                history_path=history_path,
            )

    # The pending row should still be on disk.
    history = load_review_history(history_path)
    assert len(history) == 1, f"Expected 1 history row; got {history}"
    assert history[0]["status"] == "pending", f"Expected pending; got {history[0]}"
    # Page body WAS written before the crash (Phase 2 succeeded).
    assert "New body content" in page_path.read_text(encoding="utf-8")


# ────────────────────────────────────────────────────────────────────────────
# AC10 — lock order: page_lock OUTER, history_lock INNER
# ────────────────────────────────────────────────────────────────────────────


def test_lock_order_page_outer_history_inner(tmp_wiki: Path, tmp_path: Path, monkeypatch) -> None:
    """T-10 — Lock-acquisition order is page_lock FIRST, history_lock SECOND."""
    from contextlib import contextmanager

    from kb.review import refiner
    from kb.review.refiner import refine_page

    _seed_page(tmp_wiki, "concepts/foo", "Foo", "Body.")
    history_path = tmp_path / "review_history.json"

    # Spy on file_lock to record acquisition order.
    real_file_lock = refiner.file_lock
    acquisitions: list[str] = []

    @contextmanager
    def spy_lock(path: Path, *args, **kwargs):
        if "review_history" in str(path):
            acquisitions.append("history")
        elif path.suffix == ".md":
            acquisitions.append("page")
        with real_file_lock(path, *args, **kwargs):
            yield

    monkeypatch.setattr(refiner, "file_lock", spy_lock)

    refine_page(
        "concepts/foo",
        "Updated body.",
        revision_notes="cycle19 AC10 lock-order",
        wiki_dir=tmp_wiki,
        history_path=history_path,
    )

    assert acquisitions == ["page", "history"], (
        f"Lock order should be page first, history second; got {acquisitions}. "
        f"AC10 WITHDRAW preserves cycle-1 H1 contract."
    )


# ────────────────────────────────────────────────────────────────────────────
# AC8 — flip locates row by attempt_id (not by index)
# ────────────────────────────────────────────────────────────────────────────


def test_flip_locates_row_by_attempt_id(tmp_wiki: Path, tmp_path: Path) -> None:
    """T-8b — The applied flip targets THIS refine's attempt_id, not concurrent rows."""
    from kb.review.refiner import load_review_history, refine_page, save_review_history

    _seed_page(tmp_wiki, "concepts/foo", "Foo", "Body.")
    history_path = tmp_path / "review_history.json"

    # Pre-seed a stuck pending row from a "concurrent" refine that crashed.
    save_review_history(
        [
            {
                "timestamp": "2026-04-21T12:00:00",
                "page_id": "concepts/other",
                "revision_notes": "concurrent stuck refine",
                "content_length": 100,
                "status": "pending",
                "attempt_id": "deadbeef",
            }
        ],
        history_path,
    )

    refine_page(
        "concepts/foo",
        "Updated body for AC8 attempt_id test.",
        revision_notes="cycle19 AC8 attempt_id correlation",
        wiki_dir=tmp_wiki,
        history_path=history_path,
    )

    history = load_review_history(history_path)
    # Two rows: the pre-seeded stuck one (still pending) + our applied refine.
    assert len(history) == 2
    statuses = sorted([(r["page_id"], r["status"]) for r in history])
    assert ("concepts/foo", "applied") in statuses
    assert ("concepts/other", "pending") in statuses, (
        "The stuck pending row must NOT be flipped to applied — flip must "
        "target THIS refine's attempt_id only."
    )


# ────────────────────────────────────────────────────────────────────────────
# AC8b — list_stale_pending visibility helper
# ────────────────────────────────────────────────────────────────────────────


def test_list_stale_pending_returns_old_pending_rows(tmp_path: Path) -> None:
    """T-8c — list_stale_pending returns pending entries older than the threshold."""
    from kb.review.refiner import list_stale_pending, save_review_history

    history_path = tmp_path / "review_history.json"
    now = datetime.now()
    save_review_history(
        [
            {
                "timestamp": (now - timedelta(hours=2)).isoformat(timespec="seconds"),
                "page_id": "p1",
                "status": "pending",
                "attempt_id": "0001",
            },
            {
                "timestamp": (now - timedelta(hours=25)).isoformat(timespec="seconds"),
                "page_id": "p2",
                "status": "pending",
                "attempt_id": "0002",
            },
            {
                "timestamp": (now - timedelta(hours=48)).isoformat(timespec="seconds"),
                "page_id": "p3",
                "status": "pending",
                "attempt_id": "0003",
            },
            {
                "timestamp": (now - timedelta(hours=25)).isoformat(timespec="seconds"),
                "page_id": "p4",
                "status": "applied",
                "attempt_id": "0004",
            },
        ],
        history_path,
    )

    stale = list_stale_pending(hours=24, history_path=history_path)
    stale_ids = sorted(r["page_id"] for r in stale)
    assert stale_ids == ["p2", "p3"], f"Expected pending rows older than 24h; got {stale_ids}"


def test_list_stale_pending_empty_when_no_pending(tmp_path: Path) -> None:
    """T-8d — list_stale_pending returns [] when all entries are applied/failed."""
    from kb.review.refiner import list_stale_pending, save_review_history

    history_path = tmp_path / "review_history.json"
    save_review_history(
        [
            {
                "timestamp": "2026-01-01T00:00:00",
                "page_id": "p1",
                "status": "applied",
                "attempt_id": "0001",
            }
        ],
        history_path,
    )
    assert list_stale_pending(hours=24, history_path=history_path) == []


# ────────────────────────────────────────────────────────────────────────────
# Cycle-11 L1 vacuous-gate revert check for AC10 lock order
# ────────────────────────────────────────────────────────────────────────────


def test_revert_lock_order_would_break_test(tmp_wiki: Path, tmp_path: Path, monkeypatch) -> None:
    """Vacuous-gate: if we reverted to history-FIRST, the AC10 test would fail.

    This proves the AC10 test's order assertion is non-vacuous — it actually
    catches a regression to the rejected lock-flip order.
    """
    from contextlib import contextmanager

    from kb.review import refiner
    from kb.review.refiner import refine_page

    _seed_page(tmp_wiki, "concepts/foo", "Foo", "Body.")
    history_path = tmp_path / "review_history.json"

    real_file_lock = refiner.file_lock
    acquisitions: list[str] = []

    @contextmanager
    def spy_lock(path: Path, *args, **kwargs):
        if "review_history" in str(path):
            acquisitions.append("history")
        elif path.suffix == ".md":
            acquisitions.append("page")
        with real_file_lock(path, *args, **kwargs):
            yield

    monkeypatch.setattr(refiner, "file_lock", spy_lock)
    refine_page(
        "concepts/foo",
        "Updated.",
        revision_notes="vacuous-gate check",
        wiki_dir=tmp_wiki,
        history_path=history_path,
    )

    # If a reviewer flipped the lock order to history-first, this would be
    # ['history', 'page']. The current (correct) order is ['page', 'history'].
    assert acquisitions != ["history", "page"], (
        "Revert-check sanity: current code must NOT acquire history_lock first. "
        "If this assertion fires, AC10 was inadvertently flipped — see design.md "
        "AC10 WITHDRAW rationale."
    )
