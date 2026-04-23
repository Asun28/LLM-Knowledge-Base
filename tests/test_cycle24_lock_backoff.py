"""Cycle 24 AC9/AC10 — `file_lock` exponential backoff across all polling sites.

Regression tests for:
- AC9: retry loop uses exponential backoff (floor LOCK_INITIAL_POLL_INTERVAL,
  cap LOCK_POLL_INTERVAL). Both constants are module attributes read at call
  time so tests can monkeypatch either one.
- AC10: sleep-spy dual assertion — call_count >= 2 AND observed sequence
  matches the exponential schedule.
- CONDITION 3: LOCK_POLL_INTERVAL is the CAP — monkeypatching to a smaller
  value clamps all observed sleeps to <= that value.
- CONDITION 7: backoff applies to ALL THREE polling sites (normal retry,
  POSIX stale-steal, Windows stale-steal).

Closes threats T3 (starvation), T4 (monkeypatch compatibility).
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kb.utils import io as io_mod


def _seed_lock_with_live_pid(lock_path: Path) -> None:
    """Seed `.lock` file with the current-process PID so `file_lock` sees
    `FileExistsError` on first acquire attempt AND treats the PID as live
    (current process is running)."""
    lock_path.write_text(str(os.getpid()), encoding="ascii")


def test_sleep_sequence_is_exponential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC10 — during contention, `time.sleep` calls follow the exponential
    schedule `[0.01, 0.02, 0.04, 0.05, 0.05, ...]` (floor 0.01, cap 0.05).

    Divergent-fails on AC9 revert (fixed 0.05 poll) because the first two
    observed sleeps would be 0.05 instead of 0.01 / 0.02.
    """
    # Set a short deadline so the test times out quickly. LOCK_TIMEOUT_SECONDS
    # monkeypatch ensures the test doesn't wait seconds of real time.
    monkeypatch.setattr(io_mod, "LOCK_TIMEOUT_SECONDS", 0.15)

    target = tmp_path / "target.txt"
    target.touch()
    lock_path = target.with_suffix(target.suffix + ".lock")
    _seed_lock_with_live_pid(lock_path)

    sleep_spy = MagicMock(wraps=time.sleep)
    monkeypatch.setattr(io_mod.time, "sleep", sleep_spy)

    # Acquire must fail with TimeoutError (live PID, never released).
    with pytest.raises((TimeoutError, OSError)):
        with io_mod.file_lock(target):
            pass

    # At least two sleeps observed (retry loop actually entered).
    assert sleep_spy.call_count >= 2, (
        f"Expected >= 2 sleeps under contention; got {sleep_spy.call_count}"
    )

    # Collect observed sleep values.
    observed = [call.args[0] for call in sleep_spy.call_args_list]
    # Verify exponential pattern: first should be 0.01 (floor), doubling up to
    # cap 0.05. Build expected prefix of same length.
    expected = []
    for i in range(len(observed)):
        expected.append(min(0.01 * (2**i), 0.05))
    assert observed == pytest.approx(expected), (
        f"Observed sleep sequence {observed!r} does not match exponential "
        f"schedule {expected!r}. AC9 revert to fixed 0.05 would show all 0.05."
    )


