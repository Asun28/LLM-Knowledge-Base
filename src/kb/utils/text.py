"""Text utilities — slugify, YAML escaping."""

import re


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug.

    Strips punctuation, collapses whitespace/underscores to hyphens,
    and lowercases. Returns empty string for all-punctuation input.
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def yaml_escape(value: str) -> str:
    """Escape a string for safe YAML double-quote style.

    Handles backslashes, double quotes, newlines, tabs, carriage returns, and null bytes.
    """
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
        .replace("\0", "")
    )
