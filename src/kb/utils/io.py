"""Atomic file write utilities.

Lock-ordering convention (Cycle 7 AC17): any caller acquiring more than one
``file_lock()`` across the concurrency surface MUST acquire them in stable
alphabetical order by the authoritative path:

    VERDICTS_PATH → FEEDBACK_PATH → REVIEW_HISTORY_PATH

A single out-of-order acquisition can deadlock with any caller honouring the
convention. Verified by cycle-1/2/6 reviewers; deviating from this ordering is
a bug, not a style preference.
"""

import json
import logging
import os
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_SECONDS = 5.0  # default acquisition deadline
# Cycle 24 AC9 — exponential backoff cap. Read at call time inside `file_lock`
# so tests monkeypatching the module attribute (see
# `tests/test_backlog_by_file_cycle2.py:172,210`) continue to clamp all observed
# sleeps to the patched value. Also doubles as the default polling ceiling for
# the normal + stale-lock retry paths.
LOCK_POLL_INTERVAL = 0.05
# Cycle 24 AC9 — exponential-backoff floor. First retry sleeps for this
# duration; subsequent retries double until capped by ``LOCK_POLL_INTERVAL``.
# Read at call time inside `file_lock` (module attribute, not function-entry
# snapshot).
LOCK_INITIAL_POLL_INTERVAL = 0.01

_IS_WINDOWS = sys.platform == "win32"
_legacy_locks_purged = False
_legacy_locks_purge_lock = threading.Lock()

# Cycle 32 AC6 — fair-queue stagger mitigation (intra-process only,
# probabilistic). Module-level counter tracks how many threads are
# currently inside the ``file_lock`` retry loop so each entrant can
# stagger its first sleep by ``position * _FAIR_QUEUE_STAGGER_MS / 1000``
# (clamped to ``LOCK_POLL_INTERVAL``). Does NOT guarantee fair-queue
# acquisition across processes; only improves the intra-process
# thundering-herd case.
_LOCK_WAITERS: int = 0
_LOCK_WAITERS_LOCK: threading.Lock = threading.Lock()
_FAIR_QUEUE_STAGGER_MS: float = 2.0


def _take_waiter_slot() -> int:
    """Increment ``_LOCK_WAITERS`` and return 0-based position BEFORE increment.

    Caller MUST pair with ``_release_waiter_slot`` in a ``finally`` clause
    (cycle-32 C3 counter-symmetry contract). Position snapshot BEFORE the
    increment means first waiter sees 0 (zero stagger), second sees 1, etc.
    """
    global _LOCK_WAITERS
    with _LOCK_WAITERS_LOCK:
        position = _LOCK_WAITERS
        _LOCK_WAITERS += 1
        return position


def _release_waiter_slot() -> None:
    """Decrement ``_LOCK_WAITERS``; warn on underflow.

    Cycle-32 C14 (R1 Opus R2 residual): silent clamp-to-zero hides
    paired-release bugs. On underflow, emit ``logger.warning`` so counter
    drift surfaces to operators instead of silently inflating stagger for
    all subsequent waiters.
    """
    global _LOCK_WAITERS
    with _LOCK_WAITERS_LOCK:
        if _LOCK_WAITERS > 0:
            _LOCK_WAITERS -= 1
        else:
            logger.warning("_LOCK_WAITERS underflow — paired _take_waiter_slot release missing")


def _cleanup_tmp(tmp_path: str) -> None:
    """Best-effort cleanup of an atomic-write temp file.

    Item 4 (cycle 2): swallow-on-cleanup-failure was silent; now logs WARNING
    so accumulated `.tmp` orphans on AV-locked/OneDrive-synced directories are
    visible. Never masks the caller's original exception (caller re-raises).
    """
    try:
        Path(tmp_path).unlink(missing_ok=True)
    except OSError as cleanup_err:  # pragma: no cover — rare Windows / AV race
        logger.warning("Failed to clean up tempfile %s: %s", tmp_path, cleanup_err)


def _flush_and_fsync(fd: int) -> None:
    """Item 3 (cycle 2): ensure bytes are on stable storage BEFORE atomic rename.
    Without fsync a crash between buffered-write and rename can leave the
    destination atomically replaced with a half-written file; on next
    `load_manifest`/`load_verdicts` the parse fails, silently wiping all
    existing entries. Must RAISE on OSError (threat model: data durability) —
    do not swallow.
    """
    os.fsync(fd)


