"""Error-string sanitization helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path

from kb.config import PROJECT_ROOT

_ABS_PATH_PATTERNS = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s'\"]+)"  # Windows: D:\foo\bar or D:/foo/bar
    r"|(?:\\\\\?\\[^\s'\"]+)"  # Windows UNC long-path: \\?\C:\...
    r"|(?:/(?:home|Users|opt|var|srv|tmp|mnt|root)/[^\s'\"]+)"  # POSIX absolute
)


def _rel(path: Path | None) -> str:
    """Return path relative to project root with forward slashes."""
    if path is None:
        return "<path>"
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except (AttributeError, TypeError):
        return str(path).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def sanitize_error_text(exc: BaseException, *paths: Path | None) -> str:
    """Render an exception string with absolute filesystem paths redacted."""
    s = str(exc)
    for p in paths:
        if p is None:
            continue
        try:
            abs_s = str(p)
        except Exception:  # noqa: BLE001 — defensive for weird Path subclasses
            continue
        if abs_s and abs_s in s:
            s = s.replace(abs_s, _rel(p))
    for attr in ("filename", "filename2"):
        fn = getattr(exc, attr, None)
        if fn and isinstance(fn, (str, os.PathLike)):
            fn_str = str(fn)
            if fn_str and fn_str in s:
                try:
                    s = s.replace(fn_str, _rel(Path(fn_str)))
                except (TypeError, ValueError):
                    s = s.replace(fn_str, "<path>")
    return _ABS_PATH_PATTERNS.sub("<path>", s)
