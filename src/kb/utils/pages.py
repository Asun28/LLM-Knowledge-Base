"""Wiki page loading utilities — shared by query engine and MCP server."""

import datetime as _dt
import logging
from pathlib import Path

import frontmatter
import yaml

from kb.config import WIKI_DIR, WIKI_PURPOSE, WIKI_SUBDIR_TO_TYPE

logger = logging.getLogger(__name__)

WIKI_SUBDIRS = tuple(WIKI_SUBDIR_TO_TYPE.keys())


def _date_str(value: object) -> str:
    """Convert a date/datetime/str frontmatter value to an ISO-8601 date string."""
    if value is None:
        return ""
    if isinstance(value, _dt.datetime):
        return value.date().isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    return str(value)


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


def load_all_pages(
    wiki_dir: Path | None = None, *, include_content_lower: bool = True
) -> list[dict]:
    """Load all wiki pages with metadata and content.

    Returns a list of dicts with keys: id, path, title, type, confidence,
    sources, created, updated, content, and optionally content_lower.

    Args:
        wiki_dir: Path to wiki directory. Defaults to WIKI_DIR from config.
        include_content_lower: If True (default), includes pre-lowercased content.
            Phase 4.5 HIGH P2: callers that don't need content_lower (kb_list_pages,
            build_graph, lint, export, evolve) can pass False to save ~40MB at 5k pages.
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
                page_dict = {
                    "id": pid,
                    "path": str(page_path),
                    "title": str(post.metadata.get("title", page_path.stem)),
                    "type": post.metadata.get("type", "unknown"),
                    "confidence": post.metadata.get("confidence", "unknown"),
                    "sources": sources,
                    "created": _date_str(post.metadata.get("created")),
                    "updated": _date_str(post.metadata.get("updated")),
                    "content": post.content,
                }
                if include_content_lower:
                    page_dict["content_lower"] = post.content.lower()
                pages.append(page_dict)
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


def load_purpose(wiki_dir: Path | None = None) -> str | None:
    """Load the KB focus document (wiki/purpose.md) if it exists.

    Returns the file content as a string, or None if the file does not exist.
    Used to bias LLM extraction and query synthesis toward the KB's goals.

    Args:
        wiki_dir: Path to wiki directory. Defaults to WIKI_DIR from config.
    """
    purpose_path = (wiki_dir / "purpose.md") if wiki_dir else WIKI_PURPOSE
    if not purpose_path.exists():
        return None
    try:
        return purpose_path.read_text(encoding="utf-8").strip() or None
    except OSError as e:
        logger.warning("Could not read purpose.md: %s", e)
        return None
