"""Error-string sanitization helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path

from kb.config import PROJECT_ROOT

_ABS_PATH_PATTERNS = re.compile(
    # Cycle 35 — `(?<![A-Za-z])` lookbehind prevents URI overmatch
    # (`https://host/path` no longer matches as `s://host/path`). Drive-letter
    # paths legitimately start at a word boundary in real logs.
    r"(?<![A-Za-z])(?:[A-Za-z]:[\\/][^\s'\"]+)"  # Windows: D:\foo\bar or D:/foo/bar
    r"|(?:\\\\\?\\[^\s'\"]+)"  # Windows UNC long-path: \\?\C:\...
    # Cycle 18 AC13 — ordinary UNC: \\server\share\path. `?` excluded from the
    # server segment so this alternative does not shadow the long-path form
    # (which starts with \\?\). Must appear AFTER the long-path alternative.
    r"|(?:\\\\[^\s\\'\"?]+\\[^\s\\'\"]+(?:\\[^\s'\"]*)?)"
    # Cycle 35 AC1b (T1b) — slash-form Windows UNC long-path: //?/UNC/server/share/...
    # Produced by `_rel(Path(fn_str))` slash-normalising `\\?\UNC\server\share\...`.
    # Must appear BEFORE the ordinary slash-UNC alternative (more specific first).
    r"|(?://\?/UNC/[^\s'\"?]+/[^\s'\"]+(?:/[^\s'\"]*)?)"
    # Cycle 35 AC1 (T1) — ordinary slash-UNC: //server/share/path. Produced by
    # `_rel(Path(fn_str))` slash-normalising `\\server\share\path`. The `(?<!:)`
    # lookbehind prevents URI overmatch (`https://host/path` would otherwise
    # collide with `//host/path`). The pattern requires THREE slash-separated
    # segments (host + share + path) so `//word/word` prose like a Markdown
    # `<!-- //tag/section -->` comment is NOT redacted (R1 Sonnet PR-49 MAJOR);
    # real UNC paths always have a file/path component after the share.
    r"|(?<!:)(?://[^\s'\"?/]+/[^\s'\"?/]+/[^\s'\"]+)"
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


def sanitize_text(s: str) -> str:
    """Redact absolute filesystem paths from a free-text string.

    Cycle 18 AC13 — string-only helper shared with `sanitize_error_text`.
    Does NOT perform exception-attribute handling; for that use
    `sanitize_error_text`. Does NOT accept Path arguments — the string form
    is for callers (e.g. `kb.ingest.pipeline._emit_ingest_jsonl`) that do
    not have Path context and only need regex-based redaction.

    Covered path shapes (via `_ABS_PATH_PATTERNS`):
    - Windows drive-letter with backslash or forward slash: `C:\\foo`, `C:/foo`.
    - Windows long-path UNC: `\\\\?\\C:\\foo`.
    - Ordinary UNC: `\\\\server\\share\\path`.
    - POSIX roots: `/home`, `/Users`, `/opt`, `/var`, `/srv`, `/tmp`, `/mnt`,
      `/root`.

    Input is NOT normalized (no case-folding, no slash-collapsing) so the
    original evidence string is preserved wherever no path pattern matches.
    """
    return _ABS_PATH_PATTERNS.sub("<path>", s)


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
            # Cycle 35 — OSError.__str__ doubles backslashes when rendering the
            # `filename` attribute (Windows-style paths). Probe both the raw
            # single-backslash form AND the doubled-backslash form so UNC and
            # ordinary Windows paths inside `str(exc)` both substitute. Cycle 33
            # documented the gap via xfail-strict; cycle-35 closes it here AND
            # adds slash-UNC regex alternatives in `_ABS_PATH_PATTERNS` for
            # direct `sanitize_text` callers (kb.ingest.pipeline._emit_*).
            candidates = [fn_str]
            if "\\" in fn_str:
                candidates.append(fn_str.replace("\\", "\\\\"))
            for cand in candidates:
                if cand and cand in s:
                    try:
                        s = s.replace(cand, _rel(Path(fn_str)))
                    except (TypeError, ValueError):
                        s = s.replace(cand, "<path>")
                    break
    # Cycle 18 AC13 — final regex sweep is delegated to `sanitize_text` so both
    # callers (exception form + JSONL string form) share the same redaction
    # regex. Order is preserved (caller-supplied paths → filename attrs →
    # regex sub) per cycle-10 L2.
    return sanitize_text(s)
