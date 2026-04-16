"""Evidence trail — append-only provenance sections in wiki pages."""

import logging
import re
from datetime import date
from pathlib import Path

from kb.utils.io import atomic_text_write, file_lock

logger = logging.getLogger(__name__)

# H12 fix (Phase 4.5 HIGH): Sentinel that anchors evidence trail entries.
# FIRST-match heuristic: when upgrading a pre-sentinel page, place the sentinel
# at the end of the FIRST ## Evidence Trail section found (not LAST — attacker-planted
# forgeries land later in the body).
SENTINEL = "<!-- evidence-trail:begin -->"


def _neutralize_pipe(value: str) -> str:
    """Item 28 (cycle 2): backtick-wrap values containing `|` so the pipe is
    unambiguous inside the evidence-trail table-like row format.
    """
    if "|" in value:
        return f"`{value}`"
    return value


def build_evidence_entry(
    source_ref: str,
    action: str,
    entry_date: str | None = None,
) -> str:
    """Build a single evidence trail entry line (byte-clean stored form).

    Format: - YYYY-MM-DD | source_ref | action

    Cycle 2 PR review R1 MAJOR: the stored entry MUST stay byte-for-byte
    compatible with pre-cycle-2 evidence trails. Backtick-wrapping for
    pipe-containing values moves to `format_evidence_entry` (RENDER layer),
    which is now the single consumer used by `append_evidence_trail`.
    """
    d = entry_date or date.today().isoformat()
    return f"- {d} | {source_ref} | {action}"


def format_evidence_entry(date_str: str, source: str, summary: str) -> str:
    """Render an evidence trail line with backtick-escaped pipes (item 28).

    Cycle 2 PR review R3 MAJOR: signature restored to the original positional
    contract `(date_str, source, summary)` — callers that predated cycle 2
    (or internal call sites matching the high-cycle1 plan) keep working; only
    the internal pipe-escape behaviour changes. This is the render form that
    `append_evidence_trail` persists. The escape is applied render-time only —
    callers building the entry purely for logical comparison should use
    `build_evidence_entry` to preserve the raw string.
    """
    return f"- {date_str} | {_neutralize_pipe(source)} | {_neutralize_pipe(summary)}"


def append_evidence_trail(
    page_path: Path,
    source_ref: str,
    action: str,
    entry_date: str | None = None,
) -> None:
    """Append an evidence trail entry to a wiki page.

    If the page has no ## Evidence Trail section, one is created at the end.
    New entries are inserted right after the sentinel (reverse chronological).

    H12 fix (Phase 4.5 HIGH): Uses SENTINEL to anchor new entries.
    FIRST-match heuristic: when no sentinel exists, finds the FIRST
    ## Evidence Trail header (not LAST — attacker-planted forgeries land later
    in body), places the sentinel at end of that section's header line, then
    inserts new entry after sentinel.  When sentinel already present: inserts
    new entry right after the sentinel line.  When no ## Evidence Trail exists:
    creates section with sentinel.
    """
    # H2 fix (Phase 4.5 HIGH): lock the page file for the entire read→modify→write window
    # so concurrent append_evidence_trail calls on the same page don't lose entries.
    with file_lock(page_path):
        content = page_path.read_text(encoding="utf-8")
        d = entry_date or date.today().isoformat()
        entry = format_evidence_entry(d, source_ref, action)

        if SENTINEL in content:
            # Sentinel already present — insert new entry right after the sentinel line.
            sentinel_pos = content.index(SENTINEL)
            after_sentinel = sentinel_pos + len(SENTINEL)
            # Skip the newline immediately after the sentinel
            if after_sentinel < len(content) and content[after_sentinel] == "\n":
                after_sentinel += 1
            content = content[:after_sentinel] + entry + "\n" + content[after_sentinel:]
        else:
            # No sentinel yet — use FIRST-match heuristic.
            trail_match = re.search(r"^## Evidence Trail\r?\n", content, re.MULTILINE)
            if trail_match:
                # Place sentinel at end of the header line, then insert new entry.
                insert_pos = trail_match.end()
                content = (
                    content[:insert_pos] + SENTINEL + "\n" + entry + "\n" + content[insert_pos:]
                )
            else:
                # No ## Evidence Trail section exists — create one with sentinel.
                content = (
                    content.rstrip("\n")
                    + "\n\n## Evidence Trail\n"
                    + SENTINEL
                    + "\n"
                    + entry
                    + "\n"
                )

        atomic_text_write(content, page_path)
