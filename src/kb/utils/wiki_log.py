"""Wiki log utilities — append operation entries to wiki/log.md."""

import logging
import stat as _stat
from datetime import date
from pathlib import Path

from kb.utils.io import file_lock

logger = logging.getLogger(__name__)


LOG_SIZE_WARNING_BYTES = 500_000  # Warn when log exceeds ~500KB


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
    safe_op = operation.replace("|", "/").replace("\n", " ").replace("\r", " ").replace("\t", " ")
    safe_msg = message.replace("|", "/").replace("\n", " ").replace("\r", " ").replace("\t", " ")
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
            with log_path.open("x", encoding="utf-8") as f:
                f.write("# Wiki Log\n\n")
        except FileExistsError:
            # Another concurrent call created it first — re-check the target
            # type in case the concurrent creator produced a non-regular file.
            _reject_if_not_regular_file(log_path)

    def _write() -> None:
        with file_lock(log_path):
            with log_path.open("a", encoding="utf-8") as f:
                f.write(entry)
        log_stat = log_path.stat()
        if log_stat.st_size > LOG_SIZE_WARNING_BYTES:
            logger.warning(
                "Wiki log %s is large (%d bytes > %d threshold). Consider archiving.",
                log_path,
                log_stat.st_size,
                LOG_SIZE_WARNING_BYTES,
            )

    try:
        _write()
    except OSError:
        # Retry once, then raise to caller.
        _write()
