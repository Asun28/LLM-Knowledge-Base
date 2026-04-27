"""Inline callout lint checks."""

import logging
import re
from pathlib import Path

from kb.config import CALLOUT_MARKERS
from kb.lint import checks
from kb.utils.pages import page_id, scan_wiki_pages

logger = logging.getLogger(__name__)


_CALLOUTS_PER_PAGE_CAP: int = 500
_CALLOUTS_CROSS_PAGE_CAP: int = 10_000
# R1 Sonnet Minor 4 — codepoint-based cap (not byte cap). `len(str)` counts
# codepoints in Python; CJK UTF-8 encodes at 3 bytes/char so a 1 M-codepoint
# cap can represent up to ~3 MiB on-disk. The DoS target is regex-engine
# backtracking time, which is bounded by codepoint count, so the cap is
# correct for its intent; the prior name `_CALLOUT_BODY_BYTE_CAP` was
# misleading. T5 bound preserved.
_CALLOUT_BODY_CHAR_CAP: int = 1_048_576  # ~1 M codepoints

_CALLOUT_MARKER_PATTERN = "|".join(re.escape(m) for m in CALLOUT_MARKERS)
_CALLOUT_RE = re.compile(
    r"^> \[!(" + _CALLOUT_MARKER_PATTERN + r")\][^\n]*$",
    re.MULTILINE | re.IGNORECASE,
)


def parse_inline_callouts(content: str) -> list[dict]:
    """Return Obsidian-style callouts `> [!marker] text` from ``content``.

    Cycle 16 AC11 / T5 / T12.

    Returns list of ``{"marker": str, "line": int, "text": str}``.
    - ``marker`` is lowercased (regex is case-insensitive per AC11).
    - ``line`` is 1-based.
    - ``text`` is the full matched line (``> [!…] …``).

    Bounded: input > ``_CALLOUT_BODY_BYTE_CAP`` returns ``[]`` (T5 page-body
    DoS mitigation). Per-page cap: ``_CALLOUTS_PER_PAGE_CAP`` matches,
    then appends a ``{"marker": "__truncated__", ...}`` sentinel and stops.
    """
    if len(content) > _CALLOUT_BODY_CHAR_CAP:
        return []

    out: list[dict] = []
    for m in _CALLOUT_RE.finditer(content):
        if len(out) >= _CALLOUTS_PER_PAGE_CAP:
            out.append(
                {
                    "marker": "__truncated__",
                    "line": 0,
                    "text": f"truncated at {_CALLOUTS_PER_PAGE_CAP} matches",
                }
            )
            break
        line_number = content.count("\n", 0, m.start()) + 1
        out.append(
            {
                "marker": m.group(1).lower(),
                "line": line_number,
                "text": m.group(0),
            }
        )
    return out


def check_inline_callouts(
    wiki_dir: Path | None = None, pages: list[Path] | None = None
) -> list[dict]:
    """Aggregate inline callouts across the wiki for lint reporting.

    Cycle 16 AC12 / T5 / T12.

    Returns dicts: ``{"page_id", "marker", "line", "text"}``. Unreadable
    pages are logged and skipped (consistent with other checks). Cross-page
    cap: ``_CALLOUTS_CROSS_PAGE_CAP`` — adds a truncation record and breaks
    when exceeded.
    """
    wiki_dir = wiki_dir or checks.WIKI_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)

    out: list[dict] = []
    for p in pages:
        try:
            content = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Skipping unreadable page %s in callout scan: %s", p, e)
            continue
        try:
            pid = page_id(p, wiki_dir)
        except (OSError, ValueError) as e:
            logger.warning("Skipping unresolvable page_id for %s: %s", p, e)
            continue

        for entry in checks.parse_inline_callouts(content):
            if len(out) >= _CALLOUTS_CROSS_PAGE_CAP:
                out.append(
                    {
                        "page_id": "__truncated__",
                        "marker": "__truncated__",
                        "line": 0,
                        "text": f"truncated at {_CALLOUTS_CROSS_PAGE_CAP} matches",
                    }
                )
                return out
            out.append(
                {
                    "page_id": pid,
                    "marker": entry["marker"],
                    "line": entry["line"],
                    "text": entry["text"],
                }
            )
    return out
