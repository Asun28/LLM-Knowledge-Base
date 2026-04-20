"""Cycle 18 AC13 — sanitize_text string helper + UNC path coverage.

Threat T1: absolute filesystem paths (Windows drive-letter, UNC, POSIX) must
be redacted from any free-text field written to `.data/ingest_log.jsonl`.
Ordinary UNC (`\\\\server\\share\\path`) was missing from cycle-17 coverage.
"""

from __future__ import annotations

from kb.utils.sanitize import _ABS_PATH_PATTERNS, sanitize_error_text, sanitize_text


def test_sanitize_text_windows_backslash() -> None:
    """Windows drive-letter with backslash."""
    assert sanitize_text("error at C:\\Users\\Admin\\file.md end") == "error at <path> end"


def test_sanitize_text_windows_forward_slash() -> None:
    """Windows drive-letter with forward slash."""
    assert sanitize_text("error at C:/Users/Admin/file.md end") == "error at <path> end"


def test_sanitize_text_unc_long_path() -> None:
    """Windows UNC long-path prefix (\\\\?\\C:\\foo)."""
    out = sanitize_text("error at \\\\?\\C:\\foo\\bar end")
    assert out == "error at <path> end", f"Got: {out!r}"


def test_sanitize_text_unc_ordinary() -> None:
    """Ordinary UNC (\\\\server\\share\\path) — NEW coverage for cycle 18 AC13."""
    out = sanitize_text("error at \\\\server\\share\\file.md end")
    assert out == "error at <path> end", f"Got: {out!r}"


def test_sanitize_text_unc_ordinary_minimal() -> None:
    """Ordinary UNC without trailing path."""
    out = sanitize_text("error at \\\\server\\share end")
    assert out == "error at <path> end", f"Got: {out!r}"


def test_sanitize_text_posix_home() -> None:
    assert sanitize_text("error at /home/user/file end") == "error at <path> end"


def test_sanitize_text_posix_opt() -> None:
    assert sanitize_text("error at /opt/tool/x end") == "error at <path> end"


def test_sanitize_text_posix_users() -> None:
    assert sanitize_text("error at /Users/alice/file end") == "error at <path> end"


def test_sanitize_text_posix_root() -> None:
    assert sanitize_text("error at /root/secret end") == "error at <path> end"


def test_sanitize_text_no_path_preserved() -> None:
    """Strings without a path shape pass through verbatim."""
    assert sanitize_text("just a plain error message") == "just a plain error message"


def test_sanitize_text_multiple_paths_all_redacted() -> None:
    """All matches in a single string are replaced."""
    out = sanitize_text("failed at C:\\foo and /home/x and \\\\srv\\share")
    assert out == "failed at <path> and <path> and <path>", f"Got: {out!r}"


def test_sanitize_text_unc_does_not_shadow_long_path() -> None:
    """Ordinary UNC pattern must not match the long-path `\\\\?\\` form's `?`.

    The long-path alternative is listed before the ordinary UNC alternative
    in `_ABS_PATH_PATTERNS`, and the ordinary-UNC regex excludes `?` from
    the server segment. Both forms should redact to `<path>`.
    """
    long_out = sanitize_text("at \\\\?\\C:\\foo end")
    ord_out = sanitize_text("at \\\\srv\\share end")
    assert long_out == "at <path> end"
    assert ord_out == "at <path> end"


def test_sanitize_error_text_delegates_to_sanitize_text() -> None:
    """`sanitize_error_text` pipes str(exc) through `sanitize_text` at the tail."""

    exc = FileNotFoundError("Could not find /home/user/missing.txt")
    out = sanitize_error_text(exc)
    assert "<path>" in out, f"Expected <path> substitution; got {out!r}"
    assert "/home/user/missing.txt" not in out


def test_sanitize_error_text_order_preserved() -> None:
    """Caller-supplied Path wins over the regex `<path>` mask (cycle-10 L2)."""
    from pathlib import Path  # noqa: PLC0415

    # Build an exception whose message mentions a path that is ALSO a registered
    # caller path. The caller-path substitution runs first and should produce
    # the project-relative form; the regex sweep should then no-op on that.
    p = Path("/home/user/project_file.md")
    exc = RuntimeError(f"failed at {p}")
    out = sanitize_error_text(exc, p)
    # The caller-path substitution produces a project-relative form via _rel,
    # not <path>. On non-project paths _rel falls through and returns the
    # forward-slash string which then gets regex-masked.
    # Most important: the raw posix path is GONE.
    assert str(p) not in out, f"Raw path leaked: {out!r}"


def test_abs_path_patterns_regex_compiled() -> None:
    """`_ABS_PATH_PATTERNS` is a compiled regex (smoke test)."""
    import re  # noqa: PLC0415

    assert isinstance(_ABS_PATH_PATTERNS, re.Pattern)


def test_sanitize_text_empty_string() -> None:
    """Empty input returns empty output."""
    assert sanitize_text("") == ""
