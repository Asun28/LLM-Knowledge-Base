"""Wiki log utilities — append operation entries to wiki/log.md."""

import logging
import stat as _stat
from datetime import UTC, date, datetime
from pathlib import Path

from kb.utils.io import file_lock

logger = logging.getLogger(__name__)


LOG_SIZE_WARNING_BYTES = 500_000  # Rotation threshold — see _rotate_log_if_oversized.


def _rotate_log_if_oversized(log_path: Path) -> None:
    """Cycle 4 item #20 — monthly rotation with ordinal collision fallback.

    When ``log_path.stat().st_size`` exceeds ``LOG_SIZE_WARNING_BYTES``, rename
    the current log to ``log.YYYY-MM.md`` (or ``log.YYYY-MM.2.md`` on collision,
    etc.) and leave an empty fresh log for the next caller to create. Silent
    no-op if the file does not exist or is under threshold.

    Rotation event is logged at INFO BEFORE the rename so the audit chain is
    preserved even if the rename fails partway.
    """
    if not log_path.exists():
        return
    try:
        if log_path.stat().st_size <= LOG_SIZE_WARNING_BYTES:
            return
    except OSError:
        return
    stem = f"log.{datetime.now(UTC).strftime('%Y-%m')}"
    archive = log_path.parent / f"{stem}.md"
    ordinal = 2
    while archive.exists():
        archive = log_path.parent / f"{stem}.{ordinal}.md"
        ordinal += 1
    logger.info(
        "Rotating %s (%d bytes) → %s",
        log_path,
        log_path.stat().st_size,
        archive,
    )
    try:
        log_path.rename(archive)
    except OSError as e:
        logger.warning("Log rotation failed for %s: %s", log_path, e)


def append_wiki_log(operation: str, message: str, log_path: Path) -> None:
    """Append a timestamped entry to wiki/log.md.

    Creates the log file if it does not exist. Warns when log exceeds size threshold.
    Uses a file lock to prevent concurrent write corruption.
    On OSError, retries once then raises.

    Args:
        operation: Operation name (e.g., 'ingest', 'compile', 'lint', 'refine').
        message: Description of what happened.
        log_path: Path to log file (required — caller must pass the effective wiki_dir / "log.md").
    """
    # Item 8 (cycle 2): the log is pipe-delimited markdown that humans + LLMs both
    # parse. Leading `#`/`-`/`>`/`!` chars and `[[...]]` wikilinks render as active
    # headings, lists, callouts, and clickable links when viewed in Obsidian or
    # displayed back to the LLM — providing a log-injection vector via ingested
    # source content. Neutralize by prefixing a zero-width space so the text
    # remains readable but the Markdown parser no longer matches.
    _ZWSP = "\u200b"

    def _escape_markdown_prefix(field: str) -> str:
        field = field.replace("|", "/").replace("\n", " ").replace("\r", " ").replace("\t", " ")
        stripped = field.lstrip(" ")
        if stripped[:1] in {"#", "-", ">", "!"}:
            # Preserve the user's leading whitespace, prefix the ZWSP before the marker
            lead = field[: len(field) - len(stripped)]
            field = f"{lead}{_ZWSP}{stripped}"
        # Neutralize wikilinks anywhere in the text (audit log does not need live links)
        field = field.replace("[[", f"[{_ZWSP}[").replace("]]", f"]{_ZWSP}]")
        return field

    safe_op = _escape_markdown_prefix(operation)
    safe_msg = _escape_markdown_prefix(message)
    entry = f"- {date.today().isoformat()} | {safe_op} | {safe_msg}\n"

    # S1 (Phase 4.5 R5 HIGH): reject non-regular-file log targets up front.
    # On Windows, log_path.open("a") on a directory raises PermissionError
    # (not IsADirectoryError); on POSIX, a FIFO or socket can also mimic
    # existence. Symlinks follow by default with is_file(), so a symlink to
    # a regular file would pass — use lstat and S_ISLNK for the symlink
    # check, then verify the underlying mode is a regular file.
    # PR review round 1 (Sonnet MAJOR S1): `is_file()` alone followed the
    # symlink and returned True for symlink → regular file, silently
    # accepting what spec says should be rejected.
    def _reject_if_not_regular_file(p: Path) -> None:
        try:
            st = p.lstat()
        except FileNotFoundError:
            return
        if _stat.S_ISLNK(st.st_mode) or not _stat.S_ISREG(st.st_mode):
            raise OSError(
                f"Log target is not a regular file: {p} (directory, symlink, or special file)."
            )

    _reject_if_not_regular_file(log_path)
    # Cycle 4 item #20 — rotate BEFORE append if already oversized. Runs
    # outside the file_lock so the rename doesn't contend with readers.
    _rotate_log_if_oversized(log_path)
    if not log_path.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Item 29 (cycle 2): also force LF on initial creation.
            with log_path.open("x", encoding="utf-8", newline="\n") as f:
                f.write("# Wiki Log\n\n")
        except FileExistsError:
            # Another concurrent call created it first — re-check the target
            # type in case the concurrent creator produced a non-regular file.
            _reject_if_not_regular_file(log_path)

    def _write() -> None:
        # Item 29 (cycle 2): force LF on Windows — prevents mixed-EOL files (wiki_log
        # was the only writer using the default `newline=None` translation while
        # atomic_*_write already force LF), which breaks content_hash idempotency
        # and makes `git diff` noisy across Windows/Linux contributors.
        with file_lock(log_path):
            with log_path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(entry)

    try:
        _write()
    except OSError:
        # Retry once, then raise to caller.
        _write()
