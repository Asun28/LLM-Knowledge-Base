"""Wikilink resolution, cross-referencing, and backlink management."""

from pathlib import Path

from kb.config import WIKI_DIR
from kb.graph.builder import page_id, scan_wiki_pages
from kb.utils.markdown import extract_wikilinks


def resolve_wikilinks(wiki_dir: Path | None = None) -> dict:
    """Resolve all wikilinks across the wiki and report broken links.

    Returns:
        dict with keys: total_links, resolved, broken (list of {source, target}).
    """
    wiki_dir = wiki_dir or WIKI_DIR
    pages = scan_wiki_pages(wiki_dir)
    existing_ids = {page_id(p, wiki_dir) for p in pages}

    total = 0
    resolved = 0
    broken = []

    for page_path in pages:
        content = page_path.read_text(encoding="utf-8")
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
    backlinks: dict[str, list[str]] = {}

    for page_path in pages:
        content = page_path.read_text(encoding="utf-8")
        links = extract_wikilinks(content)
        source_id = page_id(page_path, wiki_dir)

        for link in links:
            target = link
            if target not in backlinks:
                backlinks[target] = []
            if source_id not in backlinks[target]:
                backlinks[target].append(source_id)

    return backlinks
