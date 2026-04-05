"""MCP server — expose the knowledge base as tools for Claude Code.

Two modes of operation:

1. **API mode** (requires ANTHROPIC_API_KEY): Use kb_ingest, kb_query, kb_compile — these
   call the Anthropic API directly for extraction and synthesis.

2. **Claude Code native mode** (no API key needed): Use the _prepare/_apply tool pairs —
   these return prompts and context for Claude Code to process, then accept the results
   back to write wiki pages. Claude Code itself acts as the LLM.

   Workflow:
   - kb_ingest_prepare → Claude Code extracts → kb_ingest_apply
   - kb_query_context  → Claude Code synthesizes the answer directly
   - kb_compile_scan   → loop kb_ingest_prepare/apply for each source
"""

import json
from pathlib import Path

import frontmatter
from fastmcp import FastMCP

from kb.config import PROJECT_ROOT, RAW_DIR, WIKI_DIR

mcp = FastMCP(
    "LLM Knowledge Base",
    instructions=(
        "Knowledge base tools for searching, reading, and managing a structured wiki "
        "compiled from raw sources. Use kb_search or kb_list_pages first to discover "
        "content, then kb_read_page to read specific pages.\n\n"
        "TWO MODES for LLM-powered operations:\n"
        "- With API key: kb_query, kb_ingest, kb_compile call the Anthropic API directly.\n"
        "- Without API key (Claude Code native): Use kb_query_context to get search results "
        "and synthesize the answer yourself. Use kb_ingest_prepare to get the extraction "
        "prompt, do the extraction yourself, then kb_ingest_apply to save results. Use "
        "kb_compile_scan to find changed sources, then ingest each with prepare/apply."
    ),
)


def _rel(path: Path) -> str:
    """Return path relative to project root with forward slashes."""
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _load_all_pages() -> list[dict]:
    """Load all wiki pages with metadata."""
    pages = []
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        subdir_path = WIKI_DIR / subdir
        if not subdir_path.exists():
            continue
        for page_path in sorted(subdir_path.glob("*.md")):
            try:
                post = frontmatter.load(str(page_path))
                page_id = (
                    str(page_path.relative_to(WIKI_DIR)).replace("\\", "/").removesuffix(".md")
                )
                pages.append({
                    "id": page_id,
                    "title": post.metadata.get("title", page_path.stem),
                    "type": post.metadata.get("type", "unknown"),
                    "confidence": post.metadata.get("confidence", "unknown"),
                    "sources": post.metadata.get("source", []),
                    "created": str(post.metadata.get("created", "")),
                    "updated": str(post.metadata.get("updated", "")),
                    "path": _rel(page_path),
                    "content": post.content,
                })
            except Exception:
                continue
    return pages


@mcp.tool()
def kb_search(query: str, max_results: int = 10) -> str:
    """Search wiki pages by keyword. Returns matching pages ranked by relevance.

    Use this as the primary way to find information in the knowledge base.
    Results include page ID, title, type, and a content snippet.

    Args:
        query: Search terms (space-separated keywords).
        max_results: Maximum results to return (default 10).
    """
    from kb.query.engine import search_pages

    results = search_pages(query, max_results=max_results)
    if not results:
        return "No matching pages found."

    lines = [f"Found {len(results)} matching page(s):\n"]
    for r in results:
        snippet = r["content"][:200].replace("\n", " ").strip()
        lines.append(
            f"- **{r['id']}** (type: {r['type']}, score: {r['score']})\n"
            f"  Title: {r['title']}\n"
            f"  Snippet: {snippet}..."
        )
    return "\n".join(lines)


@mcp.tool()
def kb_read_page(page_id: str) -> str:
    """Read a wiki page by its ID (e.g., 'concepts/rag', 'entities/openai').

    Returns the full page content including YAML frontmatter.

    Args:
        page_id: Page identifier like 'concepts/rag' or 'summaries/my-article'.
    """
    page_path = WIKI_DIR / f"{page_id}.md"
    if not page_path.exists():
        # Try case-insensitive match
        parts = page_id.split("/", 1)
        if len(parts) == 2:
            subdir = WIKI_DIR / parts[0]
            if subdir.exists():
                for f in subdir.glob("*.md"):
                    if f.stem.lower() == parts[1].lower():
                        page_path = f
                        break
    if not page_path.exists():
        return f"Page not found: {page_id}"
    return page_path.read_text(encoding="utf-8")


