"""Tests for file-locking correctness — Phase 4 audit."""

import os
import threading
import time


def test_file_lock_basic_mutual_exclusion(tmp_path):
    """file_lock must prevent concurrent access between threads."""
    from kb.utils.io import file_lock

    log = []
    errors = []

    def worker(n):
        try:
            with file_lock(tmp_path / "shared.json"):
                log.append(f"enter-{n}")
                time.sleep(0.02)
                log.append(f"exit-{n}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"file_lock raised errors: {errors}"
    # Correct interleaving: each enter is immediately followed by its matching exit
    for i in range(0, len(log) - 1, 2):
        entry = log[i]
        exit_ = log[i + 1]
        n = entry.split("-")[1]
        assert entry == f"enter-{n}" and exit_ == f"exit-{n}", f"Interleaved access detected: {log}"


def test_file_lock_writes_pid_to_lock_file(tmp_path):
    """file_lock must write the current PID to the lock file while held."""
    from kb.utils.io import file_lock

    lock_path = (tmp_path / "test.json").with_suffix(".json.lock")
    pid_in_lock = []

    with file_lock(tmp_path / "test.json"):
        if lock_path.exists():
            try:
                pid_in_lock.append(int(lock_path.read_text().strip()))
            except ValueError:
                pass

    assert pid_in_lock, "Lock file was not written or contained no PID"
    assert pid_in_lock[0] == os.getpid(), (
        f"Lock file PID {pid_in_lock[0]} != current PID {os.getpid()}"
    )


def test_feedback_lock_uses_file_lock(tmp_path):
    """_feedback_lock must now delegate to file_lock (write PID, cross-process safe)."""
    from kb.feedback.store import _feedback_lock

    lock_path = (tmp_path / "feedback.json").with_suffix(".json.lock")
    pid_seen = []

    with _feedback_lock(tmp_path / "feedback.json"):
        if lock_path.exists():
            try:
                pid_seen.append(int(lock_path.read_text().strip()))
            except ValueError:
                pass

    assert pid_seen, "_feedback_lock did not write a PID to the lock file"
    assert pid_seen[0] == os.getpid()


def test_verdicts_add_verdict_does_not_use_threading_lock(tmp_path):
    """add_verdict must not use threading.Lock — must acquire a file-based lock."""
    import kb.lint.verdicts as verd_mod

    # threading.Lock should no longer be present at module level
    assert not hasattr(verd_mod, "_verdicts_lock") or not hasattr(
        getattr(verd_mod, "_verdicts_lock", None), "acquire"
    ), "_verdicts_lock is still a threading.Lock"

    # add_verdict must complete without error
    verdicts_path = tmp_path / "verdicts.json"
    verd_mod.add_verdict("concepts/test", "review", "pass", path=verdicts_path)
    assert verdicts_path.exists()
