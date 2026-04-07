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
    RAW_DIR,
    SOURCE_TYPE_DIRS,
    WIKI_DIR,
    WIKI_INDEX,
    WIKI_SOURCES,
)
from kb.ingest.extractors import extract_from_source
from kb.utils.hashing import content_hash
from kb.utils.pages import normalize_sources
from kb.utils.paths import make_source_ref
from kb.utils.text import slugify, yaml_escape
from kb.utils.wiki_log import append_wiki_log

logger = logging.getLogger(__name__)


def _is_duplicate_content(source_hash: str, source_ref: str) -> bool:
    """Check if a source with this content hash was already ingested.

    Compares against the compile manifest to detect duplicate content
    from different file paths. Skips template entries.
    """
    try:
        from kb.compile.compiler import load_manifest

        manifest = load_manifest()
        for ref, stored_hash in manifest.items():
            if ref.startswith("_template/"):
                continue
            if stored_hash == source_hash and ref != source_ref:
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


def _build_entity_content(entity_name: str, source_ref: str, context: str) -> str:
    """Build entity page content."""
    lines = [
        f"# {entity_name}\n",
        "## References\n",
        f"- Mentioned in {source_ref}",
    ]
    if context:
        lines.insert(1, f"{context}\n")
    return "\n".join(lines)


