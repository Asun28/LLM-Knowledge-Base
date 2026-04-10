"""Wiki log utilities — append operation entries to wiki/log.md."""

import logging
from datetime import date
from pathlib import Path

from kb.config import WIKI_LOG

logger = logging.getLogger(__name__)


LOG_SIZE_WARNING_BYTES = 500_000  # Warn when log exceeds ~500KB


def append_wiki_log(operation: str, message: str, log_path: Path | None = None) -> None:
    """Append a timestamped entry to wiki/log.md.

    Creates the log file if it does not exist. Warns when log exceeds size threshold.

    Args:
        operation: Operation name (e.g., 'ingest', 'compile', 'lint', 'refine').
        message: Description of what happened.
        log_path: Path to log file (defaults to config WIKI_LOG).
    """
    log_path = log_path or WIKI_LOG
    safe_op = operation.replace("|", "-").replace("\n", " ").replace("\r", "")
    safe_msg = message.replace("|", "-").replace("\n", " ").replace("\r", "")
    entry = f"- {date.today().isoformat()} | {safe_op} | {safe_msg}\n"
    if not log_path.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with log_path.open("x", encoding="utf-8") as f:
                f.write("# Wiki Log\n\n")
        except FileExistsError:
            pass  # Another concurrent call created it first
    try:
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
    except OSError as e:
        logger.warning("Failed to append to wiki log %s: %s", log_path, e)
