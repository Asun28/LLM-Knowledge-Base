"""Cycle 23 AC7 — cross-process file_lock regression (Phase 4.5 HIGH-Deferred).

Single-process thread-based tests proved insufficient per Phase 4.5 R2:
Windows PID-recycling and NTFS lock semantics can only be exercised
across true OS processes. This test spawns a child via the ``spawn`` start
method (deterministic across Windows + POSIX), has it hold
``kb.utils.io.file_lock`` for a fixed window signalled by a
``multiprocessing.Event``, and verifies the parent:

1. observes the child's acquire event deterministically (no polling),
2. receives ``TimeoutError`` when attempting a short-timeout acquire,
3. successfully acquires the lock after releasing the child + joining.

``@pytest.mark.integration`` so the test runs under the dedicated
integration tier. The Event-based handshake replaces the naive sentinel-
file polling approach so a child that crashes before writing its PID
cannot deadlock the parent (R1 Sonnet MAJOR — design condition 20).
"""

from __future__ import annotations

import multiprocessing as mp
import time
from pathlib import Path

import pytest


def _child_hold_lock(
    lock_path_str: str,
    pid_sentinel_str: str,
    acquired_event,  # mp.Event — parent waits on this
    release_event,  # mp.Event — parent signals to release
) -> None:
    """Top-level worker (picklable for ``spawn``).

    Acquires the lock, writes its PID, signals ``acquired_event``, then
    blocks on ``release_event`` so the parent controls the hold window
    deterministically instead of racing a timer.
    """
    import os

    from kb.utils.io import file_lock

    lock_path = Path(lock_path_str)
    pid_sentinel = Path(pid_sentinel_str)
    with file_lock(lock_path, timeout=5.0):
        pid_sentinel.write_text(str(os.getpid()), encoding="ascii")
        acquired_event.set()
        # Bounded wait: if parent forgets to signal, child still exits within
        # 10 s so CI doesn't hang forever on a buggy test.
        release_event.wait(timeout=10.0)


@pytest.mark.integration
def test_cross_process_file_lock_timeout_then_recovery(tmp_path):
    """AC7 — parent times out while child holds lock; acquires after release."""
    from kb.utils.io import file_lock

    lock_target = tmp_path / "shared.json"
    lock_target.write_text("{}", encoding="utf-8")
    pid_sentinel = tmp_path / "child.pid"

    ctx = mp.get_context("spawn")
    acquired_event = ctx.Event()
    release_event = ctx.Event()
    child = ctx.Process(
        target=_child_hold_lock,
        args=(
            str(lock_target),
            str(pid_sentinel),
            acquired_event,
            release_event,
        ),
    )
    child.start()
    try:
        # Deterministic handshake — block on the mp.Event instead of polling
        # the sentinel file. 15 s covers generous spawn bootstrap on CI; if
        # the child spawn fails, Event never fires and we fall through with
        # a clear error message.
        assert acquired_event.wait(timeout=15.0), (
            f"child did not acquire lock within 15s — spawn may have failed; "
            f"exit_code={child.exitcode}, alive={child.is_alive()}"
        )

        # PID sentinel confirms which process now owns the lock (belt-and-
        # braces; the Event handshake is the primary signal).
        assert pid_sentinel.exists()
        recorded_pid = int(pid_sentinel.read_text(encoding="ascii"))
        assert recorded_pid == child.pid, f"sentinel PID mismatch: {recorded_pid} != {child.pid}"

        # Parent's short-timeout acquire must raise TimeoutError because
        # the child is still holding the lock (deterministic — we haven't
        # set release_event yet).
        t0 = time.monotonic()
        with pytest.raises(TimeoutError):
            with file_lock(lock_target, timeout=0.5):
                pytest.fail("acquired lock while child still held it")
        elapsed = time.monotonic() - t0
        # Sanity: the raise happened within a reasonable window of the
        # requested timeout (catches a regression where the lock is
        # silently acquired and only the inner fail raises).
        assert elapsed < 2.0, f"timeout path took too long ({elapsed:.2f}s)"

        # Release child, join with condition-20 budget (5s), kill fallback.
        release_event.set()
    finally:
        child.join(timeout=5)
        if child.is_alive():  # pragma: no cover — safety fallback
            child.kill()
            child.join(timeout=2)

    assert child.exitcode == 0, f"child exited non-zero: {child.exitcode}"

    # With the child gone the lock must be acquirable again.
    with file_lock(lock_target, timeout=2.0):
        lock_target.write_text("parent-wrote", encoding="utf-8")
    assert lock_target.read_text(encoding="utf-8") == "parent-wrote"
