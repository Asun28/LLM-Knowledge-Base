"""Atomic file write utilities."""

import contextlib
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
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, allow_nan=False)
        Path(tmp_path).replace(path)
    except BaseException:
        # If os.fdopen succeeded, the with-block already closed the fd.
        # If os.fdopen failed (rare), tmp_fd is still open.
        with contextlib.suppress(OSError):
            os.close(tmp_fd)
        Path(tmp_path).unlink(missing_ok=True)
        raise


def atomic_text_write(content: str, path: Path) -> None:
    """Write text to path atomically (temp file + rename).

    Creates parent directories if needed. On failure, cleans up the
    temp file and re-raises the exception.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        Path(tmp_path).replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(tmp_fd)
        Path(tmp_path).unlink(missing_ok=True)
        raise


@contextmanager
def file_lock(path: Path, timeout: float = 5.0):
    """Acquire a cross-process exclusive lock via a PID-stamped lock file.

    Writes the holder's PID to the lock file so that a timed-out waiter can
    verify the lock is stale (holder process no longer running) before stealing.

    Raises TimeoutError if the lock is held by a running process.
    """
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    my_pid_bytes = str(os.getpid()).encode()
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, my_pid_bytes)
            os.close(fd)
            break
        except (FileExistsError, PermissionError):
            if time.monotonic() > deadline:
                # Stale lock — verify the recorded PID is no longer running
                try:
                    stale_pid = int(lock_path.read_text().strip())
                    os.kill(stale_pid, 0)  # Raises ProcessLookupError if dead
                    raise TimeoutError(
                        f"Lock {lock_path} held by running PID {stale_pid}. "
                        "Stop that process or delete the lock file."
                    )
                except (ValueError, OSError):
                    pass  # PID unreadable or process dead — safe to steal
                lock_path.unlink(missing_ok=True)
                time.sleep(0.05)
                continue
            time.sleep(0.05)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)
