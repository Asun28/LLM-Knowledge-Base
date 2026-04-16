"""Text utilities — slugify, YAML escaping, shared stopwords."""

import logging
import re

logger = logging.getLogger(__name__)


def truncate(msg: str, limit: int = 500) -> str:
    """Truncate long messages to avoid terminal / log flooding.

    Moved from `kb.cli._truncate` (cycle 2 PR review round 1 MAJOR — utility
    layer was creating a downward import into the CLI layer, risking circular
    imports when exercised on the LLM error path).
    """
    return msg if len(msg) <= limit else msg[:limit] + "..."


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

# C0/C1 control characters except \t (\x09), \n (\x0a), and \r (\x0d), which
# YAML handles natively. \x00 is stripped separately with a warning because a
# null byte is more likely a data-corruption signal than whitespace.
# Hoisted to module scope so yaml_sanitize does not recompile on every call.
_CTRL_CHAR_RE = re.compile(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f\x85]")


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
    text = re.sub(r"[^\w\s-]", "", text)  # keep CJK/Cyrillic (dropped re.ASCII)
    text = re.sub(r"[\s_]+", "-", text)
    result = re.sub(r"-+", "-", text).strip("-")
    if not result:
        import hashlib

        h = hashlib.sha256(text_lower.encode("utf-8")).hexdigest()[:6]
        return f"untitled-{h}"
    return result


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
    return _CTRL_CHAR_RE.sub("", value)


def yaml_escape(value: str) -> str:
    """Escape a string for safe YAML double-quote style.

    Strips Unicode bidi formatting marks (U+202A-202E, U+2066-2069) and C0/C1
    control characters, then escapes backslashes, double quotes, newlines,
    tabs, carriage returns, and null bytes.

    Delegates the stripping phase to yaml_sanitize so both helpers stay in
    sync if the stripped set ever expands (e.g. new bidi range added).
    """
    value = yaml_sanitize(value)
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


# Matches a whole line that is a YAML frontmatter fence (--- optionally followed by spaces/tabs).
_FRONTMATTER_FENCE_RE = re.compile(r"^---[ \t]*$", re.MULTILINE)

# Matches HTML comments including their content (greedy-safe via non-greedy).
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Matches markdown ATX headers at level 2 or deeper (##, ###, etc.) — whole line.
# Does NOT match level-1 headers (single #) to preserve legitimate page titles.
_MD_HEADER_RE = re.compile(r"^##+ .*$", re.MULTILINE)


def sanitize_extraction_field(value: str | None, max_len: int = 2000) -> str:
    """Sanitize an untrusted extraction_json string field before writing to wiki body.

    Strips prompt-injection vectors from LLM-supplied extraction fields:
    - C0/C1 control characters (via yaml_sanitize)
    - Frontmatter fence lines (``---``)
    - HTML comments ``<!-- ... -->``
    - Markdown headers at level 2+ (``##``, ``###``, …) — whole line removed
      to prevent ``## Review Checklist`` / ``## Evidence Trail`` forgeries
    - Truncates to ``max_len`` chars, appending ``... [truncated]`` marker

    Does NOT strip em-dashes (—), inline code (`…`), hyphenated year ranges
    (2024-25), or normal bullet list items (``- item``).

    Returns ``""`` for ``None`` or empty input.
    """
    if not value:
        return ""

    # 1. Strip control characters and bidi marks via the shared sanitizer.
    value = yaml_sanitize(value)

    # 2. Remove HTML comments (including content).
    value = _HTML_COMMENT_RE.sub("", value)

    # 3. Remove whole frontmatter fence lines.
    value = _FRONTMATTER_FENCE_RE.sub("", value)

    # 4. Remove markdown headers at level 2+.
    value = _MD_HEADER_RE.sub("", value)

    # 5. Length cap.
    if len(value) > max_len:
        value = value[:max_len] + "... [truncated]"

    return value


def wikilink_display_escape(title: str) -> str:
    """Escape a title for safe use as wikilink display text ``[[target|TITLE]]``.

    Replaces characters that would break the wikilink syntax or allow injection:
    - ``]`` → ``)``  (prevents early close-bracket escape)
    - ``[`` → ``(``  (prevents paired open-bracket)
    - ``|`` → `` ``  (pipe is the wikilink display separator)
    - newlines (``\\n``, ``\\r``) → `` ``  (wikilinks are single-line)
    """
    return (
        title.replace("]", ")")
        .replace("[", "(")
        .replace("|", " ")
        .replace("\n", " ")
        .replace("\r", " ")
    )
