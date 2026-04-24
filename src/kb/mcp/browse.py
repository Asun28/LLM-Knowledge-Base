"""Browse & stats MCP tools — search, read, list, stats."""

import logging
import os

from kb.config import (
    MAX_QUESTION_LEN,
    MAX_SEARCH_RESULTS,
    PROJECT_ROOT,
    QUERY_CONTEXT_MAX_CHARS,
    RAW_DIR,
    WIKI_DIR,
    WIKI_SUBDIR_TO_TYPE,
)
from kb.mcp.app import _sanitize_error_str, _validate_page_id, _validate_wiki_dir, mcp
from kb.utils.pages import load_all_pages

logger = logging.getLogger(__name__)

# Maps singular type names to subdir names: "entity" → "entities", etc.
_TYPE_TO_SUBDIR = {v: k for k, v in WIKI_SUBDIR_TO_TYPE.items()}

# G1 (Phase 4.5 MEDIUM): per-subdir entry cap + total-response size cap.
# Prevents accidental or malicious million-file raw/ subdir from OOMing
# the MCP process or blowing the MCP transport buffer.
_LIST_SOURCES_PER_SUBDIR_CAP = 500
_LIST_SOURCES_TOTAL_CAP_BYTES = 64 * 1024


def _format_search_results(results: list[dict]) -> str:
    """Format `search_pages` output for human-readable CLI / MCP consumption.

    Cycle 27 AC1b — extracted from `kb_search` so the CLI `kb search`
    subcommand can reuse the identical output format without re-implementing
    the snippet-truncation + `[STALE]` marker logic. Callers that need a
    different format (e.g. JSON) should not use this helper; build a
    dedicated formatter instead.

    NOTE: This helper is NOT an MCP tool — do NOT decorate with
    ``@mcp.tool()``. The decorator belongs to ``kb_search`` below.
    """
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
        return _format_search_results(results)
    except Exception as e:
        logger.exception("Error in kb_search for query: %s", query)
        return f"Error: Search failed — {_sanitize_error_str(e)}"


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
    # Cycle 4 item #7 + PR R1 Codex MAJOR 1 — stat + bounded read so a
    # runaway wiki page (unbounded Evidence Trail, 100 MB) is capped at the
    # I/O layer, not after the full read. UTF-8 can encode up to 4 bytes
    # per character, so cap bytes at QUERY_CONTEXT_MAX_CHARS * 4 + generous
    # slack for the truncation-footer region. On decode error (mid-char
    # split at the byte boundary), fall back to latin-1 for the tail.
    cap_bytes = QUERY_CONTEXT_MAX_CHARS * 4 + 4096
    try:
        file_bytes = page_path.stat().st_size
        with page_path.open("rb") as f:
            raw = f.read(cap_bytes + 1)
    except OSError as e:
        logger.error("Error reading page %s: %s", page_id, e)
        return f"Error: Could not read page {page_id}: {_sanitize_error_str(e)}"
    truncated_at_read = len(raw) > cap_bytes
    if truncated_at_read:
        raw = raw[:cap_bytes]
    try:
        body = raw.decode("utf-8")
    except UnicodeDecodeError:
        # Last incomplete UTF-8 sequence at the read boundary — drop it.
        body = raw.decode("utf-8", errors="ignore")
    # Apply character-level cap on top of byte-level cap so the response
    # is always <= QUERY_CONTEXT_MAX_CHARS regardless of multibyte content.
    if truncated_at_read or len(body) > QUERY_CONTEXT_MAX_CHARS:
        omitted = max(
            file_bytes - len(body.encode("utf-8")),
            len(body) - QUERY_CONTEXT_MAX_CHARS,
            0,
        )
        body = body[:QUERY_CONTEXT_MAX_CHARS] + (
            f"\n\n[Truncated: ~{omitted} chars omitted; "
            f"cap={QUERY_CONTEXT_MAX_CHARS}. Use kb_list_pages + targeted tools for "
            "very large pages.]"
        )
    return body


@mcp.tool()
def kb_list_pages(page_type: str = "", limit: int = 200, offset: int = 0) -> str:
    """List all wiki pages, optionally filtered by type.

    Args:
        page_type: Filter: 'entities', 'concepts', 'comparisons', 'summaries',
                   'synthesis'. Empty returns all.
        limit: Maximum pages to return (clamped to [1, 1000]). Default 200.
        offset: Skip this many pages before returning (default 0).

    Cycle 3 M13: added pagination so a large wiki does not force the full
    serialized list through the MCP transport in a single response. Pages
    are deterministically sorted by ``load_all_pages`` (directory-then-slug).
    Header reports the window: ``Showing <shown> of <total> page(s)
    (offset=<offset>, limit=<limit>)``.
    """
    try:
        # Clamp pagination params defensively — untrusted MCP input. Coercion
        # errors (e.g. limit='x') surface as an Error string, not a raise.
        try:
            limit = max(1, min(int(limit), 1000))
            offset = max(0, int(offset))
        except (TypeError, ValueError) as exc:
            return f"Error: invalid limit/offset: {exc}"
        pages = load_all_pages(wiki_dir=WIKI_DIR)
        if page_type:
            # Accept both singular ("concept") and plural ("concepts") subdir names
            resolved_type = _TYPE_TO_SUBDIR.get(page_type, page_type)
            if resolved_type not in WIKI_SUBDIR_TO_TYPE:
                valid = ", ".join(sorted(WIKI_SUBDIR_TO_TYPE))
                return f"Error: Unknown page_type '{page_type}'. Valid: {valid}"
            page_type = resolved_type
            pages = [p for p in pages if p["id"].startswith(f"{page_type}/")]
        total = len(pages)
        if total == 0:
            return "No pages found."
        window = pages[offset : offset + limit]
        if not window:
            return f"No pages in window (offset={offset}, limit={limit}, total={total})."
        # Cycle 3 M13: emit BOTH the legacy "Total: N page(s)" line (so
        # existing callers/test assertions remain valid) and the new
        # "Showing Y of N ..." pagination line so operators see the window.
        lines = [
            f"Total: {total} page(s)",
            f"Showing {len(window)} of {total} page(s) (offset={offset}, limit={limit})\n",
        ]
        current_type = ""
        for p in window:
            ptype = p["id"].split("/")[0]
            if ptype != current_type:
                current_type = ptype
                lines.append(f"\n## {current_type}")
            lines.append(f"- {p['id']} — {p['title']} ({p['type']}, {p['confidence']})")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("Error in kb_list_pages")
        return f"Error: Could not list pages — {_sanitize_error_str(e)}"


