"""Ingest pipeline — read raw sources, create wiki summaries, update indexes."""

import logging
import re
from datetime import date
from pathlib import Path

import frontmatter
import yaml

from kb.config import (
    MAX_CONCEPTS_PER_INGEST,
    MAX_ENTITIES_PER_INGEST,
    PROJECT_ROOT,
    RAW_DIR,
    SMALL_SOURCE_THRESHOLD,
    SOURCE_TYPE_DIRS,
    WIKI_DIR,
    WIKI_INDEX,
    WIKI_SOURCES,
)
from kb.ingest.extractors import extract_from_source
from kb.utils.hashing import content_hash
from kb.utils.pages import load_all_pages, normalize_sources
from kb.utils.paths import make_source_ref
from kb.utils.text import slugify, yaml_escape
from kb.utils.wiki_log import append_wiki_log

logger = logging.getLogger(__name__)


def _find_affected_pages(page_ids: list[str], wiki_dir: Path | None = None) -> list[str]:
    """Find existing pages affected by newly created/updated pages.

    Checks backlinks (pages that link to the new pages) and shared sources.
    Returns a deduplicated, sorted list of affected page IDs.
    """
    if not page_ids:
        return []

    page_id_set = set(page_ids)
    affected: set[str] = set()
    try:
        from kb.compile.linker import build_backlinks

        backlinks_map = build_backlinks(wiki_dir)
        for pid in page_ids:
            for linker in backlinks_map.get(pid, []):
                if linker not in page_id_set:
                    affected.add(linker)
    except Exception as e:
        logger.debug("Failed to compute backlinks for cascade: %s", e)

    try:
        all_pages = load_all_pages(wiki_dir)
        new_sources: set[str] = set()
        for page in all_pages:
            if page["id"] in page_id_set:
                new_sources.update(page["sources"])

        if new_sources:
            for page in all_pages:
                if page["id"] not in page_id_set and set(page["sources"]) & new_sources:
                    affected.add(page["id"])
    except Exception as e:
        logger.debug("Failed to compute shared sources for cascade: %s", e)

    return sorted(affected)


def _is_duplicate_content(source_hash: str, source_ref: str) -> bool:
    """Check if a source with this content hash was already ingested.

    Compares against the compile manifest to detect duplicate content
    from different file paths. Skips template entries. Only flags as
    duplicate if the other source file still exists on disk.
    """
    try:
        # Lazy import: kb.compile.compiler imports kb.ingest.pipeline (circular)
        from kb.compile.compiler import load_manifest

        manifest = load_manifest()
        for ref, stored_hash in manifest.items():
            if ref.startswith("_template/"):
                continue
            if stored_hash == source_hash and ref != source_ref:
                # Verify the other source still exists (avoid stale manifest entries)
                other_path = PROJECT_ROOT / ref
                if other_path.exists():
                    return True
    except Exception as e:
        logger.debug("Duplicate check skipped: %s", e)
    return False


def detect_source_type(source_path: Path) -> str:
    """Auto-detect source type from the raw/ subdirectory path."""
    rel = source_path.resolve().relative_to(RAW_DIR.resolve())
    first_part = rel.parts[0] if rel.parts else ""
    # Map plural directory names to singular source types
    type_map = {v.name: k for k, v in SOURCE_TYPE_DIRS.items()}
    if first_part in type_map:
        return type_map[first_part]
    raise ValueError(f"Cannot detect source type from path: {source_path}")


