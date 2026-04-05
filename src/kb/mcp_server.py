"""MCP server — expose the knowledge base as tools for Claude Code."""

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
        "content, then kb_read_page to read specific pages. Use kb_query for LLM-powered "
        "answers with citations (costs API tokens)."
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


def main():
    """Run the MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