@mcp.tool()
def kb_list_pages(page_type: str = "") -> str:
    """List all wiki pages, optionally filtered by type.

    Args:
        page_type: Filter by type: 'entities', 'concepts', 'comparisons',
                   'summaries', 'synthesis'. Empty string returns all.
    """
    pages = _load_all_pages()
    if page_type:
        pages = [p for p in pages if p["id"].startswith(page_type)]

    if not pages:
        return "No pages found."

    lines = [f"Total: {len(pages)} page(s)\n"]
    current_type = ""
    for p in pages:
        ptype = p["id"].split("/")[0]
        if ptype != current_type:
            current_type = ptype
            lines.append(f"\n## {current_type}")
        lines.append(f"- {p['id']} — {p['title']} ({p['type']}, {p['confidence']})")
    return "\n".join(lines)


@mcp.tool()
def kb_query(question: str) -> str:
    """Ask a question and get an LLM-synthesized answer with citations.

    This calls the LLM API (costs tokens). For simple lookups, prefer
    kb_search + kb_read_page instead.

    Args:
        question: Natural language question about the knowledge base content.
    """
    from kb.query.citations import format_citations
    from kb.query.engine import query_wiki

    result = query_wiki(question)
    parts = [result["answer"]]
    if result["citations"]:
        parts.append("\n" + format_citations(result["citations"]))
    parts.append(f"\n[Searched {len(result['source_pages'])} pages]")
    return "\n".join(parts)


@mcp.tool()
def kb_stats() -> str:
    """Get wiki statistics: page counts by type, graph metrics, coverage info."""
    from kb.evolve.analyzer import analyze_coverage
    from kb.graph.builder import build_graph, graph_stats

    coverage = analyze_coverage()
    graph = build_graph()
    stats = graph_stats(graph)

    lines = [
        "# Wiki Statistics\n",
        f"**Total pages:** {coverage['total_pages']}",
    ]
    for ptype, count in coverage["by_type"].items():
        lines.append(f"  - {ptype}: {count}")

    lines.append(f"\n**Graph:** {stats['nodes']} nodes, {stats['edges']} edges, "
                 f"{stats['components']} component(s)")

    if coverage["under_covered_types"]:
        lines.append(f"\n**Missing types:** {', '.join(coverage['under_covered_types'])}")
    if coverage["orphan_concepts"]:
        lines.append(f"\n**Orphan concepts:** {', '.join(coverage['orphan_concepts'])}")
    if stats["most_linked"]:
        top = stats["most_linked"][:5]
        lines.append("\n**Most linked pages:**")
        for node, degree in top:
            lines.append(f"  - {node} ({degree} inbound links)")

    return "\n".join(lines)


@mcp.tool()
def kb_lint() -> str:
    """Run health checks on the wiki. Reports dead links, orphans, staleness, etc."""
    from kb.lint.runner import format_report, run_all_checks

    report = run_all_checks()
    return format_report(report)


@mcp.tool()
def kb_evolve() -> str:
    """Analyze knowledge gaps and suggest new connections, pages, and sources."""
    from kb.evolve.analyzer import format_evolution_report, generate_evolution_report

    report = generate_evolution_report()
    return format_evolution_report(report)


