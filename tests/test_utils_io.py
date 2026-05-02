"""Regression tests for kb.utils.io — file_lock SIGINT safety + sweep_orphan_tmp behaviors."""

import os
import time

from kb.utils import io as io_mod
from kb.utils.io import atomic_text_write, file_lock, sweep_orphan_tmp


def test_file_lock_cleans_up_on_exception_during_acquire(tmp_path, monkeypatch):
    """Regression: Phase 4.5 CRITICAL item 15.

    SIGINT between os.write and try: left orphan lock.
    """
    target = tmp_path / "data.json"
    target.write_text("{}", encoding="utf-8")
    orig_close = io_mod.os.close
    closed = {"called": False}

    def evil_close(fd):
        if not closed["called"]:
            closed["called"] = True
            orig_close(fd)
            raise KeyboardInterrupt("simulated SIGINT")
        orig_close(fd)

    monkeypatch.setattr(io_mod.os, "close", evil_close)
    try:
        with io_mod.file_lock(target):
            pass
    except KeyboardInterrupt:
        pass
    lock_path = target.with_suffix(target.suffix + ".lock")
    assert not lock_path.exists(), f"orphan lock survived SIGINT: {lock_path}"


# ── Cycle 12 — sweep_orphan_tmp + io doc caveats (folded from test_cycle12_io_sweep.py) ─


def test_sweep_orphan_tmp_removes_only_old_top_level_tmp(tmp_path):
    old_tmp = tmp_path / "old.tmp"
    fresh_tmp = tmp_path / "fresh.tmp"
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    nested_tmp = nested_dir / "old-nested.tmp"

    old_tmp.write_text("old", encoding="utf-8")
    fresh_tmp.write_text("fresh", encoding="utf-8")
    nested_tmp.write_text("nested", encoding="utf-8")

    now = time.time()
    os.utime(old_tmp, (now - 7200, now - 7200))
    os.utime(fresh_tmp, (now, now))
    os.utime(nested_tmp, (now - 7200, now - 7200))

    assert sweep_orphan_tmp(tmp_path) == 1

    assert not old_tmp.exists()
    assert fresh_tmp.exists()
    assert nested_tmp.exists()


def test_sweep_orphan_tmp_is_non_recursive(tmp_path):
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    nested_tmp = nested_dir / "old.tmp"
    nested_tmp.write_text("nested", encoding="utf-8")

    now = time.time()
    os.utime(nested_tmp, (now - 7200, now - 7200))

    assert sweep_orphan_tmp(tmp_path) == 0
    assert nested_tmp.exists()


def test_sweep_orphan_tmp_logs_warning_and_continues_on_unlink_error(
    tmp_path,
    monkeypatch,
    caplog,
):
    old_tmp = tmp_path / "old.tmp"
    old_tmp.write_text("old", encoding="utf-8")
    now = time.time()
    os.utime(old_tmp, (now - 7200, now - 7200))

    def fail_unlink(self, *args, **kwargs):
        raise OSError("simulated unlink failure")

    monkeypatch.setattr(io_mod.Path, "unlink", fail_unlink)

    with caplog.at_level("WARNING", logger=io_mod.logger.name):
        assert sweep_orphan_tmp(tmp_path) == 0

    assert old_tmp.exists()
    assert str(old_tmp.resolve()) in caplog.text
    assert "simulated unlink failure" in caplog.text


def test_sweep_orphan_tmp_never_raises_on_missing_directory(tmp_path, caplog):
    """AC2 security-verify fix: caller-supplied directory may not exist; helper
    must log WARNING and return 0 — never raise past the boundary. Exists so
    CLI boot / ingest-tail callers can invoke unconditionally.
    """
    missing = tmp_path / "does-not-exist"
    with caplog.at_level("WARNING", logger=io_mod.logger.name):
        assert sweep_orphan_tmp(missing) == 0
    assert "does not exist" in caplog.text or "not a directory" in caplog.text


def test_sweep_orphan_tmp_never_raises_on_non_directory(tmp_path, caplog):
    """AC2 security-verify fix: a path that exists but is a regular file must
    log WARNING and return 0, not raise NotADirectoryError during glob.
    """
    file_path = tmp_path / "regular.txt"
    file_path.write_text("i am a file", encoding="utf-8")
    with caplog.at_level("WARNING", logger=io_mod.logger.name):
        assert sweep_orphan_tmp(file_path) == 0
    assert "not a directory" in caplog.text


def test_atomic_text_write_default_replaces_existing(tmp_path):
    """Cycle 44 AC25 / CONDITION 6 — default (exclusive=False) atomically
    replaces an existing file via tempfile + os.replace.
    """
    target = tmp_path / "page.md"
    target.write_text("old content", encoding="utf-8")
    atomic_text_write("new content", target)
    assert target.read_text(encoding="utf-8") == "new content"


def test_atomic_text_write_exclusive_raises_on_existing(tmp_path):
    """Cycle 44 AC25 / CONDITION 6 — exclusive=True uses O_CREAT|O_EXCL|O_WRONLY
    for slug-collision detection. Raises FileExistsError if the destination
    already exists, cleans up nothing (caller's content preserved).
    """
    import pytest

    target = tmp_path / "slug.md"
    target.write_text("reserved", encoding="utf-8")
    with pytest.raises(FileExistsError):
        atomic_text_write("collision", target, exclusive=True)
    # Original content preserved
    assert target.read_text(encoding="utf-8") == "reserved"


