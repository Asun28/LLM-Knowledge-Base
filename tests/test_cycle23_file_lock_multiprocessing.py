"""Cycle 23 AC7 — cross-process file_lock regression (Phase 4.5 HIGH-Deferred).

Single-process thread-based tests proved insufficient per Phase 4.5 R2:
Windows PID-recycling and NTFS lock semantics can only be exercised
across true OS processes. This test spawns a Python subprocess, has it hold
``kb.utils.io.file_lock`` for a fixed window signalled by a
release sentinel, and verifies the parent:

1. observes the child's acquire sentinel without depending on multiprocessing,
2. receives ``TimeoutError`` when attempting a short-timeout acquire,
3. successfully acquires the lock after releasing the child + joining.

``@pytest.mark.integration`` so the test runs under the dedicated integration
tier. The subprocess harness avoids Windows ``multiprocessing.spawn`` bootstrap
deadlocks seen in constrained runners while still exercising a true second OS
process. The acquire wait checks both the sentinel and child exit status, so a
child that crashes before writing its PID cannot deadlock the parent.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

_CHILD_HOLD_LOCK_SCRIPT = r"""
import os
import sys
import time
from pathlib import Path

from kb.utils.io import file_lock

lock_path = Path(sys.argv[1])
pid_sentinel = Path(sys.argv[2])
release_sentinel = Path(sys.argv[3])

with file_lock(lock_path, timeout=5.0):
    pid_sentinel.write_text(str(os.getpid()), encoding="ascii")
    print("acquired", flush=True)
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if release_sentinel.exists():
            break
        time.sleep(0.02)
"""


def _child_env() -> dict[str, str]:
    """Give the subprocess the same local ``src`` import path as pytest."""
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        src_path if not current_pythonpath else f"{src_path}{os.pathsep}{current_pythonpath}"
    )
    return env


def _collect_child_output(child: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        return child.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        child.kill()
        return child.communicate(timeout=2)


def _wait_for_child_acquire(
    child: subprocess.Popen[str],
    pid_sentinel: Path,
    *,
    timeout: float,
) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pid_sentinel.exists():
            sentinel_text = pid_sentinel.read_text(encoding="ascii").strip()
            if sentinel_text:
                try:
                    return int(sentinel_text)
                except ValueError as exc:
                    raise AssertionError(
                        f"child wrote invalid PID sentinel: {sentinel_text!r}"
                    ) from exc
        exit_code = child.poll()
        if exit_code is not None:
            stdout, stderr = child.communicate(timeout=1)
            pytest.fail(
                "child exited before acquiring lock: "
                f"exit_code={exit_code}, stdout={stdout!r}, stderr={stderr!r}"
            )
        time.sleep(0.02)

    stdout, stderr = _collect_child_output(child)
    pytest.fail(
        "child did not acquire lock within timeout: "
        f"exit_code={child.returncode}, stdout={stdout!r}, stderr={stderr!r}"
    )


def _running_under_codex_tooling() -> bool:
    return any(
        os.environ.get(name)
        for name in (
            "CODEX_THREAD_ID",
            "CODEX_MANAGED_BY_NPM",
            "CODEX_SANDBOX_NETWORK_DISABLED",
        )
    )


class _StillRunningChild:
    returncode = None

    def poll(self):
        return None

    def communicate(self, timeout=None):
        return "", ""


def test_wait_for_child_acquire_waits_for_pid_content(tmp_path):
    """Regression: CI can observe the sentinel after create but before write."""
    pid_sentinel = tmp_path / "child.pid"
    pid_sentinel.write_text("", encoding="ascii")

    def populate_sentinel() -> None:
        time.sleep(0.05)
        pid_sentinel.write_text("12345", encoding="ascii")

    writer = threading.Thread(target=populate_sentinel)
    writer.start()
    try:
        assert _wait_for_child_acquire(_StillRunningChild(), pid_sentinel, timeout=1.0) == 12345
    finally:
        writer.join(timeout=1.0)


@pytest.mark.integration
@pytest.mark.skipif(
    _running_under_codex_tooling(),
    reason=(
        "Codex tool sessions abort when this Windows environment starts child "
        "Python processes; run outside Codex to exercise the cross-process path."
    ),
)
def test_cross_process_file_lock_timeout_then_recovery(tmp_path):
    """AC7 — parent times out while child holds lock; acquires after release."""
    from kb.utils.io import file_lock

    lock_target = tmp_path / "shared.json"
    lock_target.write_text("{}", encoding="utf-8")
    pid_sentinel = tmp_path / "child.pid"
    release_sentinel = tmp_path / "release"

    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _CHILD_HOLD_LOCK_SCRIPT,
            str(lock_target),
            str(pid_sentinel),
            str(release_sentinel),
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=_child_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # 15 s covers generous interpreter bootstrap on CI. Unlike the older
        # multiprocessing Event path, this loop also notices early child exit.
        recorded_pid = _wait_for_child_acquire(child, pid_sentinel, timeout=15.0)

        # PID sentinel confirms which process now owns the lock (belt-and-
        # braces; the acquire wait above is the primary signal).
        assert pid_sentinel.exists()
        assert recorded_pid != os.getpid()
        lock_file = lock_target.with_suffix(lock_target.suffix + ".lock")
        assert lock_file.read_text(encoding="ascii").strip() == str(recorded_pid)

        # Parent's short-timeout acquire must raise TimeoutError because
        # the child is still holding the lock (deterministic — we haven't
        # written release_sentinel yet).
        t0 = time.monotonic()
        with pytest.raises(TimeoutError):
            with file_lock(lock_target, timeout=0.5):
                pytest.fail("acquired lock while child still held it")
        elapsed = time.monotonic() - t0
        # Sanity: the raise happened within a reasonable window of the
        # requested timeout (catches a regression where the lock is
        # silently acquired and only the inner fail raises).
        assert elapsed < 2.0, f"timeout path took too long ({elapsed:.2f}s)"
        assert child.poll() is None, (
            "child exited before release; stale-PID liveness check may have "
            "terminated the lock holder"
        )

        # Release child, join with condition-20 budget (5s), kill fallback.
        release_sentinel.write_text("release", encoding="ascii")
    finally:
        release_sentinel.write_text("release", encoding="ascii")
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover — safety fallback
            child.kill()
            child.wait(timeout=2)

    stdout, stderr = child.communicate(timeout=1)
    assert child.returncode == 0, (
        f"child exited non-zero: {child.returncode}, stdout={stdout!r}, stderr={stderr!r}"
    )

    # With the child gone the lock must be acquirable again.
    with file_lock(lock_target, timeout=2.0):
        lock_target.write_text("parent-wrote", encoding="utf-8")
    assert lock_target.read_text(encoding="utf-8") == "parent-wrote"