def _build_concept_content(concept_name: str, source_ref: str, context: str) -> str:
    """Build concept page content."""
    lines = [
        f"# {concept_name}\n",
        "## References\n",
        f"- Discussed in {source_ref}",
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
    page_path: Path, source_ref: str, name: str = "", extraction: dict | None = None
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
    ref_line = f"- Mentioned in {source_ref}"
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


def _update_index(page_type: str, slug: str, title: str) -> None:
    """Update wiki/index.md with a new page entry under the appropriate section."""
    if not WIKI_INDEX.exists():
        return
    content = WIKI_INDEX.read_text(encoding="utf-8")
    section_headers = {
        "entity": "## Entities",
        "concept": "## Concepts",
        "comparison": "## Comparisons",
        "summary": "## Summaries",
        "synthesis": "## Synthesis",
    }
    section = section_headers.get(page_type)
    if not section or section not in content:
        return

    # Use the actual subdirectory name for wikilink
    subdir_map = {
        "entity": "entities",
        "concept": "concepts",
        "comparison": "comparisons",
        "summary": "summaries",
        "synthesis": "synthesis",
    }
    subdir = subdir_map[page_type]
    entry = f"- [[{subdir}/{slug}|{title}]]"

    if f"{subdir}/{slug}" in content:
        return  # Already in index

    # Replace "*No pages yet.*" or append after section header
    placeholder = f"{section}\n\n*No pages yet.*"
    if placeholder in content:
        content = content.replace(placeholder, f"{section}\n\n{entry}")
    else:
        content = content.replace(f"{section}\n", f"{section}\n{entry}\n", 1)

    WIKI_INDEX.write_text(content, encoding="utf-8")


def ingest_source(
    source_path: Path,
    source_type: str | None = None,
    extraction: dict | None = None,
) -> dict:
    """Ingest a single raw source into the knowledge base.

    Args:
        source_path: Path to the raw source file.
        source_type: Source type (auto-detected from path if omitted).
        extraction: Pre-extracted data dict. If None, calls LLM to extract.

    Returns:
        dict with keys: source_path, source_type, content_hash, pages_created, pages_updated
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

    # 1. Create summary page
    title = extraction.get("title") or extraction.get("name") or source_path.stem
    summary_slug = slugify(title)
    summary_path = WIKI_DIR / "summaries" / f"{summary_slug}.md"
    summary_content = _build_summary_content(extraction, source_type)
    _write_wiki_page(summary_path, title, "summary", source_ref, "stated", summary_content)
    pages_created.append(f"summaries/{summary_slug}")

    # 2. Create or update entity pages
    entities = extraction.get("entities_mentioned") or []
    if not isinstance(entities, list):
        logger.warning(
            "entities_mentioned is not a list (%s), skipping entities",
            type(entities).__name__,
        )
        entities = []
    if len(entities) > MAX_ENTITIES_PER_INGEST:
        logger.warning(
            "entities_mentioned has %d items, truncating to %d",
            len(entities),
            MAX_ENTITIES_PER_INGEST,
        )
        entities = entities[:MAX_ENTITIES_PER_INGEST]
    seen_entity_slugs: dict[str, str] = {}
    for entity in entities:
        if not entity or not entity.strip():
            continue
        entity_slug = slugify(entity)
        if not entity_slug:
            logger.warning("Skipping entity with empty slug: %r", entity)
            continue
        if entity_slug in seen_entity_slugs:
            prev = seen_entity_slugs[entity_slug]
            if prev != entity:
                logger.warning(
                    "Slug collision: %r and %r both slug to %r",
                    prev,
                    entity,
                    entity_slug,
                )
                pages_skipped.append(f"entities/{entity_slug} (collision: {entity!r})")
            continue
        seen_entity_slugs[entity_slug] = entity
        entity_path = WIKI_DIR / "entities" / f"{entity_slug}.md"
        if entity_path.exists():
            _update_existing_page(entity_path, source_ref, name=entity, extraction=extraction)
            pages_updated.append(f"entities/{entity_slug}")
        else:
            ctx = _extract_entity_context(entity, extraction)
            entity_content = _build_entity_content(entity, source_ref, ctx)
            _write_wiki_page(entity_path, entity, "entity", source_ref, "stated", entity_content)
            pages_created.append(f"entities/{entity_slug}")

    # 3. Create or update concept pages
    concepts = extraction.get("concepts_mentioned") or []
    if not isinstance(concepts, list):
        logger.warning(
            "concepts_mentioned is not a list (%s), skipping concepts",
            type(concepts).__name__,
        )
        concepts = []
    if len(concepts) > MAX_CONCEPTS_PER_INGEST:
        logger.warning(
            "concepts_mentioned has %d items, truncating to %d",
            len(concepts),
            MAX_CONCEPTS_PER_INGEST,
        )
        concepts = concepts[:MAX_CONCEPTS_PER_INGEST]
    seen_concept_slugs: dict[str, str] = {}
    for concept in concepts:
        if not concept or not concept.strip():
            continue
        concept_slug = slugify(concept)
        if not concept_slug:
            logger.warning("Skipping concept with empty slug: %r", concept)
            continue
        if concept_slug in seen_concept_slugs:
            prev = seen_concept_slugs[concept_slug]
            if prev != concept:
                logger.warning(
                    "Slug collision: %r and %r both slug to %r",
                    prev,
                    concept,
                    concept_slug,
                )
                pages_skipped.append(f"concepts/{concept_slug} (collision: {concept!r})")
            continue
        seen_concept_slugs[concept_slug] = concept
        concept_path = WIKI_DIR / "concepts" / f"{concept_slug}.md"
        if concept_path.exists():
            _update_existing_page(concept_path, source_ref, name=concept, extraction=extraction)
            pages_updated.append(f"concepts/{concept_slug}")
        else:
            ctx = _extract_entity_context(concept, extraction)
            concept_content = _build_concept_content(concept, source_ref, ctx)
            _write_wiki_page(
                concept_path, concept, "concept", source_ref, "stated", concept_content
            )
            pages_created.append(f"concepts/{concept_slug}")

    # 4. Update index files
    _update_index("summary", summary_slug, title)
    for entity in entities:
        if entity and entity.strip():
            _update_index("entity", slugify(entity), entity)
    for concept in concepts:
        if concept and concept.strip():
            _update_index("concept", slugify(concept), concept)

    # 5. Update _sources.md mapping
    all_pages = pages_created + pages_updated
    _update_sources_mapping(source_ref, all_pages)

    # 6. Record hash in manifest for duplicate detection
    try:
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

    return {
        "source_path": str(source_path),
        "source_type": source_type,
        "content_hash": source_hash,
        "pages_created": pages_created,
        "pages_updated": pages_updated,
        "pages_skipped": pages_skipped,
    }
