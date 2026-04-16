"""Evidence trail — append-only provenance sections in wiki pages."""

import re
from datetime import date
from pathlib import Path

from kb.utils.io import atomic_text_write, file_lock


def build_evidence_entry(
    source_ref: str,
    action: str,
    entry_date: str | None = None,
) -> str:
    """Build a single evidence trail entry line.

    Format: - YYYY-MM-DD | source_ref | action
    """
    d = entry_date or date.today().isoformat()
    return f"- {d} | {source_ref} | {action}"


def format_evidence_entry(date_str: str, source: str, summary: str) -> str:
    """Format a single evidence trail entry line (alternative signature).

    Convenience wrapper around build_evidence_entry for callers that have
    already computed the date string and prefer named arguments.
    """
    return build_evidence_entry(source_ref=source, action=summary, entry_date=date_str)


def append_evidence_trail(
    page_path: Path,
    source_ref: str,
    action: str,
    entry_date: str | None = None,
) -> None:
    """Append an evidence trail entry to a wiki page.

    If the page has no ## Evidence Trail section, one is created at the end.
    New entries are inserted at the top of the trail (reverse chronological).
    """
    # H2 fix (Phase 4.5 HIGH): lock the page file for the entire read→modify→write window
    # so concurrent append_evidence_trail calls on the same page don't lose entries.
    with file_lock(page_path):
        content = page_path.read_text(encoding="utf-8")
        entry = build_evidence_entry(source_ref, action, entry_date)

        trail_match = re.search(r"^## Evidence Trail\r?\n", content, re.MULTILINE)
        if trail_match:
            # Insert new entry right after the header
            insert_pos = trail_match.end()
            content = content[:insert_pos] + entry + "\n" + content[insert_pos:]
        else:
            # Add new section at the end
            content = content.rstrip("\n") + "\n\n## Evidence Trail\n" + entry + "\n"

        atomic_text_write(content, page_path)