@mcp.tool()
def kb_ingest(source_path: str, source_type: str = "") -> str:
    """Ingest a raw source file into the knowledge base.

    Creates summary, entity, and concept pages from the source.

    Args:
        source_path: Path to the source file (absolute or relative to project root).
        source_type: One of: article, paper, repo, video, podcast, book, dataset,
                     conversation. Auto-detected from path if empty.
    """
    from kb.ingest.pipeline import ingest_source

    path = Path(source_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()

    result = ingest_source(path, source_type or None)
    lines = [
        f"Ingested: {_rel(Path(result['source_path']))}",
        f"Type: {result['source_type']}",
        f"Hash: {result['content_hash']}",
        f"Pages created ({len(result['pages_created'])}):",
    ]
    for p in result["pages_created"]:
        lines.append(f"  + {p}")
    lines.append(f"Pages updated ({len(result['pages_updated'])}):")
    for p in result["pages_updated"]:
        lines.append(f"  ~ {p}")
    return "\n".join(lines)


@mcp.tool()
def kb_list_sources() -> str:
    """List all raw source files in the knowledge base."""
    if not RAW_DIR.exists():
        return "No raw directory found."

    lines = ["# Raw Sources\n"]
    total = 0
    for subdir in sorted(RAW_DIR.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith("."):
            continue
        files = sorted(subdir.glob("*"))
        files = [f for f in files if f.is_file()]
        if files:
            lines.append(f"\n## {subdir.name}/ ({len(files)} files)")
            for f in files:
                size_kb = f.stat().st_size / 1024
                lines.append(f"  - {f.name} ({size_kb:.1f} KB)")
            total += len(files)

    lines.insert(1, f"**Total:** {total} source file(s)")
    return "\n".join(lines)


# ── Claude Code Native Mode (no API key needed) ─────────────────────


@mcp.tool()
def kb_query_context(question: str, max_results: int = 10) -> str:
    """Search the wiki and return full page context for a question — NO API key needed.

    Instead of calling the Anthropic API to synthesize an answer, this returns
    the matched wiki pages with their full content. Claude Code can then
    synthesize the answer directly.

    Use this instead of kb_query when you don't have an ANTHROPIC_API_KEY.

    After receiving the context, answer the question yourself using the wiki
    content. Cite sources using [source: page_id] format.

    Args:
        question: Natural language question.
        max_results: Maximum pages to include in context (default 10).
    """
    from kb.query.engine import search_pages

    results = search_pages(question, max_results=max_results)
    if not results:
        return (
            "No relevant wiki pages found for this question. "
            "The knowledge base may not have content on this topic yet."
        )

    lines = [
        f"# Query Context for: {question}\n",
        f"Found {len(results)} relevant page(s). "
        "Synthesize an answer using this context. "
        "Cite sources with [source: page_id] format.\n",
    ]
    for r in results:
        lines.append(
            f"--- Page: {r['id']} (type: {r['type']}, "
            f"confidence: {r['confidence']}, score: {r['score']}) ---\n"
            f"Title: {r['title']}\n\n{r['content']}\n"
        )
    return "\n".join(lines)


@mcp.tool()
def kb_ingest_prepare(source_path: str, source_type: str = "") -> str:
    """Prepare a raw source for ingestion — NO API key needed.

    Reads the source file, loads the extraction template, and returns the
    extraction prompt. Claude Code should then:
    1. Read the prompt and extract the structured JSON
    2. Call kb_ingest_apply with the extraction JSON to write wiki pages

    Args:
        source_path: Path to the source file (absolute or relative to project root).
        source_type: One of: article, paper, repo, video, podcast, book, dataset,
                     conversation. Auto-detected from path if empty.
    """
    from kb.ingest.extractors import build_extraction_prompt, load_template
    from kb.ingest.pipeline import detect_source_type

    path = Path(source_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()

    if not path.exists():
        return f"Error: Source file not found: {path}"

    content = path.read_text(encoding="utf-8")

    if not source_type:
        try:
            source_type = detect_source_type(path)
        except ValueError as e:
            return f"Error: {e}. Please specify source_type."

    try:
        template = load_template(source_type)
    except FileNotFoundError as e:
        return f"Error: {e}"

    prompt = build_extraction_prompt(content, template)

    return (
        f"# Ingest Preparation\n\n"
        f"**Source:** {_rel(path)}\n"
        f"**Type:** {source_type}\n"
        f"**Template:** {template['name']} — {template['description']}\n\n"
        f"## Extraction Prompt\n\n"
        f"Extract the following as a JSON object and then call `kb_ingest_apply` "
        f"with source_path=\"{_rel(path)}\", source_type=\"{source_type}\", "
        f"and extraction_json set to your JSON result.\n\n"
        f"---\n\n{prompt}"
    )


@mcp.tool()
def kb_ingest_apply(source_path: str, source_type: str, extraction_json: str) -> str:
    """Apply an extraction result to create wiki pages — NO API key needed.

    This is the second step of Claude Code native ingestion. After Claude Code
    has extracted structured data from a source (via kb_ingest_prepare), call
    this with the JSON result to write summary, entity, and concept pages.

    Args:
        source_path: Path to the source file (must match kb_ingest_prepare).
        source_type: Source type (must match kb_ingest_prepare).
        extraction_json: JSON string with extracted fields. Must include at minimum:
            title (str), entities_mentioned (list[str]), concepts_mentioned (list[str]).
            Optional: author, core_argument, key_claims, abstract, etc.
    """
    from kb.ingest.pipeline import (
        _append_to_log,
        _build_concept_content,
        _build_entity_content,
        _build_summary_content,
        _update_existing_page,
        _update_index,
        _update_sources_mapping,
        _write_wiki_page,
        slugify,
    )
    from kb.utils.hashing import content_hash

    path = Path(source_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()

    if not path.exists():
        return f"Error: Source file not found: {path}"

    try:
        extraction = json.loads(extraction_json)
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON — {e}"

    source_hash = content_hash(path)

    # Build source reference
    try:
        source_ref = str(path.relative_to(RAW_DIR.resolve().parent)).replace("\\", "/")
    except ValueError:
        source_ref = f"raw/{path.name}"

    pages_created = []
    pages_updated = []

    # 1. Create summary page
    title = extraction.get("title") or extraction.get("name") or path.stem
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
        entity_path = WIKI_DIR / "entities" / f"{entity_slug}.md"
        if entity_path.exists():
            _update_existing_page(entity_path, source_ref)
            pages_updated.append(f"entities/{entity_slug}")
        else:
            entity_content = _build_entity_content(entity, source_ref, "")
            _write_wiki_page(
                entity_path, entity, "entity", source_ref, "stated", entity_content
            )
            pages_created.append(f"entities/{entity_slug}")

    # 3. Create or update concept pages
    concepts = extraction.get("concepts_mentioned") or []
    for concept in concepts:
        if not concept or not concept.strip():
            continue
        concept_slug = slugify(concept)
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

    # 4. Update indexes
    _update_index("summary", summary_slug, title)
    for entity in entities:
        if entity and entity.strip():
            _update_index("entity", slugify(entity), entity)
    for concept in concepts:
        if concept and concept.strip():
            _update_index("concept", slugify(concept), concept)

    # 5. Update _sources.md
    all_pages = pages_created + pages_updated
    _update_sources_mapping(source_ref, all_pages)

    # 6. Log
    _append_to_log(
        f"Ingested {source_ref} (via Claude Code) → "
        f"created {len(pages_created)} pages, updated {len(pages_updated)} pages"
    )

    lines = [
        f"Ingested: {_rel(path)}",
        f"Type: {source_type}",
        f"Hash: {source_hash}",
        f"Pages created ({len(pages_created)}):",
    ]
    for p in pages_created:
        lines.append(f"  + {p}")
    lines.append(f"Pages updated ({len(pages_updated)}):")
    for p in pages_updated:
        lines.append(f"  ~ {p}")
    return "\n".join(lines)


@mcp.tool()
def kb_compile_scan(incremental: bool = True) -> str:
    """Scan for new/changed raw sources that need ingestion — NO API key needed.

    Returns a list of source files that need processing. For each one,
    use kb_ingest_prepare → extract → kb_ingest_apply.

    Args:
        incremental: If True (default), only return new/changed sources.
                     If False, return all sources.
    """
    from kb.compile.compiler import find_changed_sources, scan_raw_sources

    if incremental:
        new_sources, changed_sources = find_changed_sources()
        lines = ["# Compile Scan (incremental)\n"]
        if not new_sources and not changed_sources:
            return "No new or changed sources found. Wiki is up to date."

        if new_sources:
            lines.append(f"## New sources ({len(new_sources)})\n")
            for s in new_sources:
                lines.append(f"- {_rel(s)}")
        if changed_sources:
            lines.append(f"\n## Changed sources ({len(changed_sources)})\n")
            for s in changed_sources:
                lines.append(f"- {_rel(s)}")

        total = len(new_sources) + len(changed_sources)
        lines.append(
            f"\n**Total: {total} source(s) to process.** "
            "For each source, call kb_ingest_prepare, extract the JSON, "
            "then call kb_ingest_apply."
        )
    else:
        all_sources = scan_raw_sources()
        lines = ["# Compile Scan (full)\n"]
        if not all_sources:
            return "No source files found in raw/."
        lines.append(f"**Total: {len(all_sources)} source(s)**\n")
        for s in all_sources:
            lines.append(f"- {_rel(s)}")
        lines.append(
            "\nFor each source, call kb_ingest_prepare, extract the JSON, "
            "then call kb_ingest_apply."
        )

    return "\n".join(lines)


def main():
    """Run the MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
