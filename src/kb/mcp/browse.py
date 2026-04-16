"""Browse & stats MCP tools — search, read, list, stats."""

import logging
import os

from kb.config import (
    MAX_QUESTION_LEN,
    MAX_SEARCH_RESULTS,
    RAW_DIR,
    WIKI_DIR,
    WIKI_SUBDIR_TO_TYPE,
)
from kb.mcp.app import _validate_page_id, mcp
from kb.utils.pages import load_all_pages

logger = logging.getLogger(__name__)

# Maps singular type names to subdir names: "entity" → "entities", etc.
_TYPE_TO_SUBDIR = {v: k for k, v in WIKI_SUBDIR_TO_TYPE.items()}

# G1 (Phase 4.5 MEDIUM): per-subdir entry cap + total-response size cap.
# Prevents accidental or malicious million-file raw/ subdir from OOMing
# the MCP process or blowing the MCP transport buffer.
_LIST_SOURCES_PER_SUBDIR_CAP = 500
_LIST_SOURCES_TOTAL_CAP_BYTES = 64 * 1024


@mcp.tool()
def kb_search(query: str, max_results: int = 10) -> str:
    """Search wiki pages by keyword. Returns matching pages ranked by relevance.

    Args:
        query: Search terms (space-separated keywords).
        max_results: Maximum results to return (default 10).
    """
    if not query or not query.strip():
        return "Error: Query cannot be empty."
    # G2 (Phase 4.5 R4 HIGH): reject over-long queries to avoid DoS from
    # `query="x"*1_000_000` being tokenized + BM25-scored against every page.
    if len(query) > MAX_QUESTION_LEN:
        return f"Error: Query too long ({len(query)} chars; max {MAX_QUESTION_LEN})."

    max_results = max(1, min(max_results, MAX_SEARCH_RESULTS))

    try:
        from kb.query.engine import search_pages

        results = search_pages(query, max_results=max_results)
        if not results:
            return "No matching pages found."
        lines = [f"Found {len(results)} matching page(s):\n"]
        for r in results:
            snippet = r["content"][:200].replace("\n", " ").strip()
            # G2 (Phase 4.5 R4 HIGH): surface staleness alongside score so
            # discoverability matches kb_query's [STALE] treatment.
            stale_marker = " [STALE]" if r.get("stale") else ""
            lines.append(
                f"- **{r['id']}** (type: {r['type']}, score: {r['score']}){stale_marker}\n"
                f"  Title: {r['title']}\n"
                f"  Snippet: {snippet}..."
            )
        return "\n".join(lines)
    except Exception as e:
        logger.exception("Error in kb_search for query: %s", query)
        return f"Error: Search failed — {e}"


@mcp.tool()
def kb_read_page(page_id: str) -> str:
    """Read a wiki page by its ID (e.g., 'concepts/rag', 'entities/openai').

    Args:
        page_id: Page identifier like 'concepts/rag' or 'summaries/my-article'.
    """
    err = _validate_page_id(page_id, check_exists=False)
    if err:
        return f"Error: {err}"
    page_path = WIKI_DIR / f"{page_id}.md"
    if not page_path.exists():
        parts = page_id.split("/", 1)
        if len(parts) == 2:
            subdir = WIKI_DIR / parts[0]
            if subdir.exists():
                # G3 (Phase 4.5 R4 LOW): collect ALL case-insensitive matches
                # and reject if >1. Insertion-order wins on collisions is
                # non-deterministic; surfacing ambiguity is safer than
                # silently picking one match.
                matches = []
                for f in subdir.glob("*.md"):
                    if f.stem.lower() == parts[1].lower():
                        try:
                            f.resolve().relative_to(WIKI_DIR.resolve())
                        except ValueError:
                            continue
                        matches.append(f)
                if len(matches) > 1:
                    match_names = sorted(f.stem for f in matches)
                    return (
                        f"Error: ambiguous page_id — multiple files match "
                        f"{page_id} case-insensitively: {match_names}"
                    )
                if len(matches) == 1:
                    logger.warning(
                        "Case-insensitive match for '%s' → '%s'", page_id, matches[0].stem
                    )
                    page_path = matches[0]
    if not page_path.exists():
        return f"Page not found: {page_id}"
    try:
        return page_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.error("Error reading page %s: %s", page_id, e)
        return f"Error: Could not read page {page_id}: {e}"


