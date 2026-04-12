"""Ingest pipeline — read raw sources, create wiki summaries, update indexes."""

import json
import logging
import os
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
    WIKI_SUBDIR_TO_TYPE,
)
from kb.ingest.contradiction import detect_contradictions
from kb.ingest.evidence import append_evidence_trail
from kb.ingest.extractors import extract_from_source
from kb.utils.hashing import content_hash as compute_hash
from kb.utils.io import atomic_text_write
from kb.utils.pages import load_all_pages, normalize_sources
from kb.utils.paths import make_source_ref
from kb.utils.text import slugify, yaml_escape
from kb.utils.wiki_log import append_wiki_log

logger = logging.getLogger(__name__)

# Fix 2.3 (module-level): compiled once, reused in every _update_existing_page call.
_SOURCE_BLOCK_RE = re.compile(r"^(source:\s*\n(?:  - [^\n]*\n)*)", re.MULTILINE)


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


def detect_source_type(source_path: Path, raw_dir: Path | None = None) -> str:
    """Auto-detect source type from the raw/ subdirectory path."""
    effective_raw = (raw_dir or RAW_DIR).resolve()
    rel = source_path.resolve().relative_to(effective_raw)
    first_part = rel.parts[0] if rel.parts else ""
    if first_part == "assets":
        raise ValueError(
            "raw/assets/ files are not ingestable — assets are referenced by other sources"
        )
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
    fm_text = f'''---
title: "{safe_title}"
source:
  - "{safe_source}"
created: {today}
updated: {today}
type: {page_type}
confidence: {confidence}
---

'''
    atomic_text_write(fm_text + content, path)
    append_evidence_trail(path, source_ref, f"Initial extraction: {page_type} page created")