def atomic_json_write(data: object, path: Path) -> None:
    """Write data as JSON to path atomically (temp file + rename).

    Creates parent directories if needed. On failure, cleans up the
    temp file and re-raises the exception.

    Caveat: cloud-synced or network-backed directories such as OneDrive or SMB
    shares can transiently lock the temp file or destination and make the final
    replace time out or fail. Failed writes attempt immediate cleanup, but a
    locked sibling `.tmp` can remain; callers that write in those directories
    should periodically call `sweep_orphan_tmp(path.parent)` to remove old
    orphan temp files.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    fd_transferred = False
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            fd_transferred = True
            json.dump(data, f, indent=2, allow_nan=False)
            f.flush()
            _flush_and_fsync(f.fileno())
        Path(tmp_path).replace(path)
    except BaseException:
        # fd_transferred=True means os.fdopen took ownership; the with-block already
        # closed it. Only close manually if os.fdopen never ran (rare failure).
        if not fd_transferred:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        _cleanup_tmp(tmp_path)
        raise


def atomic_text_write(content: str, path: Path) -> None:
    """Write text to path atomically (temp file + rename).

    Creates parent directories if needed. On failure, cleans up the
    temp file and re-raises the exception.

    Caveat: cloud-synced or network-backed directories such as OneDrive or SMB
    shares can transiently lock the temp file or destination and make the final
    replace time out or fail. Failed writes attempt immediate cleanup, but a
    locked sibling `.tmp` can remain; callers that write in those directories
    should periodically call `sweep_orphan_tmp(path.parent)` to remove old
    orphan temp files.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    fd_transferred = False
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            fd_transferred = True
            f.write(content)
            f.flush()
            _flush_and_fsync(f.fileno())
        Path(tmp_path).replace(path)
    except BaseException:
        if not fd_transferred:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        _cleanup_tmp(tmp_path)
        raise


def _purge_legacy_locks(base: Path | None = None) -> int:
    """Item 2 (cycle 2): one-time migration that removes lock files whose
    content is not ASCII-decodable pure int. Legacy runs may have written PID
    files with UTF-8/BOM/CRLF; the cycle-2 `file_lock` path RAISES on such
    content rather than stealing — without this purge the first acquisition
    after upgrade would fail. Idempotent: files already clean are skipped.
    """
    from kb.config import PROJECT_ROOT

    scan_base = base if base is not None else PROJECT_ROOT / ".data"
    if not scan_base.exists():
        return 0
    purged = 0
    for lock_file in scan_base.rglob("*.lock"):
        try:
            text = lock_file.read_text(encoding="ascii")
            int(text.strip())
        except (OSError, UnicodeDecodeError, ValueError):
            try:
                lock_file.unlink(missing_ok=True)
                purged += 1
            except OSError as exc:  # pragma: no cover
                logger.warning("Failed to purge legacy lock %s: %s", lock_file, exc)
    if purged:
        logger.info("Purged %d legacy lock file(s) under %s", purged, scan_base)
    return purged


def sweep_orphan_tmp(directory: Path, *, max_age_seconds: float = 3600.0) -> int:
    """Remove old top-level atomic-write `.tmp` siblings from a directory.

    The input is resolved before scanning, then only files matching
    `directory.glob("*.tmp")` are considered. The scan is intentionally
    non-recursive so callers can sweep a directory of atomic-write siblings
    without deleting unrelated temp files in nested application data.

    A temp file is removed only when `time.time() - path.stat().st_mtime` is
    greater than `max_age_seconds`; fresh files are left in place because they
    may belong to an active writer. `OSError` from `stat()` or `unlink()` is
    logged at WARNING with the path and error detail, then swallowed so one
    locked, missing, or permission-denied temp file does not block the rest of
    the sweep.

    Returns the number of files successfully removed. Never raises past the
    boundary — a missing, non-directory, or permission-denied `directory` logs
    WARNING and returns 0 so callers (CLI boot, ingest tail, cleanup scripts)
    can invoke the sweep unconditionally without defensive pre-checks.
    """
    directory = Path(directory).resolve()
    if not directory.exists():
        logger.warning("sweep_orphan_tmp: directory does not exist: %s", directory)
        return 0
    if not directory.is_dir():
        logger.warning("sweep_orphan_tmp: path is not a directory: %s", directory)
        return 0

    removed = 0
    try:
        candidates = list(directory.glob("*.tmp"))
    except OSError as exc:
        logger.warning("Failed to scan tmp files in %s: %s", directory, exc)
        return removed

    for path in candidates:
        try:
            age_seconds = time.time() - path.stat().st_mtime
        except OSError as exc:
            logger.warning("Failed to stat tmp file %s: %s", path, exc)
            continue
        if age_seconds <= max_age_seconds:
            continue
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("Failed to remove tmp file %s: %s", path, exc)
            continue
        removed += 1
    return removed


