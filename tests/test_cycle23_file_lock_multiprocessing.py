"""Cycle 23 AC7 — cross-process file_lock regression (Phase 4.5 HIGH-Deferred).

Single-process thread-based tests proved insufficient per Phase 4.5 R2:
Windows PID-recycling and NTFS lock semantics can only be exercised
across true OS processes. This test spawns a child via the ``spawn`` start
method (deterministic across Windows + POSIX), has it hold
``kb.utils.io.file_lock`` for a fixed window, and verifies the parent:

1. observes the child's PID in the sentinel file while the lock is held,
2. receives ``TimeoutError`` when attempting a short-timeout acquire,
3. successfully acquires the lock after the child releases and exits.

``@pytest.mark.integration`` so the test runs under the dedicated
integration tier; spawn + Python startup adds ~1-2 s, cheaper than the
correctness guarantee in-process proxies cannot provide.
"""

from __future__ import annotations

import multiprocessing as mp
import time
from pathlib import Path

import pytest


def _child_hold_lock(
    lock_path_str: str,
    pid_sentinel_str: str,
    hold_seconds: float,
) -> None:
    """Top-level worker (picklable for ``spawn``).

    Acquires the lock, writes its PID to the sentinel, sleeps, releases.
    Imports ``file_lock`` lazily so the child process pays the kb import
    cost only inside the Process boundary.
    """
    import os

    from kb.utils.io import file_lock

    lock_path = Path(lock_path_str)
    pid_sentinel = Path(pid_sentinel_str)
    with file_lock(lock_path, timeout=5.0):
        pid_sentinel.write_text(str(os.getpid()), encoding="ascii")
        time.sleep(hold_seconds)


@pytest.mark.integration
def test_cross_process_file_lock_timeout_then_recovery(tmp_path):
    """AC7 — parent times out while child holds lock; acquires after release."""
    from kb.utils.io import file_lock

    lock_target = tmp_path / "shared.json"
    lock_target.write_text("{}", encoding="utf-8")
    pid_sentinel = tmp_path / "child.pid"

    ctx = mp.get_context("spawn")
    hold_seconds = 2.0
    child = ctx.Process(
        target=_child_hold_lock,
        args=(str(lock_target), str(pid_sentinel), hold_seconds),
    )
    child.start()
    try:
        # Wait for child to claim the lock + publish its PID.
        deadline = time.monotonic() + 10.0  # generous for spawn bootstrap
        while not pid_sentinel.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert pid_sentinel.exists(), (
            "child did not acquire lock within 10s (spawn may have failed; "
            f"exit_code={child.exitcode})"
        )
        recorded_pid = int(pid_sentinel.read_text(encoding="ascii"))
        assert recorded_pid == child.pid, f"sentinel PID mismatch: {recorded_pid} != {child.pid}"

        # Parent's short-timeout acquire must raise TimeoutError because
        # the child is still holding the lock.
        with pytest.raises(TimeoutError):
            with file_lock(lock_target, timeout=0.5):
                pytest.fail("acquired lock while child still held it")
    finally:
        child.join(timeout=10)
        if child.is_alive():  # pragma: no cover — safety fallback
            child.kill()
            child.join(timeout=2)

    assert child.exitcode == 0, f"child exited non-zero: {child.exitcode}"

    # With the child gone the lock must be acquirable again.
    with file_lock(lock_target, timeout=2.0):
        lock_target.write_text("parent-wrote", encoding="utf-8")
    assert lock_target.read_text(encoding="utf-8") == "parent-wrote"