@mcp.tool()
def kb_list_sources(limit: int = 200, offset: int = 0) -> str:
    """List all raw source files in the knowledge base.

    G1 (Phase 4.5 MEDIUM): per-subdir cap (500 files) + total response size
    cap (64KB) + os.scandir (streaming) + skip dotfiles. Prevents a
    million-file subdir from OOMing the MCP process or blowing the
    transport buffer.

    Cycle 3 M13: ``limit`` and ``offset`` apply AFTER the per-subdir caps
    above, operating on the flattened list of entries sorted within each
    subdir. ``limit`` is clamped to [1, 1000]; ``offset`` clamped to [0, ∞).
    Subdir iteration order is ``sorted(RAW_DIR.iterdir())`` so pagination is
    deterministic across runs on the same filesystem.
    """
    try:
        # Clamp pagination params defensively — untrusted MCP input. Coercion
        # errors (e.g. limit='x') must surface as an Error string, not raise
        # through to the MCP framework (contract: MCP tools never raise).
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))
    except (TypeError, ValueError) as exc:
        return f"Error: invalid limit/offset: {exc}"
    if not RAW_DIR.exists():
        return "No raw directory found."

    try:
        # Cycle 3 M13: flatten (subdir, entry) pairs in deterministic order
        # so limit/offset windowing is stable across runs. The per-subdir
        # cap (G1) still applies to each subdir's local scan.
        flat_entries: list[tuple[str, os.DirEntry, bool]] = []
        per_subdir_counts: dict[str, tuple[int, bool]] = {}
        for subdir in sorted(RAW_DIR.iterdir()):
            if not subdir.is_dir() or subdir.name.startswith("."):
                continue
            entries: list[os.DirEntry] = []
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
            per_subdir_counts[subdir.name] = (len(entries), truncated_subdir)
            for e in entries:
                flat_entries.append((subdir.name, e, truncated_subdir))

        total_global = len(flat_entries)
        window = flat_entries[offset : offset + limit]
        # PR review R1 Sonnet MAJOR: mirror kb_list_pages' empty-window
        # guard so offset>=total returns an explicit Error string instead
        # of silently emitting the header with no body. Lets callers
        # detect "past end" without string-matching the pagination header.
        if not window and total_global > 0:
            return f"No sources in window (offset={offset}, limit={limit}, total={total_global})."
        # Cycle 3 M13: retain the legacy "Total: N source file(s)" line so
        # existing test assertions (test_mcp_browse_health, etc.) continue
        # to match; append pagination line below it.
        lines = [
            "# Raw Sources\n",
            f"**Total:** {total_global} source file(s)",
            f"Showing {len(window)} of {total_global} file(s) (offset={offset}, limit={limit})\n",
        ]
        total_bytes = 0
        truncated_notice = ""
        current_subdir = ""
        total = 0
        for subdir_name, entry, truncated_subdir in window:
            if subdir_name != current_subdir:
                current_subdir = subdir_name
                count, sub_trunc = per_subdir_counts[subdir_name]
                header = (
                    f"\n## {subdir_name}/ ({count} file(s)"
                    + (" — truncated" if sub_trunc else "")
                    + ")"
                )
                lines.append(header)
            try:
                size_kb = entry.stat().st_size / 1024
                lines.append(f"  - {entry.name} ({size_kb:.1f} KB)")
            except OSError as e:
                logger.warning("Could not stat %s: %s", entry.name, e)
                lines.append(f"  - {entry.name} (size unknown)")
            total += 1
            # Estimate output size — break once cap approached.
            total_bytes = sum(len(s) for s in lines)
            if total_bytes >= _LIST_SOURCES_TOTAL_CAP_BYTES:
                truncated_notice = (
                    f"\n\n*(Output truncated at {_LIST_SOURCES_TOTAL_CAP_BYTES // 1024}KB.)*"
                )
                break

        if truncated_notice:
            lines.append(truncated_notice)
        return "\n".join(lines)
    except OSError as e:
        logger.error("Error listing sources: %s", e)
        return f"Error: Could not list sources: {_sanitize_error_str(e)}"


@mcp.tool()
def kb_stats(wiki_dir: str | None = None) -> str:
    """Get wiki statistics: page counts by type, graph metrics, coverage info."""
    try:
        from kb.evolve.analyzer import analyze_coverage
        from kb.graph.builder import build_graph, graph_stats

        wiki_path, err = _validate_wiki_dir(wiki_dir, project_root=PROJECT_ROOT)
        if err:
            return f"Error: {err}"

        coverage = analyze_coverage(wiki_dir=wiki_path)
        graph = build_graph(wiki_dir=wiki_path)
        stats = graph_stats(graph)
    except Exception as e:
        logger.exception("Error computing wiki stats")
        return f"Error computing wiki stats: {_sanitize_error_str(e)}"

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
