"""Wiki page loading utilities — shared by query engine and MCP server."""

import logging
from pathlib import Path

import frontmatter
import yaml

from kb.config import WIKI_DIR
from kb.graph.builder import page_id

logger = logging.getLogger(__name__)

WIKI_SUBDIRS = ("entities", "concepts", "comparisons", "summaries", "synthesis")


def normalize_sources(sources: str | list | None) -> list[str]:
    """Normalize frontmatter 'source' field to always be a list of strings."""
    if sources is None:
        return []
    if isinstance(sources, str):
        return [sources]
    return list(sources)


def load_all_pages(wiki_dir: Path | None = None) -> list[dict]:
    """Load all wiki pages with metadata and content.

    Returns a list of dicts with keys: id, path, title, type, confidence,
    sources, created, updated, content, raw_content.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    pages = []
    for subdir in WIKI_SUBDIRS:
        subdir_path = wiki_dir / subdir
        if not subdir_path.exists():
            continue
        for page_path in sorted(subdir_path.glob("*.md")):
            try:
                post = frontmatter.load(str(page_path))
                pid = page_id(page_path, wiki_dir)
                sources = normalize_sources(post.metadata.get("source"))
                pages.append(
                    {
                        "id": pid,
                        "path": str(page_path),
                        "title": post.metadata.get("title", page_path.stem),
                        "type": post.metadata.get("type", "unknown"),
                        "confidence": post.metadata.get("confidence", "unknown"),
                        "sources": sources,
                        "created": str(post.metadata.get("created", "")),
                        "updated": str(post.metadata.get("updated", "")),
                        "content": post.content,
                        "raw_content": post.content.lower(),
                    }
                )
            except (
                OSError, ValueError, TypeError, AttributeError,
                yaml.YAMLError, UnicodeDecodeError,
            ) as e:
                logger.warning("Skipping page %s: %s", page_path, e)
                continue
    return pages
