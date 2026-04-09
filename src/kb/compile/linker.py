"""Wikilink resolution, cross-referencing, and backlink management."""

import logging
import re
from pathlib import Path

from kb.config import WIKI_DIR
from kb.graph.builder import page_id, scan_wiki_pages
from kb.utils.markdown import extract_wikilinks

logger = logging.getLogger(__name__)

# Regex for splitting frontmatter from body — correct for --- inside YAML values
_FRONTMATTER_RE = re.compile(r"\A(---\n.*?\n---\n?)(.*)", re.DOTALL)

# Regex for fenced code blocks (``` ... ```) and inline code (`...`)
_CODE_MASK_RE = re.compile(r"```.*?```|`[^`\n]+`", re.DOTALL)


def _mask_code_blocks(text: str) -> tuple[str, list[str]]:
    """Replace code blocks and inline code with null-byte placeholders."""
    masked: list[str] = []

    def _replace(m: re.Match) -> str:
        masked.append(m.group(0))
        return f"\x00CODE{len(masked) - 1}\x00"

    return _CODE_MASK_RE.sub(_replace, text), masked


def _unmask_code_blocks(text: str, masked: list[str]) -> str:
    """Restore code blocks and inline code from placeholders."""
    for i, code in enumerate(masked):
        text = text.replace(f"\x00CODE{i}\x00", code)
    return text


def resolve_wikilinks(wiki_dir: Path | None = None) -> dict:
    """Resolve all wikilinks across the wiki and report broken links.

    Returns:
        dict with keys: total_links, resolved, broken (list of {source, target}).
    """
    wiki_dir = wiki_dir or WIKI_DIR
    pages = scan_wiki_pages(wiki_dir)
    existing_ids = {page_id(p, wiki_dir).lower() for p in pages}

    total = 0
    resolved = 0
    broken = []

    for page_path in pages:
        try:
            content = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read %s for wikilink resolution: %s", page_path, e)
            continue
        links = extract_wikilinks(content)
        source_id = page_id(page_path, wiki_dir)

        for link in links:
            total += 1
            target = link
            if target in existing_ids:
                resolved += 1
            else:
                broken.append({"source": source_id, "target": target})

    return {"total_links": total, "resolved": resolved, "broken": broken}


def build_backlinks(wiki_dir: Path | None = None) -> dict[str, list[str]]:
    """Build a backlink index: for each page, list all pages that link to it.

    Returns:
        dict mapping page ID to list of page IDs that link to it.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    pages = scan_wiki_pages(wiki_dir)
    existing_ids = {page_id(p, wiki_dir).lower() for p in pages}
    backlinks: dict[str, list[str]] = {}

    for page_path in pages:
        try:
            content = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read %s for backlink index: %s", page_path, e)
            continue
        links = extract_wikilinks(content)
        source_id = page_id(page_path, wiki_dir)

        for link in links:
            target = link
            if target not in existing_ids:
                continue  # Skip broken links (consistent with build_graph)
            if target not in backlinks:
                backlinks[target] = []
            if source_id not in backlinks[target]:
                backlinks[target].append(source_id)

    return backlinks


def inject_wikilinks(
    title: str,
    target_page_id: str,
    wiki_dir: Path | None = None,
) -> list[str]:
    """Scan existing pages and inject wikilinks for mentions of a new page's title.

    Uses word-boundary matching (case-insensitive) to find plain-text mentions
    of the title in existing page bodies (not frontmatter). Skips pages that
    already link to the target or are the target page itself.

    Args:
        title: The title of the newly created page.
        target_page_id: Page ID of the new page (e.g., 'concepts/rag').
        wiki_dir: Path to wiki directory.

    Returns:
        List of page IDs that were updated with new wikilinks.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    target_page_id = target_page_id.lower()
    pages = scan_wiki_pages(wiki_dir)
    updated = []

    # Build regex for word-boundary match of the title (case-insensitive).
    # \b fails for titles starting/ending with non-word chars (C++, .NET, GPT-4o).
    # Use lookahead/lookbehind based on whether the first/last char is a word char.
    escaped_title = re.escape(title)
    starts_with_word = bool(title) and (title[0].isalnum() or title[0] == "_")
    ends_with_word = bool(title) and (title[-1].isalnum() or title[-1] == "_")
    left = r"\b" if starts_with_word else r"(?<![a-zA-Z0-9_])"
    right = r"\b" if ends_with_word else r"(?![a-zA-Z0-9_])"
    pattern = re.compile(left + escaped_title + right, re.IGNORECASE)

    for page_path in pages:
        pid = page_id(page_path, wiki_dir)

        # Skip self
        if pid == target_page_id:
            continue

        try:
            content = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # Skip if already links to target (case-insensitive — extract_wikilinks returns lowercased)
        existing_links = extract_wikilinks(content)
        if target_page_id in existing_links:
            continue

        # Split frontmatter from body — use regex to avoid splitting on --- inside YAML values
        fm_match = _FRONTMATTER_RE.match(content)
        if fm_match:
            frontmatter_section = fm_match.group(1)
            body = fm_match.group(2)
        else:
            frontmatter_section = ""
            body = content

        # Save original body for final comparison, then mask code blocks so
        # wikilink injection cannot touch content inside ``` ``` or `...` spans.
        original_body = body
        body, masked_code = _mask_code_blocks(body)

        # Check if title appears in body (outside code blocks)
        if not pattern.search(body):
            continue

        # Replace first occurrence in body with wikilink
        replacement = f"[[{target_page_id}|{title}]]"

        # Only replace plain text mentions (not already inside wikilinks)
        def _replace_if_not_in_wikilink(match):
            start = match.start()
            # Check if this match is already inside a [[ ]] pair
            before = body[:start]
            open_count = before.count("[[") - before.count("]]")
            if open_count > 0:
                logger.warning(
                    "inject_wikilinks: skipping replacement in %s "
                    "— unmatched [[ before position %d",
                    pid,
                    start,
                )
                return match.group(0)  # Inside a wikilink, don't replace
            return replacement

        new_body = pattern.sub(_replace_if_not_in_wikilink, body, count=1)

        # Restore code blocks before writing (compare against original to avoid
        # spurious writes when the only match was inside a code block)
        new_body = _unmask_code_blocks(new_body, masked_code)
        if new_body != original_body:
            page_path.write_text(frontmatter_section + new_body, encoding="utf-8")
            updated.append(pid)
            logger.info("Injected wikilink to %s in %s", target_page_id, pid)

    return updated
