"""Atomic file write utilities."""

import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


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
        Path(tmp_path).replace(path)
    except BaseException:
        # fd_transferred=True means os.fdopen took ownership; the with-block already
        # closed it. Only close manually if os.fdopen never ran (rare failure).
        if not fd_transferred:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        Path(tmp_path).unlink(missing_ok=True)
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
        Path(tmp_path).replace(path)
    except BaseException:
        if not fd_transferred:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        Path(tmp_path).unlink(missing_ok=True)
        raise


@contextmanager
def file_lock(path: Path, timeout: float = 5.0):
    """Acquire a cross-process exclusive lock via a PID-stamped lock file.

    Writes the holder's PID to the lock file so that a timed-out waiter can
    verify the lock is stale (holder process no longer running) before stealing.

    Raises TimeoutError if the lock is held by a running process.

    Lock-order convention (Phase 4.5 HIGH cycle 1):
      page_path < history_path < contradictions_path < log_path < manifest_path
      (refine_page is the only nested-lock path today: page_path then history_path.)
    """
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    my_pid_bytes = str(os.getpid()).encode()
    deadline = time.monotonic() + timeout
    acquired = False
    try:
        while not acquired:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                # Lock file now exists on disk; mark it so finally always cleans up.
                acquired = True
                try:
                    os.write(fd, my_pid_bytes)
                finally:
                    os.close(fd)
            except (FileExistsError, PermissionError):
                if time.monotonic() > deadline:
                    try:
                        stale_pid = int(lock_path.read_text().strip())
                        os.kill(stale_pid, 0)
                        raise TimeoutError(
                            f"Lock {lock_path} held by running PID {stale_pid}. "
                            "Stop that process or delete the lock file."
                        )
                    except (ValueError, OSError):
                        pass
                    lock_path.unlink(missing_ok=True)
                    time.sleep(0.05)
                    continue
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            lock_path.unlink(missing_ok=True)
