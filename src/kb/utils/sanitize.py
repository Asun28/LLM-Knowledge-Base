"""Error-string sanitization helpers."""

from __future__ import annotations

import os
import re

_ABS_PATH_PATTERNS = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s'\"]+)"  # Windows: D:\foo\bar or D:/foo/bar
    r"|(?:\\\\\?\\[^\s'\"]+)"  # Windows UNC long-path: \\?\C:\...
    r"|(?:/(?:home|Users|opt|var|srv|tmp|mnt|root)/[^\s'\"]+)"  # POSIX absolute
)


def sanitize_error_text(exc: BaseException) -> str:
    """Render an exception string with absolute filesystem paths redacted."""
    s = str(exc)
    for attr in ("filename", "filename2"):
        fn = getattr(exc, attr, None)
        if fn and isinstance(fn, (str, os.PathLike)):
            fn_str = str(fn)
            if fn_str and fn_str in s:
                s = s.replace(fn_str, "<path>")
    return _ABS_PATH_PATTERNS.sub("<path>", s)
