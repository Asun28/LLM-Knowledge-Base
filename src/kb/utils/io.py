"""Atomic file write utilities."""

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
LOCK_POLL_INTERVAL = 0.05

_IS_WINDOWS = sys.platform == "win32"
_legacy_locks_purged = False
_legacy_locks_purge_lock = threading.Lock()


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
    try:
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
            except (FileExistsError, PermissionError):
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
                        time.sleep(LOCK_POLL_INTERVAL)
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
                            time.sleep(LOCK_POLL_INTERVAL)
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
                time.sleep(LOCK_POLL_INTERVAL)
        yield
    finally:
        if acquired:
            lock_path.unlink(missing_ok=True)
