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
# Phase 4.5 HIGH D3: bounded to 10 KB to prevent catastrophic backtracking on
# pages missing a closing fence. Interior ``---`` on indented lines (YAML block
# scalars) are correctly skipped because the regex requires ``\n---`` at col 0.
FRONTMATTER_RE = re.compile(r"\A(---[ \t]*\r?\n.{0,10000}?\r?\n---[ \t]*\r?\n?)(.*)", re.DOTALL)

# Matches raw/ file references that are NOT mid-URL (lookbehind rejects /, \w, and - before raw/)
_RAW_REF_PATTERN = re.compile(
    r"(?<![/\w-])raw/[\w/.-]+\.(?:md|txt|pdf|json|yaml|csv|png|jpg|jpeg|svg|gif)",
    re.IGNORECASE,
)

# P1 (Phase 4.5 R4 HIGH): strip fenced code blocks and inline code spans
# before wikilink + raw-ref matching. Without this, documentation of wiki
# syntax (e.g. a README showing `[[concepts/rag]]`) is treated as a real
# edge and pollutes the graph + dead-link lint + BM25.
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _strip_code_spans_and_fences(text: str) -> str:
    """Return text with fenced code blocks, inline code spans, and YAML
    frontmatter replaced by spaces. Preserves character offsets for
    downstream regex correctness when callers expect line-by-line parity.
    """
    # Strip frontmatter first (anchored) so code fences in the body aren't
    # confused with the YAML fence.
    m = FRONTMATTER_RE.match(text)
    if m:
        # Replace frontmatter block with equivalent-length blanks to preserve
        # line numbers in any caller that uses offsets from the stripped view.
        fm_block = m.group(1)
        text = " " * len(fm_block) + m.group(2)
    text = _FENCED_CODE_RE.sub(lambda m: " " * len(m.group(0)), text)
    text = _INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), text)
    return text


def extract_wikilinks(text: str) -> list[str]:
    """Extract all [[wikilink]] targets from markdown text.

    Normalizes targets: strips whitespace, removes trailing .md.
    Targets longer than 500 chars are rejected; a logger.warning is emitted
    for overlength targets detected by _WIKILINK_OVERLENGTH_PATTERN.

    P1 (Phase 4.5 R4 HIGH): strips fenced code blocks, inline code spans,
    and YAML frontmatter before pattern matching. Documented wiki-syntax
    examples (`[[concepts/rag]]` inside a ``` block) no longer manufacture
    fake edges.
    """
    stripped = _strip_code_spans_and_fences(text)
    # Q_K_b fix (Phase 4.5 HIGH): warn about overlength targets (>500 chars) that
    # WIKILINK_PATTERN silently rejects (the main pattern only matches up to 500 chars).
    for overlength_match in _WIKILINK_OVERLENGTH_PATTERN.finditer(stripped):
        target = overlength_match.group(1)
        logger.warning(
            "Wikilink target exceeds 500-char cap (%d chars) — skipping: %r…",
            len(target),
            target[:40],
        )

    raw = WIKILINK_PATTERN.findall(stripped)
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