@mcp.tool()
def kb_list_pages(page_type: str = "") -> str:
    """List all wiki pages, optionally filtered by type.

    Args:
        page_type: Filter: 'entities', 'concepts', 'comparisons', 'summaries',
                   'synthesis'. Empty returns all.
    """
    try:
        pages = load_all_pages(wiki_dir=WIKI_DIR)
        if page_type:
            # Accept both singular ("concept") and plural ("concepts") subdir names
            resolved_type = _TYPE_TO_SUBDIR.get(page_type, page_type)
            if resolved_type not in WIKI_SUBDIR_TO_TYPE:
                valid = ", ".join(sorted(WIKI_SUBDIR_TO_TYPE))
                return f"Error: Unknown page_type '{page_type}'. Valid: {valid}"
            page_type = resolved_type
            pages = [p for p in pages if p["id"].startswith(f"{page_type}/")]
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
    except Exception as e:
        logger.exception("Error in kb_list_pages")
        return f"Error: Could not list pages — {e}"


@mcp.tool()
def kb_list_sources() -> str:
    """List all raw source files in the knowledge base.

    G1 (Phase 4.5 MEDIUM): per-subdir cap (500 files) + total response size
    cap (64KB) + os.scandir (streaming) + skip dotfiles. Prevents a
    million-file subdir from OOMing the MCP process or blowing the
    transport buffer.
    """
    if not RAW_DIR.exists():
        return "No raw directory found."

    try:
        lines = ["# Raw Sources\n"]
        total = 0
        total_bytes = 0
        truncated_notice = ""
        for subdir in sorted(RAW_DIR.iterdir()):
            if not subdir.is_dir() or subdir.name.startswith("."):
                continue
            entries = []
            truncated_subdir = False
            with os.scandir(subdir) as it:
                for entry in it:
                    name = entry.name
                    if name.startswith(".") or name == ".gitkeep":
                        continue
                    try:
                        if not entry.is_file():
                            continue
                    except OSError:
                        continue
                    entries.append(entry)
                    if len(entries) >= _LIST_SOURCES_PER_SUBDIR_CAP:
                        truncated_subdir = True
                        break
            entries.sort(key=lambda e: e.name)
            if entries:
                header = (
                    f"\n## {subdir.name}/ ({len(entries)} file(s)"
                    + (" — truncated" if truncated_subdir else "")
                    + ")"
                )
                lines.append(header)
                for entry in entries:
                    try:
                        size_kb = entry.stat().st_size / 1024
                        lines.append(f"  - {entry.name} ({size_kb:.1f} KB)")
                    except OSError as e:
                        logger.warning("Could not stat %s: %s", entry.name, e)
                        lines.append(f"  - {entry.name} (size unknown)")
                    # Estimate output size — break once cap approached.
                    total_bytes = sum(len(s) for s in lines)
                    if total_bytes >= _LIST_SOURCES_TOTAL_CAP_BYTES:
                        truncated_notice = (
                            "\n\n*(Output truncated at "
                            f"{_LIST_SOURCES_TOTAL_CAP_BYTES // 1024}KB.)*"
                        )
                        break
                total += len(entries)
                if truncated_notice:
                    break

        lines.insert(1, f"**Total:** {total} source file(s)")
        if truncated_notice:
            lines.append(truncated_notice)
        return "\n".join(lines)
    except OSError as e:
        logger.error("Error listing sources: %s", e)
        return f"Error: Could not list sources: {e}"


@mcp.tool()
def kb_stats() -> str:
    """Get wiki statistics: page counts by type, graph metrics, coverage info."""
    try:
        from kb.evolve.analyzer import analyze_coverage
        from kb.graph.builder import build_graph, graph_stats

        coverage = analyze_coverage()
        graph = build_graph()
        stats = graph_stats(graph)
    except Exception as e:
        logger.exception("Error computing wiki stats")
        return f"Error computing wiki stats: {e}"

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
