"""Wiki log utilities — append operation entries to wiki/log.md."""

import logging
import stat as _stat
from datetime import UTC, date, datetime
from pathlib import Path

from kb.utils.io import file_lock

logger = logging.getLogger(__name__)


LOG_SIZE_WARNING_BYTES = 500_000  # Rotation threshold — see rotate_if_oversized.


def rotate_if_oversized(
    path: Path,
    max_bytes: int,
    archive_stem_prefix: str,
) -> None:
    """Generic size-based rotation — archive ``path`` when it exceeds ``max_bytes``.

    Renames the current file to ``<archive_stem_prefix>.YYYY-MM<path.suffix>``
    (with ordinal collision fallback like ``.2``, ``.3``, ...). Silent no-op if
    the file does not exist or is under threshold.

    The pre-rename ``logger.info("Rotating ...")`` audit event (moved here from
    the old ``_rotate_log_if_oversized`` per cycle 18 AC5) ensures that a mid-
    rotate crash leaves an audit trail even if the rename fails.

    Cycle 18 AC5 + AC12 — reused by both `append_wiki_log` (for ``wiki/log.md``)
    AND `kb.ingest.pipeline._emit_ingest_jsonl` (for ``.data/ingest_log.jsonl``).
    Archive suffix is derived from ``path.suffix`` so ``.jsonl`` files rotate to
    ``<stem>.YYYY-MM.jsonl``, ``.md`` files rotate to ``<stem>.YYYY-MM.md``, etc.
    """
    if not path.exists():
        return
    try:
        if path.stat().st_size <= max_bytes:
            return
    except OSError:
        return
    suffix = path.suffix or ""
    stem = f"{archive_stem_prefix}.{datetime.now(UTC).strftime('%Y-%m')}"
    archive = path.parent / f"{stem}{suffix}"
    ordinal = 2
    while archive.exists():
        archive = path.parent / f"{stem}.{ordinal}{suffix}"
        ordinal += 1
    logger.info(
        "Rotating %s (%d bytes) → %s",
        path,
        path.stat().st_size,
        archive,
    )
    try:
        path.rename(archive)
    except OSError as e:
        logger.warning("Log rotation failed for %s: %s", path, e)


def _rotate_log_if_oversized(log_path: Path) -> None:
    """Thin wrapper preserving the existing wiki/log.md call site.

    Cycle 18 AC5 — delegates to the generic ``rotate_if_oversized`` so the
    same logic can serve ``.data/ingest_log.jsonl`` in AC12.
    """
    rotate_if_oversized(log_path, LOG_SIZE_WARNING_BYTES, "log")


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
        # Cycle 18 AC4 — rotate INSIDE file_lock to close the POSIX handle-
        # holding-stale-file race (Phase 4.5 HIGH R5, threat T2). Under the
        # previous "rotate outside lock" ordering, a concurrent appender
        # holding an open handle while another process renamed the file
        # would silently write to the archived (renamed-away) file on POSIX.
        # Readers are brief; lock contention under rotation is negligible.
        # Item 29 (cycle 2): force LF on Windows — prevents mixed-EOL files
        # (wiki_log was the only writer using the default `newline=None`
        # translation while atomic_*_write already force LF), which breaks
        # content_hash idempotency and makes `git diff` noisy across Windows/
        # Linux contributors.
        with file_lock(log_path):
            _rotate_log_if_oversized(log_path)
            with log_path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(entry)

    try:
        _write()
    except OSError:
        # Retry once, then raise to caller.
        _write()
