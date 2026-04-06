"""Ingest pipeline — read raw sources, create wiki summaries, update indexes."""

import re
from datetime import date
from pathlib import Path

from kb.config import (
    RAW_DIR,
    SOURCE_TYPE_DIRS,
    WIKI_DIR,
    WIKI_INDEX,
    WIKI_LOG,
    WIKI_SOURCES,
)
from kb.ingest.extractors import extract_from_source
from kb.utils.hashing import content_hash
from kb.utils.paths import make_source_ref


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def detect_source_type(source_path: Path) -> str:
    """Auto-detect source type from the raw/ subdirectory path."""
    rel = source_path.resolve().relative_to(RAW_DIR.resolve())
    first_part = rel.parts[0] if rel.parts else ""
    # Map plural directory names to singular source types
    type_map = {v.name: k for k, v in SOURCE_TYPE_DIRS.items()}
    if first_part in type_map:
        return type_map[first_part]
    raise ValueError(f"Cannot detect source type from path: {source_path}")


def _yaml_escape(value: str) -> str:
    """Escape a string for safe YAML quoting (double-quote style)."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _write_wiki_page(
    path: Path, title: str, page_type: str, source_ref: str, confidence: str, content: str
) -> None:
    """Write a wiki page with proper YAML frontmatter."""
    today = date.today().isoformat()
    safe_title = _yaml_escape(title)
    safe_source = _yaml_escape(source_ref)
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


def _update_existing_page(page_path: Path, source_ref: str) -> None:
    """Add a new source reference to an existing wiki page's References section."""
    content = page_path.read_text(encoding="utf-8")
    ref_line = f"- Mentioned in {source_ref}"
    if source_ref in content:
        return  # Already referenced
    # Append to References section
    if "## References" in content:
        content = content.replace("## References\n", f"## References\n{ref_line}\n", 1)
    else:
        content += f"\n## References\n\n{ref_line}\n"

    # Update the 'updated' field in frontmatter
    today = date.today().isoformat()
    content = re.sub(r"updated: \d{4}-\d{2}-\d{2}", f"updated: {today}", content)

    page_path.write_text(content, encoding="utf-8")


def _append_to_log(message: str) -> None:
    """Append an entry to wiki/log.md."""
    today = date.today().isoformat()
    entry = f"- {today} | ingest | {message}\n"
    if WIKI_LOG.exists():
        content = WIKI_LOG.read_text(encoding="utf-8")
        content += entry
        WIKI_LOG.write_text(content, encoding="utf-8")


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


def ingest_source(source_path: Path, source_type: str | None = None) -> dict:
    """Ingest a single raw source into the knowledge base.

    Args:
        source_path: Path to the raw source file.
        source_type: Source type (auto-detected from path if omitted).

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

    # Extract structured data via LLM
    extraction = extract_from_source(raw_content, source_type)

    # Build source reference (canonical relative path)
    source_ref = make_source_ref(source_path)

    # Track created/updated pages
    pages_created = []
    pages_updated = []

    # 1. Create summary page
    title = extraction.get("title") or extraction.get("name") or source_path.stem
    summary_slug = slugify(title)
    summary_path = WIKI_DIR / "summaries" / f"{summary_slug}.md"
    summary_content = _build_summary_content(extraction, source_type)
    _write_wiki_page(summary_path, title, "summary", source_ref, "stated", summary_content)
    pages_created.append(f"summaries/{summary_slug}")

    # 2. Create or update entity pages
    entities = extraction.get("entities_mentioned") or []
    for entity in entities:
        if not entity or not entity.strip():
            continue
        entity_slug = slugify(entity)
        if not entity_slug:
            continue
        entity_path = WIKI_DIR / "entities" / f"{entity_slug}.md"
        if entity_path.exists():
            _update_existing_page(entity_path, source_ref)
            pages_updated.append(f"entities/{entity_slug}")
        else:
            entity_content = _build_entity_content(entity, source_ref, "")
            _write_wiki_page(entity_path, entity, "entity", source_ref, "stated", entity_content)
            pages_created.append(f"entities/{entity_slug}")

    # 3. Create or update concept pages
    concepts = extraction.get("concepts_mentioned") or []
    for concept in concepts:
        if not concept or not concept.strip():
            continue
        concept_slug = slugify(concept)
        if not concept_slug:
            continue
        concept_path = WIKI_DIR / "concepts" / f"{concept_slug}.md"
        if concept_path.exists():
            _update_existing_page(concept_path, source_ref)
            pages_updated.append(f"concepts/{concept_slug}")
        else:
            concept_content = _build_concept_content(concept, source_ref, "")
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

    # 6. Append to log
    _append_to_log(
        f"Ingested {source_ref} → created {len(pages_created)} pages, "
        f"updated {len(pages_updated)} pages"
    )

    return {
        "source_path": str(source_path),
        "source_type": source_type,
        "content_hash": source_hash,
        "pages_created": pages_created,
        "pages_updated": pages_updated,
    }
