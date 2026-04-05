"""Markdown parsing helpers — wikilink extraction, frontmatter access."""

import re

WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def extract_wikilinks(text: str) -> list[str]:
    """Extract all [[wikilink]] targets from markdown text."""
    return WIKILINK_PATTERN.findall(text)


def extract_raw_refs(text: str) -> list[str]:
    """Extract all references to raw/ source files from markdown text."""
    return re.findall(r"raw/[\w/.-]+\.(?:md|txt|pdf|json|yaml)", text)
