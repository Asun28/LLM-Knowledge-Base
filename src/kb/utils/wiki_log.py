"""Wiki log utilities — append operation entries to wiki/log.md."""

import logging
from datetime import date
from pathlib import Path

from kb.config import WIKI_LOG

logger = logging.getLogger(__name__)


def append_wiki_log(operation: str, message: str, log_path: Path | None = None) -> None:
    """Append a timestamped entry to wiki/log.md.

    Creates the log file if it does not exist.

    Args:
        operation: Operation name (e.g., 'ingest', 'compile', 'lint', 'refine').
        message: Description of what happened.
        log_path: Path to log file (defaults to config WIKI_LOG).
    """
    log_path = log_path or WIKI_LOG
    entry = f"- {date.today().isoformat()} | {operation} | {message}\n"
    if not log_path.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("# Wiki Log\n\n", encoding="utf-8")
    content = log_path.read_text(encoding="utf-8")
    content += entry
    log_path.write_text(content, encoding="utf-8")