def test_atomic_text_write_exclusive_creates_new(tmp_path):
    """Cycle 44 AC25 / CONDITION 6 — exclusive=True creates a new file
    successfully when the destination does not exist.
    """
    target = tmp_path / "fresh.md"
    atomic_text_write("first write", target, exclusive=True)
    assert target.read_text(encoding="utf-8") == "first write"


def test_load_page_frontmatter_caches_within_same_mtime_tick(tmp_path):
    """Cycle 44 CONDITION 8 — behavioral replacement for the docstring caveat
    test deleted in cycle 44. Pins the DOCUMENTED stale-read contract from
    `kb.utils.pages.load_page_frontmatter` (cache key is `(path_str, mtime_ns)`,
    so two edits within the same coarse mtime tick share a cache key and the
    second read returns the cached metadata).

    Self-check (cycle-16 L2): mutate `_load_page_frontmatter_cached` to bypass
    the cache (e.g. recompute on every call) → this test FAILS because the
    second read would return the new content "B" instead of cached "A".

    See BACKLOG.md Phase 4.5 HIGH #4 vacuous-test upgrade candidate (C40-L3 +
    C41-L1) for the upgrade history.
    """
    from kb.utils.pages import load_page_frontmatter

    page = tmp_path / "page.md"
    page.write_text("---\ntitle: A\n---\nbody A\n", encoding="utf-8")
    load_page_frontmatter.cache_clear()  # start clean per cycle-19 L2 isolation
    first_meta, first_body = load_page_frontmatter(page)
    assert first_meta["title"] == "A"
    assert first_body == "body A"  # frontmatter.load strips trailing newline

    # Force the same mtime_ns the cache was keyed on, then rewrite content
    stat = page.stat()
    page.write_text("---\ntitle: B\n---\nbody B\n", encoding="utf-8")
    os.utime(page, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    second_meta, second_body = load_page_frontmatter(page)
    # Cache hit: documented stale read contract preserved (cycle 44 non-goal #1
    # — no behavior changes; pin the EXISTING semantic).
    assert second_meta["title"] == "A", "stale-read contract: cache returns 'A'"
    assert second_body == "body A", "stale-read contract: cache returns body 'A'"


def test_file_lock_reaps_stale_lock_with_dead_pid(tmp_path, monkeypatch):
    """Cycle 44 CONDITION 9 — behavioral replacement for the file_lock /
    atomic_*_write docstring tests deleted in cycle 44. Exercises the
    stale-lock-reaping path at `src/kb/utils/io.py:412-415`: if the PID stored
    in a stale .lock file refers to a dead process (`os.kill(pid, 0)` raises
    `ProcessLookupError`), `file_lock` unlinks the stale lock and acquires.

    Self-check (cycle-16 L2): mutate `lock_path.unlink(missing_ok=True)` at
    `src/kb/utils/io.py:415` to a no-op (e.g. `pass`) → this test FAILS with
    a TimeoutError because the stale lock survives.

    See BACKLOG.md Phase 4.5 HIGH #4 vacuous-test upgrade candidate (C40-L3 +
    C41-L1) for the upgrade history. The OneDrive/sweep_orphan_tmp docstring
    portions were deleted as redundant vs `test_sweep_orphan_tmp_*` tests.
    """
    target = tmp_path / "target.json"
    lock_path = target.with_suffix(target.suffix + ".lock")
    fake_dead_pid = 999_999_999
    lock_path.write_text(str(fake_dead_pid), encoding="utf-8")

    real_kill = io_mod.os.kill

    def _kill_raises_for_dead_pid(pid, sig):
        if pid == fake_dead_pid:
            raise ProcessLookupError(f"no such process: {pid}")
        return real_kill(pid, sig)

    monkeypatch.setattr(io_mod.os, "kill", _kill_raises_for_dead_pid)

    # If the stale-lock-reaping path works, file_lock acquires within timeout.
    # Otherwise the stale .lock survives and acquire raises TimeoutError.
    with file_lock(target, timeout=2.0):
        # Inside the with-block, the lock is held by us; the .lock file exists
        # and contains the current PID (not the fake dead PID we wrote earlier).
        assert lock_path.exists()
        assert lock_path.read_text(encoding="utf-8").strip() != str(fake_dead_pid)


# ── file_lock concurrency + verdicts threading.Lock removal (cycle 56 fold) ─


class TestFileLockConcurrency:
    """Phase 4 audit — file_lock mutual exclusion, PID-write contract,
    _feedback_lock delegation, verdicts add_verdict file-lock conformance.
    """

    def test_file_lock_basic_mutual_exclusion(self, tmp_path):
        """file_lock must prevent concurrent access between threads."""
        import threading
        import time

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
            assert entry == f"enter-{n}" and exit_ == f"exit-{n}", (
                f"Interleaved access detected: {log}"
            )

    def test_file_lock_writes_pid_to_lock_file(self, tmp_path):
        """file_lock must write the current PID to the lock file while held."""
        import os

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

    def test_feedback_lock_uses_file_lock(self, tmp_path):
        """_feedback_lock must now delegate to file_lock (write PID, cross-process safe)."""
        import os

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

    def test_verdicts_add_verdict_does_not_use_threading_lock(self, tmp_path):
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