def test_module_attribute_monkeypatch_honored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONDITION 3 — monkeypatching `LOCK_POLL_INTERVAL` to a small value clamps
    ALL observed sleeps to <= that value (CAP semantic).

    Pins the contract: future refactors that snapshot `LOCK_POLL_INTERVAL` into
    a function-local at `file_lock` entry would silently bypass the patch
    (test would fail catching observed sleeps > 0.005).
    """
    monkeypatch.setattr(io_mod, "LOCK_TIMEOUT_SECONDS", 0.05)
    # Set cap smaller than floor so every sleep clamps to the cap.
    monkeypatch.setattr(io_mod, "LOCK_POLL_INTERVAL", 0.005)

    target = tmp_path / "target.txt"
    target.touch()
    lock_path = target.with_suffix(target.suffix + ".lock")
    _seed_lock_with_live_pid(lock_path)

    sleep_spy = MagicMock(wraps=time.sleep)
    monkeypatch.setattr(io_mod.time, "sleep", sleep_spy)

    with pytest.raises((TimeoutError, OSError)):
        with io_mod.file_lock(target):
            pass

    observed = [call.args[0] for call in sleep_spy.call_args_list]
    assert sleep_spy.call_count >= 1, "Must observe at least one sleep"
    for value in observed:
        assert value <= 0.005, (
            f"All observed sleeps must be <= LOCK_POLL_INTERVAL (0.005); got {value}. "
            f"CAP semantic broken — LOCK_POLL_INTERVAL was snapshotted instead of "
            f"read at call time."
        )


def test_backoff_applies_to_stale_lock_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONDITION 7 — exponential backoff also applies to the stale-lock recovery
    path. Seeds a dead-PID lock; the first timeout attempts stale-steal AND
    sleeps with backoff schedule (not fixed cap)."""
    monkeypatch.setattr(io_mod, "LOCK_TIMEOUT_SECONDS", 0.0)  # immediate timeout

    target = tmp_path / "target.txt"
    target.touch()
    lock_path = target.with_suffix(target.suffix + ".lock")
    # Seed lock with a PID we know is dead (1 is almost always init/systemd,
    # but we override os.kill to simulate ProcessLookupError).
    lock_path.write_text("99999999", encoding="ascii")

    # Force the POSIX stale-steal branch via ProcessLookupError.
    def _fake_kill(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(io_mod.os, "kill", _fake_kill)

    sleep_spy = MagicMock(wraps=time.sleep)
    monkeypatch.setattr(io_mod.time, "sleep", sleep_spy)

    # The stale-steal path should succeed (lock stolen + reacquired) on next
    # loop iteration.
    with io_mod.file_lock(target, timeout=0.15):
        pass

    # At least one sleep observed from stale-steal recovery path.
    assert sleep_spy.call_count >= 1, (
        "Stale-lock recovery must sleep on its exponential-backoff path"
    )
    observed = [call.args[0] for call in sleep_spy.call_args_list]
    # First observed sleep must be LOCK_INITIAL_POLL_INTERVAL (0.01), NOT
    # the pre-cycle-24 fixed 0.05. Revert to fixed polling would fail here.
    assert observed[0] == pytest.approx(0.01), (
        f"Stale-lock recovery first sleep must use LOCK_INITIAL_POLL_INTERVAL "
        f"(0.01); got {observed[0]}. Partial AC9 (only normal retry covered) "
        f"would show 0.05 here."
    )


def test_lock_poll_interval_read_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: `LOCK_POLL_INTERVAL` must be looked up at CALL TIME (module
    attribute access) rather than snapshotted at function entry.

    This complements the monkeypatch test by asserting the attribute-lookup
    semantic explicitly. A refactor that moves `LOCK_POLL_INTERVAL` to a
    function-local would silently break cycle-2 tests that monkeypatch the
    module attribute to 0.01; this test would also fail because the
    monkeypatched value of 0.0 would not clamp the sleeps.
    """
    monkeypatch.setattr(io_mod, "LOCK_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(io_mod, "LOCK_POLL_INTERVAL", 0.0)
    # With LOCK_POLL_INTERVAL=0 and LOCK_INITIAL_POLL_INTERVAL=0.01 unchanged,
    # `min(0.01 * 2^attempt_count, 0) = 0` for every attempt, so ALL observed
    # sleeps clamp to 0. This pins CAP semantics: the module-level CAP is
    # applied at call time, not snapshotted. A refactor that snapshots the
    # cap into a function-local at function entry would silently ignore the
    # monkeypatch (cap would remain at the pre-patch 0.05 default) and the
    # observed sleeps would be 0.01, 0.02, etc. — the test would fail.
    target = tmp_path / "target.txt"
    target.touch()
    lock_path = target.with_suffix(target.suffix + ".lock")
    _seed_lock_with_live_pid(lock_path)

    sleep_spy = MagicMock(wraps=time.sleep)
    monkeypatch.setattr(io_mod.time, "sleep", sleep_spy)

    with pytest.raises((TimeoutError, OSError)):
        with io_mod.file_lock(target):
            pass

    for value in [c.args[0] for c in sleep_spy.call_args_list]:
        assert value == 0.0, f"With LOCK_POLL_INTERVAL=0, all sleeps must be 0; got {value}"


def test_lock_initial_poll_interval_is_module_constant() -> None:
    """Pin `LOCK_INITIAL_POLL_INTERVAL` as a module-level attribute with value
    0.01. Prevents future refactors that inline the constant from silently
    drifting the floor."""
    assert hasattr(io_mod, "LOCK_INITIAL_POLL_INTERVAL"), (
        "LOCK_INITIAL_POLL_INTERVAL must exist as a module-level constant"
    )
    assert io_mod.LOCK_INITIAL_POLL_INTERVAL == 0.01


def test_existing_cycle2_monkeypatch_compatibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cycle-2 compatibility check: existing `test_backlog_by_file_cycle2.py`
    tests monkeypatch `LOCK_POLL_INTERVAL = 0.01` and rely on all sleeps
    clamping to 0.01 or below. This test replicates that pattern."""
    monkeypatch.setattr(io_mod, "LOCK_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(io_mod, "LOCK_TIMEOUT_SECONDS", 0.05)

    target = tmp_path / "target.txt"
    target.touch()
    lock_path = target.with_suffix(target.suffix + ".lock")
    _seed_lock_with_live_pid(lock_path)

    sleep_spy = MagicMock(wraps=time.sleep)
    monkeypatch.setattr(io_mod.time, "sleep", sleep_spy)

    t = threading.Thread(target=lambda: None)
    t.start()
    t.join()
    # Attempt acquire under contention; expect TimeoutError.
    with pytest.raises((TimeoutError, OSError)):
        with io_mod.file_lock(target):
            pass

    # All sleeps must be <= 0.01 (CAP clamps them).
    observed = [c.args[0] for c in sleep_spy.call_args_list]
    assert sleep_spy.call_count >= 1
    for v in observed:
        assert v <= 0.01, (
            f"cycle-2 pattern: all sleeps must be <= 0.01 (monkeypatched cap); got {v}"
        )
