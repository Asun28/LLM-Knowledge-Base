"""Cycle 18 AC4/AC5/AC6 — wiki_log rotate-in-lock + generic helper tests.

Threat T2: POSIX handle-holding-stale-file race. Rotation must run INSIDE
`file_lock(log_path)` so a concurrent appender cannot write to the renamed-
away (archived) file.

Test strategy: call-order spy per cycle-17 L2 — do NOT simulate concurrency.
Verify via shared events list that rotation happens between lock_enter and
the append write.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

from kb.utils import wiki_log


def test_rotate_inside_lock(tmp_path: Path, monkeypatch) -> None:
    """AC4 + AC6 — rotate runs after file_lock.__enter__ and before append write."""
    log_path = tmp_path / "log.md"
    # Populate the log to exceed the rotation threshold so rotate actually fires.
    log_path.write_text(
        "# Wiki Log\n\n" + ("x" * (wiki_log.LOG_SIZE_WARNING_BYTES + 100)),
        encoding="utf-8",
    )

    events: list[str] = []

    # Spy on file_lock — record enter/exit order around the inner write.
    @contextmanager
    def spy_file_lock(path: Path, timeout=None):
        events.append(f"lock_enter:{path.name}")
        try:
            yield
        finally:
            events.append(f"lock_exit:{path.name}")

    # Spy on rotate — record when it runs relative to lock boundaries.
    real_rotate = wiki_log._rotate_log_if_oversized

    def spy_rotate(p: Path) -> None:
        events.append(f"rotate:{p.name}")
        real_rotate(p)

    # Spy on Path.rename — captures the actual rotation rename.
    real_rename = Path.rename

    def spy_rename(self, target):
        events.append(f"rename:{self.name}->{Path(target).name}")
        return real_rename(self, target)

    monkeypatch.setattr(wiki_log, "file_lock", spy_file_lock)
    monkeypatch.setattr(wiki_log, "_rotate_log_if_oversized", spy_rotate)
    monkeypatch.setattr(Path, "rename", spy_rename)

    wiki_log.append_wiki_log("test", "trigger rotate", log_path)

    # Assert the TOTAL ORDER: lock_enter < rotate < rename < lock_exit.
    lock_enter_idx = next(i for i, e in enumerate(events) if e.startswith("lock_enter"))
    rotate_idx = next(i for i, e in enumerate(events) if e.startswith("rotate:"))
    rename_idx = next(i for i, e in enumerate(events) if e.startswith("rename:"))
    lock_exit_idx = next(i for i, e in enumerate(events) if e.startswith("lock_exit"))

    assert lock_enter_idx < rotate_idx, f"Rotate must run AFTER lock_enter. Events: {events}"
    assert rotate_idx < rename_idx, f"Rename must run AFTER rotate call. Events: {events}"
    assert rename_idx < lock_exit_idx, f"Rename must run BEFORE lock_exit. Events: {events}"


def test_rotate_if_oversized_generic(tmp_path: Path, caplog) -> None:
    """AC5 — generic helper rotates a non-log.md path with the right archive suffix."""
    path = tmp_path / "foo.jsonl"
    path.write_text("x" * 200, encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="kb.utils.wiki_log"):
        wiki_log.rotate_if_oversized(path, max_bytes=100, archive_stem_prefix="foo")

    # Original path gone, archive created with .jsonl suffix preserved.
    assert not path.exists()
    archives = list(tmp_path.glob("foo.*.jsonl"))
    assert len(archives) == 1, f"Expected 1 archive, got {archives}"
    # Audit event fires BEFORE the rename — rename wipes mtime, but the log record
    # in caplog is the evidence.
    rotate_records = [r for r in caplog.records if "Rotating" in r.getMessage()]
    assert len(rotate_records) == 1, f"Expected 1 rotation log line, got {rotate_records}"


def test_rotate_if_oversized_under_threshold(tmp_path: Path) -> None:
    """AC5 — no rotation when file size <= max_bytes."""
    path = tmp_path / "foo.jsonl"
    path.write_text("x" * 50, encoding="utf-8")

    wiki_log.rotate_if_oversized(path, max_bytes=100, archive_stem_prefix="foo")

    assert path.exists(), "File must still exist after no-op rotation"
    assert list(tmp_path.glob("foo.*.jsonl")) == [], "No archive expected under threshold"


def test_rotate_if_oversized_missing_file(tmp_path: Path) -> None:
    """AC5 — no-op for non-existent path."""
    path = tmp_path / "missing.jsonl"
    wiki_log.rotate_if_oversized(path, max_bytes=100, archive_stem_prefix="missing")
    assert not path.exists()


def test_rotate_if_oversized_ordinal_collision(tmp_path: Path) -> None:
    """AC5 — second rotation in the same month uses ordinal .2 fallback."""
    from datetime import UTC, datetime  # noqa: PLC0415

    year_month = datetime.now(UTC).strftime("%Y-%m")
    stem = f"foo.{year_month}"
    # Pre-seed the primary archive name so the helper must pick the .2 ordinal.
    (tmp_path / f"{stem}.jsonl").write_text("pre-existing", encoding="utf-8")

    path = tmp_path / "foo.jsonl"
    path.write_text("x" * 200, encoding="utf-8")

    wiki_log.rotate_if_oversized(path, max_bytes=100, archive_stem_prefix="foo")

    assert not path.exists()
    assert (tmp_path / f"{stem}.jsonl").read_text(encoding="utf-8") == "pre-existing"
    assert (tmp_path / f"{stem}.2.jsonl").exists(), (
        f"Expected ordinal .2 archive; got {list(tmp_path.iterdir())}"
    )