def _ensure_legacy_locks_purged() -> None:
    """Cycle 2 PR review R1: run `_purge_legacy_locks` lazily on first
    `file_lock` acquisition rather than at module import. Avoids touching
    the real PROJECT_ROOT/.data/ directory during test collection or any
    other import-time path that doesn't actually acquire a lock.
    """
    global _legacy_locks_purged
    if _legacy_locks_purged:
        return
    with _legacy_locks_purge_lock:
        if _legacy_locks_purged:
            return
        try:
            _purge_legacy_locks()
        except Exception as exc:  # pragma: no cover — purge must not block acquire
            logger.warning("_purge_legacy_locks failed on first use: %s", exc)
        _legacy_locks_purged = True


def _backoff_sleep_interval(attempt_count: int) -> float:
    """Cycle 24 AC9 — compute the retry-sleep duration for ``file_lock``.

    Reads ``LOCK_INITIAL_POLL_INTERVAL`` and ``LOCK_POLL_INTERVAL`` from the
    module at CALL TIME (attribute lookup) so test monkeypatches on either
    constant take effect. Bounds the exponent at 30 to avoid ``OverflowError``
    under degenerate conditions (e.g., when ``LOCK_POLL_INTERVAL`` is
    monkeypatched to 0 and the caller spins); the cap clamps the duration to
    the current ``LOCK_POLL_INTERVAL`` value regardless.
    """
    # `min(..., 30)` prevents `2**attempt_count` from exploding into a bignum.
    # Once `2**30 * INITIAL` exceeds any reasonable CAP, further doubling is
    # irrelevant — the outer `min` with CAP already clamps the result.
    shift = min(attempt_count, 30)
    return min(LOCK_INITIAL_POLL_INTERVAL * (2**shift), LOCK_POLL_INTERVAL)


