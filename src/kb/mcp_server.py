"""MCP server — expose the knowledge base as tools for Claude Code.

Claude Code is the default LLM. No API key needed for any operation.

- kb_query: returns wiki context; Claude Code synthesizes the answer (add use_api=true to
  call the Anthropic API instead).
- kb_ingest: accepts extraction_json from Claude Code to create wiki pages (add use_api=true
  to have the Anthropic API do the extraction instead).
- kb_ingest_content: one-shot — provide raw content + extraction JSON, saves source and
  creates wiki pages in a single call.
"""

import json
import logging
import re
from datetime import date
from pathlib import Path

import frontmatter
from fastmcp import FastMCP

from kb.config import PROJECT_ROOT, RAW_DIR, SOURCE_TYPE_DIRS, WIKI_DIR
from kb.utils.paths import make_source_ref

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "LLM Knowledge Base",
    instructions=(
        "Knowledge base tools for a structured wiki compiled from raw sources. "
        "You (Claude Code) ARE the LLM — no API key needed.\n\n"
        "WORKFLOW:\n"
        "- kb_query: returns wiki context for you to synthesize an answer.\n"
        "- kb_ingest: pass source_path + your extraction_json to create wiki pages. "
        "Omit extraction_json to get the extraction prompt first.\n"
        "- kb_ingest_content: one-shot for content not yet saved to raw/.\n"
        "- kb_compile_scan: find changed sources, then kb_ingest each.\n"
        "- kb_search, kb_read_page, kb_list_pages, kb_list_sources: browse wiki.\n"
        "- kb_lint, kb_evolve, kb_stats: health and gap analysis."
    ),
)


def _rel(path: Path) -> str:
    """Return path relative to project root with forward slashes."""
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


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
                pages.append(
                    {
                        "id": page_id,
                        "title": post.metadata.get("title", page_path.stem),
                        "type": post.metadata.get("type", "unknown"),
                        "confidence": post.metadata.get("confidence", "unknown"),
                        "sources": post.metadata.get("source", []),
                        "created": str(post.metadata.get("created", "")),
                        "updated": str(post.metadata.get("updated", "")),
                        "path": _rel(page_path),
                        "content": post.content,
                    }
                )
            except Exception as e:
                logger.warning("Skipping page %s: %s", page_path, e)
                continue
    return pages


