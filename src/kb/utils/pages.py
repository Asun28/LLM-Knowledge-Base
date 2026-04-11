"""Wiki page loading utilities — shared by query engine and MCP server."""

import logging
from pathlib import Path

import frontmatter
import yaml

from kb.config import WIKI_DIR, WIKI_SUBDIR_TO_TYPE

logger = logging.getLogger(__name__)

WIKI_SUBDIRS = tuple(WIKI_SUBDIR_TO_TYPE.keys())


def _page_id(page_path: Path, wiki_dir: Path) -> str:
    """Convert a wiki page path to a page ID (e.g., 'concepts/rag')."""
    return str(page_path.relative_to(wiki_dir)).replace("\\", "/").removesuffix(".md").lower()


def normalize_sources(sources: str | list | None) -> list[str]:
    """Normalize frontmatter 'source' field to always be a list of strings."""
    if sources is None:
        return []
    if isinstance(sources, str):
        return [sources] if sources else []
    if not isinstance(sources, list):
        logger.warning("Unexpected source type %r, returning empty list", type(sources).__name__)
        return []
    result = []
    for s in sources:
        if s is None or (isinstance(s, str) and not s):
            continue
        if not isinstance(s, str):
            logger.warning("Non-string source item %r (type %s), converting", s, type(s).__name__)
        result.append(str(s))
    return result


def load_all_pages(wiki_dir: Path | None = None) -> list[dict]:
    """Load all wiki pages with metadata and content.

    Returns a list of dicts with keys: id, path, title, type, confidence,
    sources, created, updated, content, content_lower.
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
                pid = _page_id(page_path, wiki_dir)
                sources = normalize_sources(post.metadata.get("source"))
                pages.append(
                    {
                        "id": pid,
                        "path": str(page_path),
                        "title": str(post.metadata.get("title", page_path.stem)),
                        "type": post.metadata.get("type", "unknown"),
                        "confidence": post.metadata.get("confidence", "unknown"),
                        "sources": sources,
                        "created": str(post.metadata.get("created") or ""),
                        "updated": str(post.metadata.get("updated") or ""),
                        "content": post.content,
                        "content_lower": post.content.lower(),
                    }
                )
            except (
                OSError,
                ValueError,
                TypeError,
                AttributeError,
                yaml.YAMLError,
                UnicodeDecodeError,
            ) as e:
                logger.warning("Skipping page %s: %s", page_path, e)
                continue
    return pages
