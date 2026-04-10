"""Atomic file write utilities."""

import contextlib
import json
import os
import tempfile
from pathlib import Path


def atomic_json_write(data: object, path: Path) -> None:
    """Write data as JSON to path atomically (temp file + rename).

    Creates parent directories if needed. On failure, cleans up the
    temp file and re-raises the exception.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
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
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp_path).replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(tmp_fd)
        Path(tmp_path).unlink(missing_ok=True)
        raise
