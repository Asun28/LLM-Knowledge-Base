"""Wiki log utilities — append operation entries to wiki/log.md."""

import logging
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
    if not log_path.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with log_path.open("x", encoding="utf-8") as f:
                f.write("# Wiki Log\n\n")
        except FileExistsError:
            # Another concurrent call created it first — usually fine, but
            # S1 (Phase 4.5 R5 HIGH): verify the now-existing target is a
            # regular file. On Windows, a symlink to nowhere or a special
            # file (FIFO, socket on POSIX) can also raise FileExistsError
            # from open("x"), and the follow-up open("a") on a non-regular
            # path either silently writes to a device or raises a
            # misleading second error. Surface the real issue instead.
            if not log_path.is_file():
                raise OSError(
                    f"Log target is not a regular file: {log_path} "
                    f"(directory, symlink, or special file)."
                )

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
