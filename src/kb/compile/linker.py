"""Wikilink resolution, cross-referencing, and backlink management."""

import logging
import re
import uuid
from pathlib import Path

from kb.config import WIKI_DIR
from kb.utils.io import atomic_text_write
from kb.utils.markdown import FRONTMATTER_RE as _FRONTMATTER_RE
from kb.utils.markdown import extract_wikilinks
from kb.utils.pages import page_id, scan_wiki_pages
from kb.utils.text import wikilink_display_escape

logger = logging.getLogger(__name__)


def _check_not_in_wikilink(match: re.Match, body: str, pid: str, replacement: str) -> str | None:
    """Return replacement text if match is not inside an open [[ ]], else None.

    Defined at module scope so inject_wikilinks does not re-create it on every
    loop iteration (avoids the function-redefinition-in-loop anti-pattern).
    """
    start = match.start()
    before = body[:start]
    open_count = before.count("[[") - before.count("]]")
    if open_count > 0:
        logger.warning(
            "inject_wikilinks: skipping replacement in %s — unmatched [[ before position %d",
            pid,
            start,
        )
        return None
    return replacement


# Regex for fenced code blocks (``` ... ```), inline code (`...`),
# markdown links ([text](url)), and images (![alt](url)).
_CODE_MASK_RE = re.compile(
    r"```.*?```|~~~.*?~~~|`[^`\n]+`"
    r"|!\[(?:[^\]]*)\]\((?:[^()]*|\([^()]*\))*\)"
    r"|\[(?:[^\]]*)\]\((?:[^()]*|\([^()]*\))*\)",
    re.DOTALL,
)


def _mask_code_blocks(text: str) -> tuple[str, list[str], str]:
    """Replace code blocks, inline code, and markdown links with null-byte placeholders.

    Returns:
        Tuple of (masked_text, list_of_originals, prefix) where prefix is a
        per-call UUID hex string used to prevent placeholder collisions.
    """
    masked: list[str] = []
    prefix = uuid.uuid4().hex[:8]

    def _replace(m: re.Match) -> str:
        masked.append(m.group(0))
        return f"\x00{prefix}{len(masked) - 1}\x00"

    return _CODE_MASK_RE.sub(_replace, text), masked, prefix


def _unmask_code_blocks(text: str, masked: list[str], prefix: str) -> str:
    """Restore code blocks and inline code from placeholders."""
    for i, code in enumerate(masked):
        text = text.replace(f"\x00{prefix}{i}\x00", code)
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
        # Strip frontmatter before extracting wikilinks to avoid false matches in YAML values
        fm_match = _FRONTMATTER_RE.match(content)
        body = fm_match.group(2) if fm_match else content
        links = extract_wikilinks(body)
        source_id = page_id(page_path, wiki_dir).lower()

        for link in links:
            total += 1
            target = link
            if target in existing_ids:
                resolved += 1
            else:
                broken.append({"source": source_id, "target": target})

    return {"total_links": total, "resolved": resolved, "broken": broken}


def build_backlinks(
    wiki_dir: Path | None = None,
    *,
    pages: list[dict] | None = None,
) -> dict[str, list[str]]:
    """Build a backlink index: for each page, list all pages that link to it.

    Args:
        wiki_dir: Path to wiki directory. Uses config default if None.
        pages: Pre-loaded page dicts (id, path, content keys). When provided,
            skips disk I/O — avoids redundant reads when callers already
            loaded pages. Cycle 7 AC10.

    Returns:
        dict mapping page ID to list of page IDs that link to it.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    backlinks: dict[str, set[str]] = {}

    if pages is not None:
        # Cycle 7 AC10: use pre-loaded bundle. Expected dict keys: id, content.
        existing_ids = {p["id"].lower() for p in pages}
        for p in pages:
            content = p.get("content", "")
            fm_match = _FRONTMATTER_RE.match(content)
            body = fm_match.group(2) if fm_match else content
            links = extract_wikilinks(body)
            source_id = p["id"].lower()
            for link in links:
                if link not in existing_ids:
                    continue
                backlinks.setdefault(link, set()).add(source_id)
    else:
        page_paths = scan_wiki_pages(wiki_dir)
        existing_ids = {page_id(p, wiki_dir).lower() for p in page_paths}

        for page_path in page_paths:
            try:
                content = page_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Failed to read %s for backlink index: %s", page_path, e)
                continue
            # Strip frontmatter before extracting wikilinks to avoid false matches in YAML values
            fm_match = _FRONTMATTER_RE.match(content)
            body = fm_match.group(2) if fm_match else content
            links = extract_wikilinks(body)
            # Lowercase source_id to match the lowercased keys in existing_ids
            source_id = page_id(page_path, wiki_dir).lower()

            for link in links:
                target = link
                if target not in existing_ids:
                    continue  # Skip broken links (consistent with build_graph)
                backlinks.setdefault(target, set()).add(source_id)

    return {k: sorted(v) for k, v in backlinks.items()}


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
    if not title or not title.strip():
        return []

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

        # Item 26 (cycle 2): match frontmatter ONCE per page and reuse the
        # result for both the "existing links" guard and the body/frontmatter
        # split. At 5k pages × N titles per ingest this halves FRONTMATTER_RE
        # cost in the inject_wikilinks hot path.
        fm_match = _FRONTMATTER_RE.match(content)
        if fm_match:
            frontmatter_section = fm_match.group(1)
            body = fm_match.group(2)
        else:
            frontmatter_section = ""
            body = content
        existing_links = extract_wikilinks(body)
        if target_page_id in existing_links:
            continue

        # Save original body for final comparison, then mask code blocks so
        # wikilink injection cannot touch content inside ``` ``` or `...` spans.
        original_body = body
        body, masked_code, mask_prefix = _mask_code_blocks(body)

        # Check if title appears in body (outside code blocks)
        if not pattern.search(body):
            continue

        # Replace first plain-text occurrence in body with wikilink.
        # Use finditer loop so a blocked match (already inside [[ ]]) doesn't
        # silently skip all subsequent occurrences.
        safe_title = wikilink_display_escape(title)
        replacement = f"[[{target_page_id}|{safe_title}]]"

        new_body = body
        for match in pattern.finditer(body):
            start = match.start()

            result = _check_not_in_wikilink(match, body, pid, replacement)
            if result is None:
                # This match is inside a wikilink — continue scanning for next
                continue
            new_body = body[:start] + replacement + body[match.end() :]
            break

        # Restore code blocks before writing (compare against original to avoid
        # spurious writes when the only match was inside a code block)
        new_body = _unmask_code_blocks(new_body, masked_code, mask_prefix)
        if new_body != original_body:
            atomic_text_write(frontmatter_section + new_body, page_path)
            updated.append(pid)
            logger.info("Injected wikilink to %s in %s", target_page_id, pid)

    return updated
