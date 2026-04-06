"""Browse & stats MCP tools — search, read, list, stats."""


from kb.config import RAW_DIR, WIKI_DIR
from kb.mcp.app import mcp
from kb.utils.pages import load_all_pages


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
    pages = load_all_pages()
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

    # PageRank insights
    if stats.get("pagerank"):
        lines.append("\n**Highest PageRank:**")
        for node, score in stats["pagerank"][:5]:
            lines.append(f"  - {node} ({score:.4f})")

    # Bridge nodes (betweenness centrality)
    if stats.get("bridge_nodes"):
        lines.append("\n**Bridge concepts (betweenness centrality):**")
        for node, centrality in stats["bridge_nodes"][:5]:
            lines.append(f"  - {node} ({centrality:.4f})")

    return "\n".join(lines)