@contextmanager
def file_lock(path: Path, timeout: float | None = None):
    """Acquire a cross-process exclusive lock via a PID-stamped lock file.

    Writes the holder's PID to the lock file so that a timed-out waiter can
    verify the lock is stale (holder process no longer running) before stealing.

    Item 2 (cycle 2): PID files are read as ASCII; on decode/int failure the
    waiter RAISES rather than silently stealing — corruption is not proof of
    death.  Legacy non-ASCII lock files are purged once at module load.
    Item 1 (cycle 2): `acquired=True` is set only AFTER `os.write` returns
    successfully; the cleanup still runs via `finally` on partial writes.

    Raises TimeoutError if the lock is held by a running process.  Raises
    OSError on unparseable lock content (item 2).

    Windows PID-recycling caveat: stale-lock detection depends on the PID in
    the lock file. Windows can recycle PIDs, so a timed-out waiter can see a
    different live process with the same PID and avoid stealing the lock even
    though the original holder is gone. Investigate and delete such lock files
    manually when the owning process is known to be dead.

    Lock-order convention (Phase 4.5 HIGH cycle 1):
      page_path < history_path < contradictions_path < log_path < manifest_path
      (refine_page is the only nested-lock path today: page_path then history_path.)
    """
    _ensure_legacy_locks_purged()
    deadline_timeout = LOCK_TIMEOUT_SECONDS if timeout is None else timeout
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    my_pid_bytes = str(os.getpid()).encode("ascii")
    deadline = time.monotonic() + deadline_timeout
    acquired = False
    # Cycle 24 AC9 — exponential-backoff counter shared across all three
    # polling sites (normal retry, POSIX stale-steal, Windows stale-steal) per
    # design CONDITION 7. Incremented at every `time.sleep` call. Sleep duration
    # is `min(LOCK_INITIAL_POLL_INTERVAL * (2 ** attempt), LOCK_POLL_INTERVAL)`;
    # both constants read at CALL TIME (module attribute lookup) so
    # monkeypatching either one in tests takes effect immediately.
    attempt_count = 0
    # Cycle 32 AC6 — fair-queue position snapshot (intra-process only mitigation).
    # Pair with ``_release_waiter_slot()`` in the finally clause (C3 symmetry).
    position = _take_waiter_slot()
    try:
        # Cycle 32 C11 — one-shot initial stagger BEFORE retry loop, clamped
        # to ``LOCK_POLL_INTERVAL`` to prevent double-compounding with
        # exponential backoff (T7). Position=0 → zero stagger → no latency
        # change for uncontended acquires.
        if position > 0:
            stagger_s = min(
                position * _FAIR_QUEUE_STAGGER_MS / 1000.0,
                LOCK_POLL_INTERVAL,
            )
            time.sleep(stagger_s)
        while not acquired:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                write_ok = False
                try:
                    os.write(fd, my_pid_bytes)
                    write_ok = True
                    # Item 1 (cycle 2): mark acquired right after the WRITE
                    # succeeds so the outer `finally: if acquired: unlink`
                    # runs even if a later step (e.g. `os.close` interrupted
                    # by SIGINT) raises — preserves Phase 4.5 CRITICAL item 15
                    # "no orphan lock on SIGINT during acquire".
                    acquired = True
                finally:
                    os.close(fd)
                    # Cycle 2 PR review R3 MAJOR: if `os.write` raised, the lock
                    # file exists on disk with no PID content — unlink here so
                    # the next waiter doesn't see an empty file that the
                    # cycle-2 RAISE-on-unparseable policy (item 2) would
                    # permanently reject.
                    if not write_ok:
                        try:
                            lock_path.unlink(missing_ok=True)
                        except OSError:  # pragma: no cover — best effort
                            logger.warning(
                                "Failed to unlink orphan lock %s after write failure",
                                lock_path,
                            )
            except PermissionError as perm_exc:
                # Cycle 3 H2: a PermissionError from os.open(O_CREAT|O_EXCL) is
                # NOT evidence that the lock is held by another process — it
                # means the directory itself cannot be written (read-only mount,
                # AV-locked parent, EACCES from tightened ACLs). Retrying the
                # same create would spin the same permission error until the
                # deadline, then enter the stale-lock path that re-raises the
                # denied read as "PID dead → safe to steal" — silently
                # corrupting the verdict/feedback RMW chain. Raise immediately
                # so the operator sees the real bug.
                raise OSError(f"Cannot create lock at {lock_path}: {perm_exc}") from perm_exc
            except FileExistsError:
                if time.monotonic() > deadline:
                    # Item 2 (cycle 2): ASCII-only decode + int-parse. Any
                    # failure is a corruption signal, not proof of death —
                    # surface as OSError.
                    try:
                        content = lock_path.read_text(encoding="ascii")
                    except (OSError, UnicodeDecodeError) as exc:
                        raise OSError(
                            f"Lock {lock_path} has unparseable content: {exc!r}. "
                            "Corruption is not proof of death — investigate manually."
                        ) from exc
                    try:
                        stale_pid = int(content.strip())
                    except ValueError as exc:
                        raise OSError(
                            f"Lock {lock_path} content is not an integer PID: "
                            f"{content!r}. Investigate manually."
                        ) from exc
                    try:
                        os.kill(stale_pid, 0)
                    except ProcessLookupError:
                        # Unambiguous: PID doesn't exist — safe to steal.
                        lock_path.unlink(missing_ok=True)
                        time.sleep(_backoff_sleep_interval(attempt_count))
                        attempt_count += 1
                        continue
                    except OSError:
                        # Cycle 2 PR review R1: on POSIX a non-ProcessLookupError
                        # `OSError` from `os.kill(pid, 0)` (typically EPERM /
                        # PermissionError) means the process IS alive but owned
                        # by a different user — stealing would double-hold the
                        # lock. Raise TimeoutError instead. On Windows `os.kill`
                        # on a nonexistent PID raises generic `OSError`
                        # ([WinError 87]); treat as "unreachable → steal" since
                        # the lock file is a single-user artifact on that
                        # platform.
                        if _IS_WINDOWS:
                            lock_path.unlink(missing_ok=True)
                            time.sleep(_backoff_sleep_interval(attempt_count))
                            attempt_count += 1
                            continue
                        raise TimeoutError(
                            f"Lock {lock_path} held by running PID {stale_pid}. "
                            "Stop that process or delete the lock file."
                        ) from None
                    else:
                        raise TimeoutError(
                            f"Lock {lock_path} held by running PID {stale_pid}. "
                            "Stop that process or delete the lock file."
                        )
                time.sleep(_backoff_sleep_interval(attempt_count))
                attempt_count += 1
        yield
    finally:
        # Cycle 32 C3 — release waiter slot on every exit path (success,
        # TimeoutError, PermissionError, KeyboardInterrupt). Paired with
        # the ``_take_waiter_slot()`` call immediately before the try.
        _release_waiter_slot()
        if acquired:
            lock_path.unlink(missing_ok=True)
