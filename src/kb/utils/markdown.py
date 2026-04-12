"""Markdown parsing helpers — wikilink extraction, frontmatter access."""

import re

WIKILINK_PATTERN = re.compile(r"(?<![!\[])\[\[([^\]|]{1,200})(?:\|[^\]]+)?\]\](?!\])")

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
    """
    raw = WIKILINK_PATTERN.findall(text)
    result = []
    for link in raw:
        cleaned = link.strip().removesuffix(".md").lower()
        # Reject targets with embedded newlines — they produce broken page IDs
        if "\n" in cleaned or "\r" in cleaned:
            continue
        result.append(cleaned)
    return result


def extract_raw_refs(text: str) -> list[str]:
    """Extract all references to raw/ source files from markdown text."""
    matches = _RAW_REF_PATTERN.findall(text)
    # Reject path traversal — consistent with extract_citations()
    return [ref for ref in matches if ".." not in ref]