def _write_wiki_page(
    path: Path, title: str, page_type: str, source_ref: str, confidence: str, content: str
) -> None:
    """Write a wiki page with proper YAML frontmatter."""
    today = date.today().isoformat()
    safe_title = yaml_escape(title)
    safe_source = yaml_escape(source_ref)
    frontmatter = f'''---
title: "{safe_title}"
source:
  - "{safe_source}"
created: {today}
updated: {today}
type: {page_type}
confidence: {confidence}
---

'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter + content, encoding="utf-8")


def _build_summary_content(extraction: dict, source_type: str) -> str:
    """Build summary page content from extracted data."""
    lines = []
    title = extraction.get("title") or extraction.get("name") or "Untitled"
    lines.append(f"# {title}\n")

    # Author/speaker info
    author = extraction.get("author") or extraction.get("speaker")
    authors = extraction.get("authors")
    if authors and isinstance(authors, list):
        lines.append(f"**Authors:** {', '.join(authors)}\n")
    elif author:
        lines.append(f"**Author:** {author}\n")

    # Core argument / abstract / description
    for field in ("core_argument", "abstract", "description", "problem_solved"):
        val = extraction.get(field)
        if val:
            lines.append(f"\n## Overview\n\n{val}\n")
            break

    # Key claims / key points / key arguments
    claims = (
        extraction.get("key_claims")
        or extraction.get("key_points")
        or extraction.get("key_arguments")
    )
    if claims and isinstance(claims, list):
        lines.append("\n## Key Claims\n")
        for claim in claims:
            lines.append(f"- {claim}")
        lines.append("")

    # Entities
    entities = extraction.get("entities_mentioned")
    if entities and isinstance(entities, list):
        lines.append("\n## Entities Mentioned\n")
        for e in entities:
            slug = slugify(e)
            lines.append(f"- [[entities/{slug}|{e}]]")
        lines.append("")

    # Concepts
    concepts = extraction.get("concepts_mentioned")
    if concepts and isinstance(concepts, list):
        lines.append("\n## Concepts\n")
        for c in concepts:
            slug = slugify(c)
            lines.append(f"- [[concepts/{slug}|{c}]]")
        lines.append("")

    return "\n".join(lines)


def _build_item_content(name: str, source_ref: str, context: str, verb: str) -> str:
    """Build entity or concept page content."""
    lines = [
        f"# {name}\n",
        "## References\n",
        f"- {verb} in {source_ref}",
    ]
    if context:
        lines.insert(1, f"{context}\n")
    return "\n".join(lines)


def _extract_entity_context(name: str, extraction: dict) -> str:
    """Build context snippet for an entity from extraction data.

    Searches key_claims, core_argument, and abstract for mentions of the entity.
    Returns a brief description or empty string if nothing relevant found.
    """
    name_lower = name.lower()
    relevant = []

    for field in ("core_argument", "abstract", "description", "problem_solved"):
        val = extraction.get(field)
        if val and name_lower in val.lower():
            relevant.append(val)
            break

    for claim in extraction.get("key_claims") or extraction.get("key_points") or []:
        if isinstance(claim, str) and name_lower in claim.lower():
            relevant.append(claim)

    if not relevant:
        return ""

    lines = ["## Context\n"]
    for item in relevant[:3]:
        lines.append(f"- {item}")
    return "\n".join(lines)


def _update_existing_page(
    page_path: Path,
    source_ref: str,
    name: str = "",
    extraction: dict | None = None,
    verb: str = "Mentioned",
) -> None:
    """Add a new source reference to an existing wiki page.

    Updates both the YAML frontmatter source: list and the References section.
    When name and extraction are provided, enriches page with context from the new source.
    """
    content = page_path.read_text(encoding="utf-8")
    # Check frontmatter sources specifically, not full content
    try:
        post = frontmatter.load(str(page_path))
        existing_sources = normalize_sources(post.metadata.get("source"))
        if source_ref in existing_sources:
            return  # Already referenced in frontmatter
    except (OSError, ValueError, AttributeError, yaml.YAMLError) as e:
        logger.warning("Failed to parse frontmatter for %s: %s", page_path, e)

    # 1. Update frontmatter source: list
    safe_ref = yaml_escape(source_ref)
    # Insert new source entry after the last existing source line
    source_line_pattern = re.compile(r'^  - ".*"$', re.MULTILINE)
    matches = list(source_line_pattern.finditer(content))
    if matches:
        last_match = matches[-1]
        content = content[: last_match.end()] + f'\n  - "{safe_ref}"' + content[last_match.end() :]
    elif "source:" in content:
        content = content.replace("source:\n", f'source:\n  - "{safe_ref}"\n', 1)

    # 2. Append to References section
    ref_line = f"- {verb} in {source_ref}"
    if "## References" in content:
        content = content.replace("## References\n", f"## References\n{ref_line}\n", 1)
    else:
        content += f"\n## References\n\n{ref_line}\n"

    # 3. Update the 'updated' date in frontmatter
    today = date.today().isoformat()
    content = re.sub(r"updated: \d{4}-\d{2}-\d{2}", f"updated: {today}", content)

    # 4. Enrich with context from new source (if extraction provided)
    if name and extraction:
        ctx = _extract_entity_context(name, extraction)
        if ctx and ctx not in content:
            # Add context before References section, or at end
            if "## References" in content:
                content = content.replace("## References", f"{ctx}\n\n## References", 1)
            else:
                content += f"\n{ctx}\n"

    page_path.write_text(content, encoding="utf-8")


def _update_sources_mapping(source_ref: str, wiki_pages: list[str]) -> None:
    """Update wiki/_sources.md with the source -> wiki page mapping."""
    pages_str = ", ".join(f"[[{p}]]" for p in wiki_pages)
    entry = f"- `{source_ref}` → {pages_str}\n"
    if WIKI_SOURCES.exists():
        content = WIKI_SOURCES.read_text(encoding="utf-8")
        if source_ref in content:
            return  # Already mapped
        content += entry
        WIKI_SOURCES.write_text(content, encoding="utf-8")


_SECTION_HEADERS = {
    "entity": "## Entities",
    "concept": "## Concepts",
    "comparison": "## Comparisons",
    "summary": "## Summaries",
    "synthesis": "## Synthesis",
}
_SUBDIR_MAP = {
    "entity": "entities",
    "concept": "concepts",
    "comparison": "comparisons",
    "summary": "summaries",
    "synthesis": "synthesis",
}


def _update_index_batch(entries: list[tuple[str, str, str]]) -> None:
    """Update wiki/index.md with multiple new page entries in a single read/write."""
    if not WIKI_INDEX.exists() or not entries:
        return
    content = WIKI_INDEX.read_text(encoding="utf-8")
    changed = False
    for page_type, slug, title in entries:
        section = _SECTION_HEADERS.get(page_type)
        if not section or section not in content:
            continue
        subdir = _SUBDIR_MAP.get(page_type)
        if not subdir or f"{subdir}/{slug}" in content:
            continue
        entry = f"- [[{subdir}/{slug}|{title}]]"
        placeholder = f"{section}\n\n*No pages yet.*"
        if placeholder in content:
            content = content.replace(placeholder, f"{section}\n\n{entry}")
        else:
            content = content.replace(f"{section}\n", f"{section}\n{entry}\n", 1)
        changed = True
    if changed:
        WIKI_INDEX.write_text(content, encoding="utf-8")


def _process_item_batch(
    items_raw: object,
    field_name: str,
    max_count: int,
    page_type: str,
    source_ref: str,
    extraction: dict,
) -> tuple[list[str], list[str], list[str], list[tuple[str, str]], list[str]]:
    """Validate, deduplicate, and create/update wiki pages for a list of names.

    Returns (created, updated, skipped, new_with_titles, valid_items).
    valid_items is the deduplicated list of names that passed all guards
    (empty-name, empty-slug, collision), for both created and updated pages.
    Used by the caller to build index entries.
    """
    verb = "Mentioned" if page_type == "entity" else "Discussed"
    subdir = _SUBDIR_MAP[page_type]
    items: list = []
    if not isinstance(items_raw, list):
        logger.warning("%s is not a list (%s), skipping", field_name, type(items_raw).__name__)
    else:
        items = items_raw
    if len(items) > max_count:
        logger.warning("%s has %d items, truncating to %d", field_name, len(items), max_count)
        items = items[:max_count]

    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []
    new_with_titles: list[tuple[str, str]] = []
    valid_items: list[str] = []
    seen_slugs: dict[str, str] = {}

    for item in items:
        if not item or not item.strip():
            continue
        item_slug = slugify(item)
        if not item_slug:
            logger.warning("Skipping %s with empty slug: %r", page_type, item)
            continue
        if item_slug in seen_slugs:
            prev = seen_slugs[item_slug]
            if prev != item:
                logger.warning("Slug collision: %r and %r both slug to %r", prev, item, item_slug)
                skipped.append(f"{subdir}/{item_slug} (collision: {item!r})")
            continue
        seen_slugs[item_slug] = item
        valid_items.append(item)
        item_path = WIKI_DIR / subdir / f"{item_slug}.md"
        if item_path.exists():
            _update_existing_page(
                item_path, source_ref, name=item, extraction=extraction, verb=verb
            )
            updated.append(f"{subdir}/{item_slug}")
        else:
            ctx = _extract_entity_context(item, extraction)
            content = _build_item_content(item, source_ref, ctx, verb)
            _write_wiki_page(item_path, item, page_type, source_ref, "stated", content)
            created.append(f"{subdir}/{item_slug}")
            new_with_titles.append((f"{subdir}/{item_slug}", item))

    return created, updated, skipped, new_with_titles, valid_items


def ingest_source(
    source_path: Path,
    source_type: str | None = None,
    extraction: dict | None = None,
    *,
    defer_small: bool = False,
) -> dict:
    """Ingest a single raw source into the knowledge base.

    Args:
        source_path: Path to the raw source file.
        source_type: Source type (auto-detected from path if omitted).
        extraction: Pre-extracted data dict. If None, calls LLM to extract.
        defer_small: If True, sources under SMALL_SOURCE_THRESHOLD chars get
            summary-only processing (no entity/concept pages).

    Returns:
        dict with keys:
            source_path, source_type, content_hash, pages_created, pages_updated,
            pages_skipped, affected_pages, wikilinks_injected.
            Also includes ``duplicate: True`` (and omits affected_pages) when the
            source has identical content to an already-ingested file.
    """
    source_path = Path(source_path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Source not found: {source_path}")

    if source_type is None:
        source_type = detect_source_type(source_path)

    # Read source and compute hash
    raw_content = source_path.read_text(encoding="utf-8")
    source_hash = content_hash(source_path)

    # Build source reference early for duplicate check
    source_ref = make_source_ref(source_path)

    # Duplicate detection: check if this content hash was already ingested
    if _is_duplicate_content(source_hash, source_ref):
        logger.warning("Duplicate content detected: %s (hash: %s)", source_ref, source_hash)
        return {
            "source_path": str(source_path),
            "source_type": source_type,
            "content_hash": source_hash,
            "pages_created": [],
            "pages_updated": [],
            "pages_skipped": [],
            "duplicate": True,
        }

    # Extract structured data via LLM (or use pre-extracted)
    if extraction is None:
        extraction = extract_from_source(raw_content, source_type)

    # Track created/updated pages
    pages_created = []
    pages_updated = []
    pages_skipped = []
    # (page_id, title) for newly created pages — used by inject_wikilinks
    new_pages_with_titles: list[tuple[str, str]] = []

    # 1. Create summary page
    title = extraction.get("title") or extraction.get("name") or source_path.stem
    summary_slug = slugify(title)
    summary_path = WIKI_DIR / "summaries" / f"{summary_slug}.md"
    summary_content = _build_summary_content(extraction, source_type)
    _write_wiki_page(summary_path, title, "summary", source_ref, "stated", summary_content)
    pages_created.append(f"summaries/{summary_slug}")
    new_pages_with_titles.append((f"summaries/{summary_slug}", title))

    # Content-length-aware tiering: short sources get summary only when
    # defer_small is enabled (entity/concept pages deferred to avoid stub proliferation).
    is_small_source = defer_small and len(raw_content) < SMALL_SOURCE_THRESHOLD
    if is_small_source:
        logger.info(
            "Small source (%d chars < %d threshold): deferring entity/concept pages",
            len(raw_content),
            SMALL_SOURCE_THRESHOLD,
        )

    # 2. Create or update entity pages (skip for small sources)
    e_created, e_updated, e_skipped, e_new, e_valid = _process_item_batch(
        [] if is_small_source else (extraction.get("entities_mentioned") or []),
        "entities_mentioned",
        MAX_ENTITIES_PER_INGEST,
        "entity",
        source_ref,
        extraction,
    )
    pages_created.extend(e_created)
    pages_updated.extend(e_updated)
    pages_skipped.extend(e_skipped)
    new_pages_with_titles.extend(e_new)

    # 3. Create or update concept pages (skip for small sources)
    c_created, c_updated, c_skipped, c_new, c_valid = _process_item_batch(
        [] if is_small_source else (extraction.get("concepts_mentioned") or []),
        "concepts_mentioned",
        MAX_CONCEPTS_PER_INGEST,
        "concept",
        source_ref,
        extraction,
    )
    pages_created.extend(c_created)
    pages_updated.extend(c_updated)
    pages_skipped.extend(c_skipped)
    new_pages_with_titles.extend(c_new)

    # 4. Update index files (single read/write)
    index_entries: list[tuple[str, str, str]] = [("summary", summary_slug, title)]
    index_entries.extend(("entity", slugify(e), e) for e in e_valid)
    index_entries.extend(("concept", slugify(c), c) for c in c_valid)
    _update_index_batch(index_entries)

    # 5. Update _sources.md mapping
    all_pages = pages_created + pages_updated
    _update_sources_mapping(source_ref, all_pages)

    # 6. Record hash in manifest for duplicate detection
    try:
        # Lazy import: kb.compile.compiler imports kb.ingest.pipeline (circular)
        from kb.compile.compiler import load_manifest, save_manifest

        manifest = load_manifest()
        manifest[source_ref] = source_hash
        save_manifest(manifest)
    except Exception as e:
        logger.debug("Failed to update hash manifest: %s", e)

    # 7. Append to log
    append_wiki_log(
        "ingest",
        f"Ingested {source_ref} → created {len(pages_created)} pages, "
        f"updated {len(pages_updated)} pages",
    )

    # 8. Compute affected pages (cascade update detection)
    affected_pages = _find_affected_pages(pages_created + pages_updated, WIKI_DIR)

    # 9. Retroactive wikilink injection — scan existing pages for mentions of new titles
    wikilinks_injected: list[str] = []
    for pid, ptitle in new_pages_with_titles:
        try:
            from kb.compile.linker import inject_wikilinks

            updated = inject_wikilinks(ptitle, pid, wiki_dir=WIKI_DIR)
            wikilinks_injected.extend(updated)
        except Exception as e:
            logger.debug("inject_wikilinks failed for %s: %s", pid, e)

    result = {
        "source_path": str(source_path),
        "source_type": source_type,
        "content_hash": source_hash,
        "pages_created": pages_created,
        "pages_updated": pages_updated,
        "pages_skipped": pages_skipped,
        "affected_pages": affected_pages,
        "wikilinks_injected": wikilinks_injected,
    }
    if is_small_source:
        result["deferred_entities"] = True
    return result
