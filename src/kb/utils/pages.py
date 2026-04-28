"""Wiki page loading utilities — shared by query engine and MCP server."""

import datetime as _dt
import functools
import logging
from pathlib import Path

import frontmatter
import yaml

from kb.config import WIKI_DIR, WIKI_SUBDIR_TO_TYPE
from kb.utils.io import atomic_text_write

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


def scan_wiki_pages(wiki_dir: Path | None = None) -> list[Path]:
    """Find all markdown files in wiki subdirectories (excluding index files)."""
    wiki_dir = wiki_dir or WIKI_DIR
    pages = []
    for subdir in WIKI_SUBDIRS:
        subdir_path = wiki_dir / subdir
        if subdir_path.exists():
            pages.extend(subdir_path.glob("*.md"))
    return sorted(pages)


def page_id(page_path: Path, wiki_dir: Path | None = None) -> str:
    """Convert a wiki page path to a page ID (e.g., 'concepts/rag').

    Note: The returned ID is lowercased for consistent node naming. The ``path``
    node attribute retains original filesystem case and must be used for all file I/O.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    return page_path.relative_to(wiki_dir).as_posix().removesuffix(".md").lower()


# Cycle 11 AC4 — deprecated alias. ``_page_id`` was the private helper name
# before cycle 11 promoted ``page_id`` to the canonical public export. Kept as a
# bare alias so legacy test imports (``tests/test_v0914_phase395.py``,
# ``tests/test_v0915_task01.py``) keep working without a cycle-12 test-migration
# commit. Scheduled for removal once those tests migrate.
_page_id = page_id  # noqa: N816


@functools.lru_cache(maxsize=8192)
def _load_page_frontmatter_cached(path_str: str, mtime_ns: int) -> tuple:
    post = frontmatter.load(path_str)
    return dict(post.metadata), post.content


def load_page_frontmatter(page_path):
    """Load frontmatter ``(metadata, body)`` with mtime-keyed LRU cache.

    The public wrapper reads ``page_path.stat().st_mtime_ns`` on every call and
    delegates to ``_load_page_frontmatter_cached`` keyed on
    ``(str(page_path), mtime_ns)``. Successful parses are cached
    (``maxsize=8192`` — covers wikis up to ~8k pages with full-run retention
    for the 4 lint/checks call sites; larger wikis see partial eviction).
    Parse/read errors (``OSError``, ``ValueError``, ``AttributeError``,
    ``yaml.YAMLError``, ``UnicodeDecodeError``) are re-raised to preserve each
    existing caller's ``try/except`` contract, and the cache never stores a
    failure (``@lru_cache`` does not cache exceptions natively).

    Caveat — ``mtime_ns`` resolution depends on the filesystem. NTFS resolves
    at ~100 ns. FAT32 is 2-second granularity. OneDrive / SMB mounts can
    coalesce mtime writes. Two edits that land within the filesystem's coarse
    window share a cache key and the second read will see stale frontmatter
    until the next edit bumps mtime_ns. Acceptable for lint/query hot-paths
    because each CLI invocation starts with a fresh cache and mid-run edits
    are rare; tests that mutate frontmatter should call
    ``load_page_frontmatter.cache_clear()`` between mutations.
    """
    mtime_ns = page_path.stat().st_mtime_ns
    return _load_page_frontmatter_cached(str(page_path), mtime_ns)


load_page_frontmatter.cache_clear = _load_page_frontmatter_cached.cache_clear


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
    wiki_dir: Path | None = None,
    *,
    include_content_lower: bool = True,
    return_errors: bool = False,
) -> list[dict] | dict:
    """Load all wiki pages with metadata and content.

    Returns a list of dicts with keys: id, path, title, type, confidence,
    sources, created, updated, content, and optionally content_lower.

    Args:
        wiki_dir: Path to wiki directory. Defaults to WIKI_DIR from config.
        include_content_lower: If True (default), includes pre-lowercased content.
            Phase 4.5 HIGH P2: callers that don't need content_lower (kb_list_pages,
            build_graph, lint, export, evolve) can pass False to save ~40MB at 5k pages.
        return_errors: Cycle 6 AC15. If False (default), returns a plain
            ``list[dict]`` for backward compatibility with every existing
            caller. If True, returns ``{"pages": list[dict], "load_errors": int}``
            so callers can distinguish "0 pages found (fresh install)" from
            "0 pages found (100 permission errors)".
    """
    wiki_dir = wiki_dir or WIKI_DIR
    pages = []
    load_errors = 0
    for subdir in WIKI_SUBDIRS:
        subdir_path = wiki_dir / subdir
        if not subdir_path.exists():
            continue
        for page_path in sorted(subdir_path.glob("*.md")):
            try:
                metadata, body = load_page_frontmatter(page_path)
                pid = _page_id(page_path, wiki_dir)
                sources = normalize_sources(metadata.get("source"))
                page_dict = {
                    "id": pid,
                    "path": str(page_path),
                    "title": str(metadata.get("title", page_path.stem)),
                    "type": metadata.get("type", "unknown"),
                    "confidence": metadata.get("confidence", "unknown"),
                    "sources": sources,
                    "created": _date_str(metadata.get("created")),
                    "updated": _date_str(metadata.get("updated")),
                    "content": body,
                    # Cycle 14 AC23 + AC1 — optional epistemic-integrity
                    # frontmatter fields surfaced as additive keys. Existing
                    # consumers ignore; publish builders and the status
                    # ranking boost read directly. Empty string when absent
                    # so downstream membership checks are safe.
                    "status": str(metadata.get("status", "")),
                    "belief_state": str(metadata.get("belief_state", "")),
                    "authored_by": str(metadata.get("authored_by", "")),
                }
                if include_content_lower:
                    page_dict["content_lower"] = body.lower()
                pages.append(page_dict)
            except (
                OSError,
                ValueError,
                TypeError,
                AttributeError,
                yaml.YAMLError,
                UnicodeDecodeError,
            ) as e:
                load_errors += 1
                logger.warning("Skipping page %s: %s", page_path, e)
                continue
    if return_errors:
        return {"pages": pages, "load_errors": load_errors}
    return pages


@functools.lru_cache(maxsize=4)
def load_purpose(wiki_dir: Path) -> str | None:
    """Load the KB focus document ``<wiki_dir>/purpose.md`` if it exists.

    Cycle 4 item #28 — ``wiki_dir`` is now REQUIRED (previously defaulted to
    the production ``WIKI_DIR`` constant, silently leaking production state
    into tests that forgot to pass the tmp wiki). Every caller in
    ``kb.query.engine`` and ``kb.ingest.extractors`` already passes
    ``wiki_dir`` explicitly; removing the fallback eliminates a whole class
    of test/prod cross-talk bugs.

    Cycle 6 AC14 — cached via ``functools.lru_cache(maxsize=4)`` so the file
    is not re-read on every extraction (previously a 500-source batch compile
    opened ``wiki/purpose.md`` 500 times).

    Tests that mutate ``purpose.md`` after first read must call
    ``load_purpose.cache_clear()`` to see the updated content. Otherwise the
    original-read value persists for the remainder of the process life.

    Args:
        wiki_dir: Path to the wiki directory (required).

    Returns:
        File content as a string, or None if the file does not exist.
    """
    purpose_path = wiki_dir / "purpose.md"
    if not purpose_path.exists():
        return None
    try:
        return purpose_path.read_text(encoding="utf-8").strip() or None
    except OSError as e:
        logger.warning("Could not read purpose.md: %s", e)
        return None


# Cycle 14 AC16 — frontmatter-preserving save wrapper.
#
# Rigid contract: rebuilds `sort_keys=False` on every call and uses
# `atomic_text_write` for crash-safe temp+rename semantics. The cycle-7
# R1 Codex M3 lesson — `frontmatter.dumps` without `sort_keys=False`
# alphabetises metadata keys and regresses the Evidence Trail sentinel
# contract plus downstream YAML-diff workflows.
#
# Single enforcement point: callers that need to write back a `Post`
# object (e.g. kb.lint.augment's three sites) MUST go through this
# wrapper so the `sort_keys=False` knob never drifts.
#
# NOT a cache-invalidating wrapper. `load_page_frontmatter` is LRU-
# cached keyed by `(path, mtime_ns)`. On coarse-mtime filesystems
# (FAT32, SMB, OneDrive), a write-immediately-followed-by-read from
# the cached helper may see stale metadata until the mtime advances.
# Callers that need post-write read consistency should use
# `frontmatter.load(path)` directly.


def save_page_frontmatter(path: Path, post: frontmatter.Post) -> None:
    """Write ``post`` to ``path`` preserving metadata key insertion order.

    Uses ``frontmatter.dumps(post, sort_keys=False)`` so that downstream
    YAML-diff tools and the Evidence Trail sentinel contract survive the
    round-trip. Body content (``post.content``) is preserved with
    interior bytes intact (blank lines, special chars, wikilinks); note
    that ``frontmatter.dumps`` inserts a blank line between the closing
    ``---`` and the body and strips trailing newlines per python-frontmatter
    conventions. Delegates to ``atomic_text_write`` for crash-safe
    temp+rename; produces LF line endings per that helper's contract.

    Args:
        path: Destination file path (existing or new).
        post: ``frontmatter.Post`` instance carrying metadata + content.
    """
    atomic_text_write(frontmatter.dumps(post, sort_keys=False), path)
