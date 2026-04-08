"""Markdown parsing helpers — wikilink extraction, frontmatter access."""

import re

WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def extract_wikilinks(text: str) -> list[str]:
    """Extract all [[wikilink]] targets from markdown text.

    Normalizes targets: strips whitespace, removes trailing .md.
    """
    raw = WIKILINK_PATTERN.findall(text)
    return [link.strip().removesuffix(".md").lower() for link in raw]


def extract_raw_refs(text: str) -> list[str]:
    """Extract all references to raw/ source files from markdown text."""
    matches = re.findall(r"raw/[\w/.-]+\.(?:md|txt|pdf|json|yaml|csv|png|jpg|jpeg|svg|gif)", text)
    # Reject path traversal — consistent with extract_citations()
    return [ref for ref in matches if ".." not in ref]
