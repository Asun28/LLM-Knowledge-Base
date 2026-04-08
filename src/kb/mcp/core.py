"""Core MCP tools — query, ingest, compile."""

import json
import logging
from datetime import date
from pathlib import Path

from kb.config import MAX_SEARCH_RESULTS, PROJECT_ROOT, SOURCE_TYPE_DIRS
from kb.mcp.app import _format_ingest_result, _rel, mcp
from kb.utils.text import slugify, yaml_escape

logger = logging.getLogger(__name__)


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
    max_results = max(1, min(max_results, MAX_SEARCH_RESULTS))

    if use_api:
        from kb.query.citations import format_citations
        from kb.query.engine import query_wiki

        try:
            result = query_wiki(question)
        except Exception as e:
            logger.exception("Error in kb_query API mode for: %s", question)
            return f"Error: Query failed — {e}"
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
    path = Path(source_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()

    # Validate source path stays within project directory
    try:
        path.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return f"Error: Source path must be within the project directory: {source_path}"

    if not path.exists():
        return f"Error: Source file not found: {path}"

    # ── API mode ──
    if use_api:
        try:
            from kb.ingest.pipeline import ingest_source

            result = ingest_source(path, source_type or None)
            return _format_ingest_result(
                _rel(Path(result["source_path"])),
                result["source_type"],
                result["content_hash"],
                result,
            )
        except Exception as e:
            logger.exception("Error ingesting %s (API mode)", source_path)
            return f"Error ingesting source: {e}"

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

        try:
            from kb.ingest.pipeline import ingest_source

            result = ingest_source(path, source_type, extraction=extraction)
            return _format_ingest_result(
                _rel(path), result["source_type"], result["content_hash"], result
            )
        except Exception as e:
            logger.exception("Error ingesting %s", source_path)
            return f"Error ingesting source: {e}"

    # ── Claude Code mode: without extraction → return prompt ──
    from kb.ingest.extractors import build_extraction_prompt, load_template

    try:
        template = load_template(source_type)
    except FileNotFoundError as e:
        return f"Error: {e}"

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return f"Error reading source file: {e}"
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
    slug = slugify(filename) or "untitled"
    type_dir = SOURCE_TYPE_DIRS.get(source_type)
    if not type_dir:
        return (
            f"Error: Unknown source_type '{source_type}'. Use one of: {', '.join(SOURCE_TYPE_DIRS)}"
        )

    type_dir.mkdir(parents=True, exist_ok=True)
    file_path = type_dir / f"{slug}.md"

    # Validate extraction JSON BEFORE writing file to avoid orphaned files
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

    save_content = content
    if url:
        header = f'---\nurl: "{yaml_escape(url)}"\nfetched: {date.today().isoformat()}\n---\n\n'
        save_content = header + content

    file_path.write_text(save_content, encoding="utf-8")

    from kb.ingest.pipeline import ingest_source

    result = ingest_source(file_path, source_type, extraction=extraction)
    source_ref = _rel(file_path)

    return f"Saved source: {source_ref} ({len(save_content)} chars)\n" + _format_ingest_result(
        source_ref, result["source_type"], result["content_hash"], result
    )


@mcp.tool()
def kb_save_source(
    content: str,
    filename: str,
    source_type: str = "article",
    url: str = "",
    overwrite: bool = False,
) -> str:
    """Save content to raw/ as a source file without ingesting.

    Use when you want to save content now and ingest later.

    Args:
        content: The full text content to save.
        filename: Filename without extension (e.g., 'karpathy-llm-knowledge-bases').
        source_type: Determines which raw/ subdirectory. Default 'article'.
        url: Optional source URL to include as metadata.
        overwrite: If true, overwrite existing file. Default false (returns error).
    """
    slug = slugify(filename) or "untitled"
    type_dir = SOURCE_TYPE_DIRS.get(source_type)
    if not type_dir:
        return (
            f"Error: Unknown source_type '{source_type}'. Use one of: {', '.join(SOURCE_TYPE_DIRS)}"
        )

    type_dir.mkdir(parents=True, exist_ok=True)
    file_path = type_dir / f"{slug}.md"

    if file_path.exists() and not overwrite:
        return (
            f"Error: Source file already exists: {_rel(file_path)}. "
            "Use overwrite=true to replace it."
        )

    if url:
        header = f'---\nurl: "{yaml_escape(url)}"\nfetched: {date.today().isoformat()}\n---\n\n'
        content = header + content

    try:
        file_path.write_text(content, encoding="utf-8")
    except OSError as e:
        return f"Error: Failed to write source file: {e}"
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
    try:
        from kb.compile.compiler import find_changed_sources, scan_raw_sources
    except Exception as e:
        return f"Error loading compile module: {e}"

    try:
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
    except Exception as e:
        return f"Error scanning sources: {e}"

    return "\n".join(lines)


@mcp.tool()
def kb_compile(incremental: bool = True) -> str:
    """Compile wiki pages from raw sources.

    In incremental mode, only processes new and changed sources.
    In full mode, recompiles everything.

    Note: Each source requires LLM extraction (ANTHROPIC_API_KEY needed).
    For Claude Code mode, use kb_compile_scan() to get the list, then
    kb_ingest() each source with your own extraction.

    Args:
        incremental: If True (default), only new/changed sources. If False, all.
    """
    try:
        from kb.compile.compiler import compile_wiki

        result = compile_wiki(incremental=incremental)
    except Exception as e:
        logger.exception("Error running compile")
        return f"Error running compile: {e}"

    mode = result["mode"]
    lines = [
        f"# Compile Complete ({mode})\n",
        f"**Sources processed:** {result['sources_processed']}",
        f"**Pages created:** {len(result['pages_created'])}",
        f"**Pages updated:** {len(result['pages_updated'])}",
    ]
    if result["pages_created"]:
        lines.append("\n## Created")
        for p in result["pages_created"]:
            lines.append(f"  + {p}")
    if result["pages_updated"]:
        lines.append("\n## Updated")
        for p in result["pages_updated"]:
            lines.append(f"  ~ {p}")
    if result.get("pages_skipped"):
        lines.append(f"\n## Skipped ({len(result['pages_skipped'])})")
        for p in result["pages_skipped"]:
            lines.append(f"  ! {p}")
    if result.get("wikilinks_injected"):
        lines.append(f"\n## Wikilinks Injected ({len(result['wikilinks_injected'])})")
        for p in result["wikilinks_injected"]:
            lines.append(f"  -> {p}")
    if result.get("duplicates"):
        lines.append(f"\n**Duplicates skipped:** {result['duplicates']}")
    if result["errors"]:
        lines.append(f"\n## Errors ({len(result['errors'])})")
        for err in result["errors"]:
            lines.append(f"  ! {err['source']}: {err['error']}")
    return "\n".join(lines)
