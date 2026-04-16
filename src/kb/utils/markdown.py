"""Markdown parsing helpers — wikilink extraction, frontmatter access."""

import logging
import re

logger = logging.getLogger(__name__)

# Q_K_b fix (Phase 4.5 HIGH): raised from 200 to 500 chars to allow long-but-legitimate
# wikilink targets (real page IDs up to 500 chars). Targets >500 trigger a logger.warning
# (detected by _WIKILINK_OVERLENGTH_PATTERN which captures up to 600 chars).
WIKILINK_PATTERN = re.compile(r"(?<![!\[])\[\[([^\]|]{1,500})(?:\|[^\]]+)?\]\](?!\])")

# Wider pattern used only to detect and warn about overlength wikilink targets (501–600 chars).
# Deliberately limited to 600 so the regex engine doesn't scan unbounded content.
_WIKILINK_OVERLENGTH_PATTERN = re.compile(
    r"(?<![!\[])\[\[([^\]|]{501,600})(?:\|[^\]]+)?\]\](?!\])"
)

# Splits YAML frontmatter from page body. Matches the opening ``---`` fence,
# captures the entire frontmatter block and the remainder of the file.
FRONTMATTER_RE = re.compile(r"\A(---\r?\n.*?\r?\n---\r?\n?)(.*)", re.DOTALL)

# Matches raw/ file references that are NOT mid-URL (lookbehind rejects /, \w, and - before raw/)
_RAW_REF_PATTERN = re.compile(
    r"(?<![/\w-])raw/[\w/.-]+\.(?:md|txt|pdf|json|yaml|csv|png|jpg|jpeg|svg|gif)",
    re.IGNORECASE,
)


def extract_wikilinks(text: str) -> list[str]:
    """Extract all [[wikilink]] targets from markdown text.

    Normalizes targets: strips whitespace, removes trailing .md.
    Targets longer than 500 chars are rejected; a logger.warning is emitted
    for overlength targets detected by _WIKILINK_OVERLENGTH_PATTERN.
    """
    # Q_K_b fix (Phase 4.5 HIGH): warn about overlength targets (>500 chars) that
    # WIKILINK_PATTERN silently rejects (the main pattern only matches up to 500 chars).
    for overlength_match in _WIKILINK_OVERLENGTH_PATTERN.finditer(text):
        target = overlength_match.group(1)
        logger.warning(
            "Wikilink target exceeds 500-char cap (%d chars) — skipping: %r…",
            len(target),
            target[:40],
        )

    raw = WIKILINK_PATTERN.findall(text)
    result = []
    for link in raw:
        cleaned = link.strip().removesuffix(".md").lower()
        # Reject targets with embedded newlines — they produce broken page IDs
        if "\n" in cleaned or "\r" in cleaned:
            continue
        if not cleaned:  # fix item 12: drop whitespace-only targets
            continue
        result.append(cleaned)
    return result


def extract_raw_refs(text: str) -> list[str]:
    """Extract all references to raw/ source files from markdown text."""
    matches = _RAW_REF_PATTERN.findall(text)
    # Reject path traversal — consistent with extract_citations()
    return [ref for ref in matches if ".." not in ref]
