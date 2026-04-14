"""Text utilities — slugify, YAML escaping, shared stopwords."""

import logging
import re

logger = logging.getLogger(__name__)

# Union of stopwords from kb.query.bm25 and kb.ingest.contradiction.
# Single source of truth — both modules import from here.
STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "about",
        "after",
        "all",
        "also",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "each",
        "else",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "just",
        "may",
        "might",
        "more",
        "most",
        "new",
        "not",
        "of",
        "on",
        "only",
        "or",
        "other",
        "our",
        "out",
        "over",
        "shall",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
    }
)

# Module-level symbol map for slugify — avoids recreating on each call
_SLUGIFY_SYMBOL_MAP = {
    "c++": "cpp",
    "c#": "csharp",
    "f#": "fsharp",
    ".net": "dotnet",
    "c/c++": "c-cpp",
}

# Unicode bidirectional formatting marks (LRE/RLE/PDF/LRO/RLO/LRI/RLI/FSI/PDI).
# Strip from any string we YAML-encode to defend against audit-log confusion
# attacks (e.g. an LLM-supplied title rendering backward in terminals).
_BIDI_RE = re.compile(r"[\u202a-\u202e\u2066-\u2069]")


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


def yaml_sanitize(value: str) -> str:
    """Strip bidi marks and control characters WITHOUT escaping.

    Use when the sanitized string will be handed to a YAML serializer
    (yaml.dump) that already performs escaping — passing yaml_escape()
    output to yaml.dump double-escapes backslashes/quotes/newlines.
    """
    value = _BIDI_RE.sub("", value)
    if "\0" in value:
        logger.warning("Null byte removed from YAML value (possible data corruption)")
        value = value.replace("\0", "")
    return re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f\x85]", "", value)


def yaml_escape(value: str) -> str:
    """Escape a string for safe YAML double-quote style.

    Strips Unicode bidi formatting marks (U+202A-202E, U+2066-2069) and C0/C1
    control characters, then escapes backslashes, double quotes, newlines,
    tabs, carriage returns, and null bytes.
    """
    value = _BIDI_RE.sub("", value)
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