def _apply_extraction(
    source_ref: str,
    source_path: Path,
    source_type: str,
    extraction: dict,
) -> dict:
    """Shared logic: apply an extraction dict to create wiki pages.

    Returns dict with pages_created, pages_updated lists.
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

    pages_created = []
    pages_updated = []

    # 1. Summary page
    title = extraction.get("title") or extraction.get("name") or source_path.stem
    summary_slug = slugify(title)
    summary_path = WIKI_DIR / "summaries" / f"{summary_slug}.md"
    summary_content = _build_summary_content(extraction, source_type)
    _write_wiki_page(summary_path, title, "summary", source_ref, "stated", summary_content)
    pages_created.append(f"summaries/{summary_slug}")

    # 2. Entity pages
    for entity in extraction.get("entities_mentioned") or []:
        if not entity or not entity.strip():
            continue
        entity_slug = slugify(entity)
        entity_path = WIKI_DIR / "entities" / f"{entity_slug}.md"
        if entity_path.exists():
            _update_existing_page(entity_path, source_ref)
            pages_updated.append(f"entities/{entity_slug}")
        else:
            entity_content = _build_entity_content(entity, source_ref, "")
            _write_wiki_page(entity_path, entity, "entity", source_ref, "stated", entity_content)
            pages_created.append(f"entities/{entity_slug}")

    # 3. Concept pages
    for concept in extraction.get("concepts_mentioned") or []:
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
    for entity in extraction.get("entities_mentioned") or []:
        if entity and entity.strip():
            _update_index("entity", slugify(entity), entity)
    for concept in extraction.get("concepts_mentioned") or []:
        if concept and concept.strip():
            _update_index("concept", slugify(concept), concept)

    # 5. Update _sources.md
    all_pages = pages_created + pages_updated
    _update_sources_mapping(source_ref, all_pages)

    # 6. Log
    _append_to_log(
        f"Ingested {source_ref} → "
        f"created {len(pages_created)} pages, updated {len(pages_updated)} pages"
    )

    return {"pages_created": pages_created, "pages_updated": pages_updated}


def _format_ingest_result(rel_path: str, source_type: str, source_hash: str, result: dict) -> str:
    """Format ingest result as readable text."""
    lines = [
        f"Ingested: {rel_path}",
        f"Type: {source_type}",
        f"Hash: {source_hash}",
        f"Pages created ({len(result['pages_created'])}):",
    ]
    for p in result["pages_created"]:
        lines.append(f"  + {p}")
    lines.append(f"Pages updated ({len(result['pages_updated'])}):")
    for p in result["pages_updated"]:
        lines.append(f"  ~ {p}")
    return "\n".join(lines)


# ── Core Tools ───────────────────────────────────────────────────────


@mcp.tool()
def kb_query(question: str, max_results: int = 10, use_api: bool = False) -> str:
    """Query the knowledge base.

    Default (Claude Code mode): returns wiki search results with full page
    content. You (Claude Code) synthesize the answer and cite sources with
    [source: page_id] format.

    With use_api=true: calls the Anthropic API to synthesize the answer
    (requires ANTHROPIC_API_KEY).

    Args:
        question: Natural language question.
        max_results: Maximum pages to search (default 10).
        use_api: If true, call the Anthropic API for synthesis. Default false.
    """
    if use_api:
        from kb.query.citations import format_citations
        from kb.query.engine import query_wiki

        result = query_wiki(question)
        parts = [result["answer"]]
        if result["citations"]:
            parts.append("\n" + format_citations(result["citations"]))
        parts.append(f"\n[Searched {len(result['source_pages'])} pages]")
        return "\n".join(parts)

    # Default: Claude Code mode — return context for synthesis
    from kb.query.engine import search_pages

    results = search_pages(question, max_results=max_results)
    if not results:
        return (
            "No relevant wiki pages found for this question. "
            "The knowledge base may not have content on this topic yet."
        )

    # Merge trust scores from feedback (fail-safe)
    try:
        from kb.feedback.reliability import compute_trust_scores

        scores = compute_trust_scores()
        for r in results:
            trust_data = scores.get(r["id"], {})
            r["trust"] = trust_data.get("trust", 0.5)
    except Exception:
        for r in results:
            r["trust"] = 0.5

    lines = [
        f"# Query Context for: {question}\n",
        f"Found {len(results)} relevant page(s). "
        "Synthesize an answer using this context. "
        "Cite sources with [source: page_id] format.\n",
    ]
    for r in results:
        trust_label = f", trust: {r['trust']:.2f}" if r.get("trust", 0.5) != 0.5 else ""
        lines.append(
            f"--- Page: {r['id']} (type: {r['type']}, "
            f"confidence: {r['confidence']}, score: {r['score']}{trust_label}) ---\n"
            f"Title: {r['title']}\n\n{r['content']}\n"
        )
    return "\n".join(lines)


@mcp.tool()
def kb_ingest(
    source_path: str,
    source_type: str = "",
    extraction_json: str = "",
    use_api: bool = False,
) -> str:
    """Ingest a raw source file into the knowledge base.

    Default (Claude Code mode):
    - With extraction_json: creates wiki pages immediately using your extraction.
    - Without extraction_json: returns the extraction prompt. Read it, extract
      the JSON, then call kb_ingest again with extraction_json.

    With use_api=true: calls the Anthropic API for extraction (requires
    ANTHROPIC_API_KEY). Ignores extraction_json.

    Args:
        source_path: Path to source file (absolute or relative to project root).
        source_type: One of: article, paper, repo, video, podcast, book, dataset,
                     conversation. Auto-detected from path if empty.
        extraction_json: JSON string with extracted fields. Required keys:
            title (str), entities_mentioned (list[str]), concepts_mentioned (list[str]).
            Optional: author, core_argument, key_claims, abstract, evidence.
            Omit to get the extraction prompt instead.
        use_api: If true, use the Anthropic API for extraction. Default false.
    """
    from kb.utils.hashing import content_hash

    path = Path(source_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()

    if not path.exists():
        return f"Error: Source file not found: {path}"

    # ── API mode ──
    if use_api:
        from kb.ingest.pipeline import ingest_source

        result = ingest_source(path, source_type or None)
        return _format_ingest_result(
            _rel(Path(result["source_path"])),
            result["source_type"],
            result["content_hash"],
            result,
        )

    # ── Detect source type ──
    if not source_type:
        from kb.ingest.pipeline import detect_source_type

        try:
            source_type = detect_source_type(path)
        except ValueError as e:
            return f"Error: {e}. Please specify source_type."

    # ── Claude Code mode: with extraction → apply ──
    if extraction_json:
        try:
            extraction = json.loads(extraction_json)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON — {e}"

        # Validate required extraction fields
        if not isinstance(extraction, dict):
            return "Error: extraction_json must be a JSON object."
        if not extraction.get("title") and not extraction.get("name"):
            return (
                "Error: extraction_json must contain 'title' (or 'name'). "
                "Required keys: title, entities_mentioned, concepts_mentioned."
            )

        source_hash = content_hash(path)
        source_ref = make_source_ref(path)

        result = _apply_extraction(source_ref, path, source_type, extraction)
        return _format_ingest_result(_rel(path), source_type, source_hash, result)

    # ── Claude Code mode: without extraction → return prompt ──
    from kb.ingest.extractors import build_extraction_prompt, load_template

    try:
        template = load_template(source_type)
    except FileNotFoundError as e:
        return f"Error: {e}"

    content = path.read_text(encoding="utf-8")
    prompt = build_extraction_prompt(content, template)

    return (
        f"# Extraction needed for: {_rel(path)}\n\n"
        f"**Type:** {source_type}\n"
        f"**Template:** {template['name']} — {template['description']}\n\n"
        f"Read the source below, extract the JSON, then call kb_ingest again with:\n"
        f'  source_path="{_rel(path)}"\n'
        f'  source_type="{source_type}"\n'
        f"  extraction_json=<your JSON>\n\n"
        f"---\n\n{prompt}"
    )


@mcp.tool()
def kb_ingest_content(
    content: str,
    filename: str,
    source_type: str,
    extraction_json: str,
    url: str = "",
) -> str:
    """One-shot ingest: save raw content + create wiki pages in a single call.

    Use this when you have content that isn't saved to raw/ yet (fetched URL,
    pasted text, etc.). Saves the source and creates all wiki pages.

    Args:
        content: The full raw source text.
        filename: Filename slug (e.g., 'karpathy-llm-knowledge-bases').
        source_type: One of: article, paper, repo, video, podcast, book, dataset,
                     conversation.
        extraction_json: JSON string with extracted fields. Required keys:
            title (str), entities_mentioned (list[str]), concepts_mentioned (list[str]).
        url: Optional source URL for metadata.
    """
    from kb.utils.hashing import content_hash

    slug = _slugify(filename) or "untitled"
    type_dir = SOURCE_TYPE_DIRS.get(source_type)
    if not type_dir:
        return (
            f"Error: Unknown source_type '{source_type}'. Use one of: {', '.join(SOURCE_TYPE_DIRS)}"
        )

    type_dir.mkdir(parents=True, exist_ok=True)
    file_path = type_dir / f"{slug}.md"

    save_content = content
    if url:
        header = f"---\nurl: {url}\nfetched: {date.today().isoformat()}\n---\n\n"
        save_content = header + content

    file_path.write_text(save_content, encoding="utf-8")

    try:
        extraction = json.loads(extraction_json)
    except json.JSONDecodeError as e:
        return f"Error: Invalid extraction JSON — {e}"

    if not isinstance(extraction, dict):
        return "Error: extraction_json must be a JSON object."
    if not extraction.get("title") and not extraction.get("name"):
        return (
            "Error: extraction_json must contain 'title' (or 'name'). "
            "Required keys: title, entities_mentioned, concepts_mentioned."
        )

    source_ref = _rel(file_path)
    result = _apply_extraction(source_ref, file_path, source_type, extraction)
    source_hash = content_hash(file_path)

    return f"Saved source: {source_ref} ({len(save_content)} chars)\n" + _format_ingest_result(
        source_ref, source_type, source_hash, result
    )


@mcp.tool()
def kb_save_source(
    content: str,
    filename: str,
    source_type: str = "article",
    url: str = "",
) -> str:
    """Save content to raw/ as a source file without ingesting.

    Use when you want to save content now and ingest later.

    Args:
        content: The full text content to save.
        filename: Filename without extension (e.g., 'karpathy-llm-knowledge-bases').
        source_type: Determines which raw/ subdirectory. Default 'article'.
        url: Optional source URL to include as metadata.
    """
    slug = _slugify(filename) or "untitled"
    type_dir = SOURCE_TYPE_DIRS.get(source_type)
    if not type_dir:
        return (
            f"Error: Unknown source_type '{source_type}'. Use one of: {', '.join(SOURCE_TYPE_DIRS)}"
        )

    type_dir.mkdir(parents=True, exist_ok=True)
    file_path = type_dir / f"{slug}.md"

    if url:
        header = f"---\nurl: {url}\nfetched: {date.today().isoformat()}\n---\n\n"
        content = header + content

    file_path.write_text(content, encoding="utf-8")
    return (
        f"Saved: {_rel(file_path)} ({len(content)} chars)\n"
        f'To ingest: kb_ingest("{_rel(file_path)}", "{source_type}")'
    )


@mcp.tool()
def kb_compile_scan(incremental: bool = True) -> str:
    """Scan for new/changed raw sources that need ingestion.

    Returns source files to process. For each, call kb_ingest with extraction_json.

    Args:
        incremental: If True (default), only new/changed sources. If False, all.
    """
    from kb.compile.compiler import find_changed_sources, scan_raw_sources

    if incremental:
        new_sources, changed_sources = find_changed_sources()
        if not new_sources and not changed_sources:
            return "No new or changed sources found. Wiki is up to date."

        lines = ["# Compile Scan (incremental)\n"]
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
            "For each: call kb_ingest(source_path) to get the extraction prompt, "
            "then call kb_ingest(source_path, extraction_json=...) with your extraction."
        )
    else:
        all_sources = scan_raw_sources()
        if not all_sources:
            return "No source files found in raw/."
        lines = [
            "# Compile Scan (full)\n",
            f"**Total: {len(all_sources)} source(s)**\n",
        ]
        for s in all_sources:
            lines.append(f"- {_rel(s)}")
        lines.append(
            "\nFor each: call kb_ingest(source_path) to get the extraction prompt, "
            "then call kb_ingest(source_path, extraction_json=...) with your extraction."
        )

    return "\n".join(lines)


# ── Browse & Health Tools ────────────────────────────────────────────


@mcp.tool()
def kb_search(query: str, max_results: int = 10) -> str:
    """Search wiki pages by keyword. Returns matching pages ranked by relevance.

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

    Args:
        page_id: Page identifier like 'concepts/rag' or 'summaries/my-article'.
    """
    page_path = WIKI_DIR / f"{page_id}.md"
    if not page_path.exists():
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
        page_type: Filter: 'entities', 'concepts', 'comparisons', 'summaries',
                   'synthesis'. Empty returns all.
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

    lines.append(
        f"\n**Graph:** {stats['nodes']} nodes, {stats['edges']} edges, "
        f"{stats['components']} component(s)"
    )

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
    result = format_report(report)

    # Append feedback-flagged pages (fail-safe)
    try:
        from kb.feedback.reliability import get_flagged_pages

        flagged = get_flagged_pages()
        if flagged:
            result += (
                "\n## Low-Trust Pages (from query feedback)\n\n"
                f"{len(flagged)} page(s) with trust score below threshold:\n"
            )
            for p in flagged:
                result += f'- {p} — run `kb_lint_deep("{p}")` for fidelity check\n'
    except Exception as e:
        logger.debug("Failed to load feedback data for lint: %s", e)

    return result


@mcp.tool()
def kb_evolve() -> str:
    """Analyze knowledge gaps and suggest new connections, pages, and sources."""
    from kb.evolve.analyzer import format_evolution_report, generate_evolution_report

    report = generate_evolution_report()
    result = format_evolution_report(report)

    # Append coverage gaps from query feedback (fail-safe)
    try:
        from kb.feedback.reliability import get_coverage_gaps

        gaps = get_coverage_gaps()
        if gaps:
            result += (
                "\n## Coverage Gaps (from query feedback)\n\n"
                f"{len(gaps)} query/queries returned incomplete answers:\n"
            )
            for g in gaps:
                notes = f" — {g['notes']}" if g["notes"] else ""
                result += f'- "{g["question"]}"{notes}\n'
    except Exception as e:
        logger.debug("Failed to load feedback data for evolve: %s", e)

    return result


# ── Phase 2: Quality Tools ──────────────────────────────────────────


@mcp.tool()
def kb_review_page(page_id: str) -> str:
    """Review a wiki page — returns page content, raw sources, and review checklist.

    The tool returns raw context (text). You (Claude Code) or a wiki-reviewer
    sub-agent evaluate the context and produce a structured JSON review.

    Args:
        page_id: Page to review (e.g., 'concepts/rag').
    """
    try:
        from kb.review.context import build_review_context

        return build_review_context(page_id)
    except Exception as e:
        return f"Error reviewing {page_id}: {e}"


@mcp.tool()
def kb_refine_page(page_id: str, updated_content: str, revision_notes: str = "") -> str:
    """Update a wiki page's content while preserving frontmatter.

    Used after review or self-critique to apply improvements.
    Logs to wiki/log.md and .data/review_history.json.

    Args:
        page_id: Page to update (e.g., 'concepts/rag').
        updated_content: New markdown body (frontmatter preserved automatically).
        revision_notes: What changed and why.
    """
    from kb.review.refiner import refine_page

    result = refine_page(page_id, updated_content, revision_notes)
    if "error" in result:
        return f"Error: {result['error']}"

    # Include affected pages in response (fail-safe)
    try:
        from kb.compile.linker import build_backlinks

        backlinks = build_backlinks()
        affected = backlinks.get(page_id, [])
    except Exception:
        affected = []

    lines = [
        f"Refined: {page_id}",
        f"Notes: {revision_notes}",
    ]
    if affected:
        lines.append(f"Affected pages ({len(affected)} — may need review):")
        for p in affected:
            lines.append(f"  - {p}")
    return "\n".join(lines)


@mcp.tool()
def kb_lint_deep(page_id: str) -> str:
    """Deep lint a single page — returns page + raw sources side-by-side
    for source fidelity evaluation.

    You (Claude Code) evaluate whether each claim traces to the source.

    Args:
        page_id: Page to check (e.g., 'concepts/rag').
    """
    try:
        from kb.lint.semantic import build_fidelity_context

        return build_fidelity_context(page_id)
    except Exception as e:
        return f"Error checking fidelity for {page_id}: {e}"


@mcp.tool()
def kb_lint_consistency(page_ids: str = "") -> str:
    """Cross-page consistency check — returns related pages grouped for
    contradiction detection.

    Pass comma-separated page IDs, or leave empty to auto-select
    pages most likely to conflict (shared sources, wikilink neighbors).

    Args:
        page_ids: Comma-separated page IDs (e.g., 'concepts/rag,concepts/llm').
                  Empty = auto-select groups.
    """
    from kb.lint.semantic import build_consistency_context

    ids = [p.strip() for p in page_ids.split(",") if p.strip()] if page_ids else None
    return build_consistency_context(ids)


@mcp.tool()
def kb_query_feedback(question: str, rating: str, cited_pages: str = "", notes: str = "") -> str:
    """Record feedback on a query answer to improve wiki reliability.

    Args:
        question: The question that was asked.
        rating: 'useful', 'wrong', or 'incomplete'.
        cited_pages: Comma-separated page IDs cited in the answer.
        notes: What was wrong or missing.
    """
    from kb.feedback.store import add_feedback_entry

    pages = [p.strip() for p in cited_pages.split(",") if p.strip()]
    try:
        add_feedback_entry(question, rating, pages, notes)
    except ValueError as e:
        return f"Error: {e}"

    action = {
        "useful": "Trust scores boosted for cited pages.",
        "wrong": "Cited pages flagged for priority re-lint.",
        "incomplete": "Coverage gap logged for kb_evolve.",
    }
    return f"Feedback recorded: {rating}\n{action.get(rating, '')}"


@mcp.tool()
def kb_reliability_map() -> str:
    """Show page trust scores based on query feedback history.

    Pages cited in successful queries score higher.
    Pages cited in wrong answers score lower and are flagged for re-lint.
    """
    from kb.feedback.reliability import compute_trust_scores, get_flagged_pages

    scores = compute_trust_scores()
    if not scores:
        return "No feedback recorded yet. Use kb_query_feedback after queries."

    sorted_pages = sorted(scores.items(), key=lambda x: x[1].get("trust", 0.5), reverse=True)
    flagged = set(get_flagged_pages())

    lines = ["# Page Reliability Map\n"]
    for pid, s in sorted_pages:
        flag = " **[FLAGGED]**" if pid in flagged else ""
        lines.append(
            f"- {pid}: trust={s['trust']:.2f} "
            f"(useful={s['useful']}, wrong={s['wrong']}, incomplete={s['incomplete']}){flag}"
        )

    if flagged:
        lines.append(
            f"\n**{len(flagged)} page(s) flagged** (trust < 0.4). Run kb_lint_deep on these."
        )

    return "\n".join(lines)


@mcp.tool()
def kb_affected_pages(page_id: str) -> str:
    """Find pages affected when this page changes.

    Returns pages that link TO this page (backlinks) and pages
    that share the same raw sources. Use after updating a page
    to decide whether related pages need review.

    Args:
        page_id: Page that was changed (e.g., 'concepts/rag').
    """
    import frontmatter as fm

    from kb.compile.linker import build_backlinks
    from kb.graph.builder import scan_wiki_pages

    backlinks_map = build_backlinks()
    back = backlinks_map.get(page_id, [])

    # Find pages sharing same sources
    page_path = WIKI_DIR / f"{page_id}.md"
    shared_source_pages: list[str] = []
    if page_path.exists():
        post = fm.load(str(page_path))
        page_sources = post.metadata.get("source", [])
        if isinstance(page_sources, str):
            page_sources = [page_sources]

        # Scan all pages for matching sources
        for other_path in scan_wiki_pages():
            try:
                other_post = fm.load(str(other_path))
                other_id = (
                    str(other_path.relative_to(WIKI_DIR)).replace("\\", "/").removesuffix(".md")
                )
                if other_id == page_id:
                    continue
                other_sources = other_post.metadata.get("source", [])
                if isinstance(other_sources, str):
                    other_sources = [other_sources]
                if set(page_sources) & set(other_sources):
                    shared_source_pages.append(other_id)
            except Exception as e:
                logger.warning("Skipping page %s in affected scan: %s", other_path, e)
                continue

    all_affected = sorted(set(back + shared_source_pages))

    if not all_affected:
        return f"No pages are affected by changes to {page_id}."

    lines = [
        f"# Pages Affected by Changes to {page_id}\n",
        f"**Total:** {len(all_affected)} page(s)\n",
    ]

    if back:
        lines.append(f"## Backlinks ({len(back)} pages link to this page)")
        for p in back:
            lines.append(f"  - {p}")

    if shared_source_pages:
        lines.append(f"\n## Shared Sources ({len(shared_source_pages)} pages share raw sources)")
        for p in shared_source_pages:
            lines.append(f"  - {p}")

    lines.append("\nReview these pages if the changes affect shared claims or definitions.")

    return "\n".join(lines)


def main():
    """Run the MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