def _build_summary_content(extraction: dict, source_type: str) -> str:
    """Build summary page content from extracted data."""
    lines = []
    title = extraction.get("title") or extraction.get("name") or "Untitled"
    safe_title = title.replace("\n", " ").replace("\r", "")
    lines.append(f"# {safe_title}\n")

    # Author/speaker info
    author = extraction.get("author") or extraction.get("speaker")
    authors = extraction.get("authors")
    if authors and isinstance(authors, list):
        safe_authors = []
        for a in authors:
            if isinstance(a, str):
                safe_authors.append(a)
            elif isinstance(a, dict) and a.get("name"):
                safe_authors.append(str(a["name"]))
            else:
                logger.warning("Dropping non-string author value: %r", a)
        if safe_authors:
            lines.append(f"**Authors:** {', '.join(safe_authors)}\n")
    elif author:
        lines.append(f"**Author:** {author}\n")

    # Core argument / abstract / description
    for field in ("core_argument", "abstract", "description", "problem_solved"):
        val = extraction.get(field)
        if val:
            lines.append(f"\n## Overview\n\n{val}\n")
            break

    # Key claims / key points / key arguments
    key_claims = extraction.get("key_claims")
    key_points = extraction.get("key_points")
    key_args = extraction.get("key_arguments")
    claims = (
        key_claims if key_claims is not None else key_points if key_points is not None else key_args
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
            # Fix 2.8: skip empty slugs; Fix 2.15: sanitize display name
            if slug:
                safe_name = e.replace("|", "-").replace("\n", " ").replace("\r", "")
                lines.append(f"- [[entities/{slug}|{safe_name}]]")
        lines.append("")

    # Concepts
    concepts = extraction.get("concepts_mentioned")
    if concepts and isinstance(concepts, list):
        lines.append("\n## Concepts\n")
        for c in concepts:
            slug = slugify(c)
            # Fix 2.8: skip empty slugs; Fix 2.15: sanitize display name
            if slug:
                safe_name = c.replace("|", "-").replace("\n", " ").replace("\r", "")
                lines.append(f"- [[concepts/{slug}|{safe_name}]]")
        lines.append("")

    return "\n".join(lines)


def _build_item_content(name: str, source_ref: str, context: str, verb: str) -> str:
    """Build entity or concept page content."""
    safe_name = name.replace("\n", " ").replace("\r", "")
    lines = [
        f"# {safe_name}\n",
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

    key_claims = extraction.get("key_claims")
    key_points = extraction.get("key_points")
    for claim in key_claims if key_claims is not None else key_points or []:
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
    # Fix 2.2: Read file exactly once; parse frontmatter from in-memory content (avoids TOCTOU).
    content = page_path.read_text(encoding="utf-8")
    # Check frontmatter sources specifically, not full content
    try:
        post = frontmatter.loads(content)
        existing_sources = normalize_sources(post.metadata.get("source"))
        if source_ref in existing_sources:
            return  # Already referenced in frontmatter
    except (ValueError, AttributeError, yaml.YAMLError) as e:
        logger.warning("Failed to parse frontmatter for %s: %s", page_path, e)

    # 1. Update frontmatter source: list
    safe_ref = yaml_escape(source_ref)
    # Split on the closing '---' to scope the regex to the frontmatter section only
    fm_match = re.match(r"\A(---\r?\n.*?\r?\n---\r?\n?)(.*)", content, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        body_text = fm_match.group(2)
    else:
        # Fix 2.9: warn when frontmatter regex fails to match
        logger.warning(
            "Could not parse frontmatter block in %s; treating whole file as body", page_path
        )
        fm_text = content
        body_text = ""

    # Fix 2.3: Target only the source: block — not any other YAML list (e.g. tags:)
    source_match = _SOURCE_BLOCK_RE.search(fm_text)
    if source_match:
        block_end = source_match.end()
        fm_text = fm_text[:block_end] + f'  - "{safe_ref}"\n' + fm_text[block_end:]
    elif "source:" in fm_text:
        fm_text = fm_text.replace("source:\n", f'source:\n  - "{safe_ref}"\n', 1)

    # Fix 2.17: Apply updated date substitution only to fm_text, not body
    today = date.today().isoformat()
    fm_text = re.sub(r"updated: \d{4}-\d{2}-\d{2}", f"updated: {today}", fm_text)

    content = fm_text + body_text

    # 2. Append to References section (Fix 2.10: append after last ref, Fix 2.11: scope to body)
    ref_line = f"- {verb} in {source_ref}"
    if "## References" in body_text:
        # Append new reference at end of References block.
        # Use MULTILINE (not DOTALL) so `.` does not cross line boundaries;
        # match non-empty lines or blank lines until a new section or end-of-string.
        body_text = re.sub(
            r"(## References\n(?:[^\n].*\n|\n)*?)(?=\n## |\Z)",
            lambda m: m.group(1) + ref_line + "\n",
            body_text,
            count=1,
            flags=re.MULTILINE,
        )
        content = fm_text + body_text
    elif "## References" not in content:
        content += f"\n## References\n\n{ref_line}\n"

    # 4. Enrich with context from new source (if extraction provided)
    if name and extraction:
        ctx = _extract_entity_context(name, extraction)
        # Fix 2.4: check for section header presence, not full block equality
        if ctx and "## Context" not in content:
            # Add context before References section, or at end.
            # Use regex anchored to line start to avoid matching "## References"
            # inside body text or LLM-extracted context strings.
            ref_match = re.search(r"^## References", content, re.MULTILINE)
            if ref_match:
                insert_pos = ref_match.start()
                content = content[:insert_pos] + f"{ctx}\n\n" + content[insert_pos:]
            else:
                content += f"\n{ctx}\n"

    # Fix 2.1: Use atomic write
    atomic_text_write(content, page_path)
    append_evidence_trail(
        page_path, source_ref, f"{verb} in new source — source reference added"
    )


def _update_sources_mapping(
    source_ref: str, wiki_pages: list[str], wiki_dir: Path | None = None
) -> None:
    """Update wiki/_sources.md with the source -> wiki page mapping."""
    sources_file = (wiki_dir / "_sources.md") if wiki_dir is not None else WIKI_SOURCES
    pages_str = ", ".join(f"[[{p}]]" for p in wiki_pages)
    entry = f"- `{source_ref}` → {pages_str}\n"
    if not sources_file.exists():
        logger.warning("_sources.md not found — skipping source mapping for %s", source_ref)
        return
    content = sources_file.read_text(encoding="utf-8")
    if f"`{source_ref}`" in content:
        return  # Already listed
    content += entry
    atomic_text_write(content, sources_file)


# Fix 2.18: Derive from WIKI_SUBDIR_TO_TYPE at module load time — single source of truth.
_SUBDIR_MAP: dict[str, str] = {v: k for k, v in WIKI_SUBDIR_TO_TYPE.items()}
_SECTION_HEADERS: dict[str, str] = {
    page_type: f"## {subdir.capitalize()}" for subdir, page_type in WIKI_SUBDIR_TO_TYPE.items()
}


def _update_index_batch(entries: list[tuple[str, str, str]], wiki_dir: Path | None = None) -> None:
    """Update wiki/index.md with multiple new page entries in a single read/write."""
    if not entries:
        return
    index_path = (wiki_dir / "index.md") if wiki_dir is not None else WIKI_INDEX
    if not index_path.exists():
        logger.warning("index.md not found — skipping index update for %d entries", len(entries))
        return
    content = index_path.read_text(encoding="utf-8")
    changed = False
    for page_type, slug, title in entries:
        section = _SECTION_HEADERS.get(page_type)
        if not section or section not in content:
            continue
        subdir = _SUBDIR_MAP.get(page_type)
        if not subdir:
            continue
        if f"[[{subdir}/{slug}|" in content or f"[[{subdir}/{slug}]]" in content:
            continue
        safe_title = title.replace("|", "-").replace("\n", " ").replace("\r", "")
        entry = f"- [[{subdir}/{slug}|{safe_title}]]"
        placeholder = f"{section}\n\n*No pages yet.*"
        if placeholder in content:
            content = content.replace(placeholder, f"{section}\n\n{entry}")
        else:
            content = content.replace(f"{section}\n", f"{section}\n{entry}\n", 1)
        changed = True
    if changed:
        atomic_text_write(content, index_path)


def _process_item_batch(
    items_raw: object,
    field_name: str,
    max_count: int,
    page_type: str,
    source_ref: str,
    extraction: dict,
    wiki_dir: Path | None = None,
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

    effective_wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR

    for item in items:
        if not isinstance(item, str):
            logger.warning("Skipping non-string %s in %s: %r", page_type, field_name, item)
            continue
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
        item_path = effective_wiki_dir / subdir / f"{item_slug}.md"
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
    wiki_dir: Path | None = None,
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

    # Verify source_path is within raw/ — use normcase on both sides for
    # reliable case-insensitive comparison on Windows (Python 3.12+).
    raw_dir_nc = Path(os.path.normcase(str(RAW_DIR.resolve())))
    source_path_nc = Path(os.path.normcase(str(source_path)))
    try:
        source_path_nc.relative_to(raw_dir_nc)
    except ValueError:
        raise ValueError(f"Source path must be within raw/ directory: {source_path}")

    if source_type is None:
        source_type = detect_source_type(source_path)

    # Fix 2.13: Read bytes once; derive both text and hash from the same read (avoids double read).
    raw_bytes = source_path.read_bytes()
    try:
        raw_content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(
            f"Binary file cannot be ingested: {source_path.name}. "
            "Convert to markdown first (e.g., markitdown or docling)."
        )
    source_hash = compute_hash(source_path)

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

    effective_wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR

    # Extract structured data via LLM (or use pre-extracted)
    if extraction is None:
        extraction = extract_from_source(raw_content, source_type)

    # Track created/updated pages
    pages_created = []
    pages_updated = []
    pages_skipped = []
    # (page_id, title) for newly created pages — used by inject_wikilinks
    new_pages_with_titles: list[tuple[str, str]] = []

    # 1. Create summary page (preserve created: date on re-ingest)
    title = extraction.get("title") or extraction.get("name") or source_path.stem
    summary_slug = slugify(title)
    if not summary_slug:
        # Fix 2.19: use "untitled" as final fallback if stem also produces empty slug
        summary_slug = slugify(source_path.stem) or "untitled"
        logger.warning(
            "Title %r produced empty slug; falling back to source stem %r",
            title,
            summary_slug,
        )
    summary_path = effective_wiki_dir / "summaries" / f"{summary_slug}.md"
    summary_content = _build_summary_content(extraction, source_type)
    if summary_path.exists():
        _update_existing_page(summary_path, source_ref, verb="Summarized")
        pages_updated.append(f"summaries/{summary_slug}")
        # Do NOT add to new_pages_with_titles — wikilinks for this page already exist
    else:
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
        wiki_dir=effective_wiki_dir,
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
        wiki_dir=effective_wiki_dir,
    )
    pages_created.extend(c_created)
    pages_updated.extend(c_updated)
    pages_skipped.extend(c_skipped)
    new_pages_with_titles.extend(c_new)

    # 4. Update index files (single read/write)
    # Fix 2.7: use page IDs from created pages for slug consistency (avoids re-slugify divergence)
    index_entries: list[tuple[str, str, str]] = [("summary", summary_slug, title)]
    for pid in e_created:
        slug = pid.split("/", 1)[-1] if "/" in pid else pid
        # Find matching name from e_valid by re-slugifying
        name = next((e for e in e_valid if slugify(e) == slug), slug)
        index_entries.append(("entity", slug, name))
    for pid in e_updated:
        slug = pid.split("/", 1)[-1] if "/" in pid else pid
        name = next((e for e in e_valid if slugify(e) == slug), slug)
        index_entries.append(("entity", slug, name))
    for pid in c_created:
        slug = pid.split("/", 1)[-1] if "/" in pid else pid
        name = next((c for c in c_valid if slugify(c) == slug), slug)
        index_entries.append(("concept", slug, name))
    for pid in c_updated:
        slug = pid.split("/", 1)[-1] if "/" in pid else pid
        name = next((c for c in c_valid if slugify(c) == slug), slug)
        index_entries.append(("concept", slug, name))
    _update_index_batch(index_entries, wiki_dir=effective_wiki_dir)

    # 5. Update _sources.md mapping
    all_pages = pages_created + pages_updated
    _update_sources_mapping(source_ref, all_pages, wiki_dir=effective_wiki_dir)

    # 6. Record hash in manifest for duplicate detection
    try:
        # Lazy import: kb.compile.compiler imports kb.ingest.pipeline (circular)
        from kb.compile.compiler import load_manifest, save_manifest

        manifest = load_manifest()
        manifest[source_ref] = source_hash
        save_manifest(manifest)
    except (OSError, json.JSONDecodeError) as e:
        # Fix 2.14: narrow bare except — log at WARNING, not DEBUG
        logger.warning("Failed to update hash manifest: %s", e)
    except Exception as e:
        logger.debug("Failed to update hash manifest (unexpected): %s", e)

    # 7. Append to log
    append_wiki_log(
        "ingest",
        f"Ingested {source_ref} → created {len(pages_created)} pages, "
        f"updated {len(pages_updated)} pages",
    )

    # 8. Compute affected pages (cascade update detection)
    affected_pages = _find_affected_pages(pages_created + pages_updated, effective_wiki_dir)

    # 9. Retroactive wikilink injection — scan existing pages for mentions of new titles
    wikilinks_injected: list[str] = []
    for pid, ptitle in new_pages_with_titles:
        try:
            from kb.compile.linker import inject_wikilinks

            updated = inject_wikilinks(ptitle, pid, wiki_dir=effective_wiki_dir)
            wikilinks_injected.extend(updated)
        except Exception as e:
            logger.debug("inject_wikilinks failed for %s: %s", pid, e)

    # Auto-contradiction detection
    contradiction_warnings: list[dict] = []
    if extraction:
        key_claims = extraction.get("key_claims") or extraction.get("key_points") or []
        if key_claims and isinstance(key_claims, list):
            try:
                existing = load_all_pages(effective_wiki_dir)
                contradiction_warnings = detect_contradictions(
                    [str(c) for c in key_claims if isinstance(c, str)],
                    existing,
                )
                if contradiction_warnings:
                    logger.warning(
                        "Detected %d potential contradiction(s) during ingest of %s",
                        len(contradiction_warnings),
                        source_ref,
                    )
            except Exception as e:
                logger.debug("Contradiction detection failed (non-fatal): %s", e)

    # Fix 2.21: deduplicate wikilinks_injected
    result = {
        "source_path": str(source_path),
        "source_type": source_type,
        "content_hash": source_hash,
        "pages_created": pages_created,
        "pages_updated": pages_updated,
        "pages_skipped": pages_skipped,
        "affected_pages": affected_pages,
        "wikilinks_injected": sorted(set(wikilinks_injected)),
    }
    if is_small_source:
        result["deferred_entities"] = True
    if contradiction_warnings:
        result["contradictions"] = contradiction_warnings
    return result
