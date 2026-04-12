"""Text utilities — slugify, YAML escaping."""

import logging
import re

logger = logging.getLogger(__name__)

# Module-level symbol map for slugify — avoids recreating on each call
_SLUGIFY_SYMBOL_MAP = {
    "c++": "cpp",
    "c#": "csharp",
    "f#": "fsharp",
    ".net": "dotnet",
    "c/c++": "c-cpp",
}


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug.

    Strips punctuation, collapses whitespace/underscores to hyphens,
    and lowercases. Preserves semantically significant symbols
    (+, #, .) via a word-substitution map to prevent collisions
    (e.g., C vs C++ vs C#).
    """
    text_lower = text.lower().strip()
    for symbol, replacement in _SLUGIFY_SYMBOL_MAP.items():
        if text_lower == symbol:
            return replacement
    # General case: replace trailing ++ or # (word-suffix) but strip mid-word symbols
    text = text.lower().strip()
    # Replace suffix symbols that follow a word character (e.g. "mylib++" → "mylibplus")
    text = re.sub(r"(\w)\+\+", r"\1plus", text)
    text = re.sub(r"(\w)#", r"\1sharp", text)
    text = re.sub(r"(?<=\d)\.(?=\d)", "-", text)
    text = re.sub(r"[^\w\s-]", "", text, flags=re.ASCII)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def yaml_escape(value: str) -> str:
    """Escape a string for safe YAML double-quote style.

    Handles backslashes, double quotes, newlines, tabs, carriage returns, and null bytes.
    """
    if "\0" in value:
        logger.warning("Null byte removed from YAML value (possible data corruption)")
        value = value.replace("\0", "")
    value = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f\x85]", "", value)
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
