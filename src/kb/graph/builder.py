"""Build a networkx graph from wiki pages and their wikilinks."""

import logging
from pathlib import Path

import networkx as nx

from kb.config import WIKI_DIR
from kb.utils.markdown import FRONTMATTER_RE as _FRONTMATTER_RE
from kb.utils.markdown import extract_wikilinks
from kb.utils.pages import WIKI_SUBDIRS

logger = logging.getLogger(__name__)


def scan_wiki_pages(wiki_dir: Path | None = None) -> list[Path]:
    """Find all markdown files in wiki subdirectories (excluding index files)."""
    wiki_dir = wiki_dir or WIKI_DIR
    pages = []
    for subdir in WIKI_SUBDIRS:
        subdir_path = wiki_dir / subdir
        if subdir_path.exists():
            pages.extend(subdir_path.glob("*.md"))
    return sorted(pages)


def page_id(page_path: Path, wiki_dir: Path | None = None) -> str:
    """Convert a wiki page path to a graph node ID (e.g., 'concepts/rag').

    Note: The returned ID is lowercased for consistent node naming. The ``path``
    node attribute retains original filesystem case and must be used for all file I/O.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    return page_path.relative_to(wiki_dir).as_posix().removesuffix(".md").lower()


def build_graph(wiki_dir: Path | None = None, pages: list[dict] | None = None) -> nx.DiGraph:
    """Build a directed graph from wiki pages and their wikilinks.

    Nodes are wiki page IDs (e.g., 'concepts/rag', 'entities/openai').
    Edges represent wikilinks from one page to another.

    Args:
        wiki_dir: Path to wiki directory. Uses config default if None.
        pages: Pre-loaded page dicts (id, path, content keys). When provided,
            skips disk I/O — avoids redundant reads when callers already loaded pages.

    Returns:
        nx.DiGraph with page nodes and wikilink edges.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    graph = nx.DiGraph()

    if pages is not None:
        # Phase 4.5 HIGH L3: use pre-loaded pages to avoid disk re-reads
        for p in pages:
            graph.add_node(p["id"], path=p.get("path", ""))

        existing_ids = set(graph.nodes())
        # Phase 4.5 HIGH P1: pre-built slug index for O(1) bare-slug resolution
        slug_index = {pid.split("/")[-1]: pid for pid in existing_ids}

        for p in pages:
            content = p.get("content", "")
            fm_match = _FRONTMATTER_RE.match(content)
            body = fm_match.group(2) if fm_match else content
            links = extract_wikilinks(body)
            source_id = p["id"]
            for link in links:
                target = link
                if target not in existing_ids:
                    resolved = slug_index.get(target)
                    if resolved:
                        target = resolved
                if target in existing_ids and target != source_id:
                    graph.add_edge(source_id, target)
    else:
        page_paths = scan_wiki_pages(wiki_dir)

        for page_path in page_paths:
            pid = page_id(page_path, wiki_dir)
            graph.add_node(pid, path=str(page_path))

        existing_ids = set(graph.nodes())
        # Phase 4.5 HIGH P1: pre-built slug index for O(1) bare-slug resolution
        slug_index = {pid.split("/")[-1]: pid for pid in existing_ids}

        for page_path in page_paths:
            try:
                content = page_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Failed to read %s: %s", page_path, e)
                continue
            fm_match = _FRONTMATTER_RE.match(content)
            body = fm_match.group(2) if fm_match else content
            links = extract_wikilinks(body)
            source_id = page_id(page_path, wiki_dir)
            for link in links:
                target = link
                if target not in existing_ids:
                    resolved = slug_index.get(target)
                    if resolved:
                        logger.debug(
                            "Resolved bare-slug [[%s]] → %s in %s",
                            link,
                            resolved,
                            source_id,
                        )
                        target = resolved
                # Fix 5.1: guard against self-loops (page linking to itself)
                if target in existing_ids and target != source_id:
                    graph.add_edge(source_id, target)

    return graph


def graph_stats(graph: nx.DiGraph, *, include_centrality: bool = False) -> dict:
    """Compute basic graph statistics.

    Returns:
        dict with keys: nodes, edges, components, no_inbound (0 in-degree),
        isolated (0 degree), most_linked (highest in-degree nodes),
        pagerank (top 10 by PageRank), bridge_nodes (top 10 by betweenness centrality).

    Cycle 6 AC13: ``include_centrality`` (default ``False``) gates the
    ``nx.betweenness_centrality`` computation. Betweenness is O(V*E) and at
    5k-node scale dominates every ``kb_stats`` / ``kb_lint`` call. By default
    we skip it and return ``bridge_nodes=[]`` with ``bridge_nodes_status="skipped"``.
    Opt-in via ``include_centrality=True`` (reserved for a future
    ``kb_stats --detail`` path; not exposed via MCP per OQ11).
    """
    in_degrees = dict(graph.in_degree())
    out_degrees = dict(graph.out_degree())
    no_inbound = [n for n, d in in_degrees.items() if d == 0 and out_degrees[n] > 0]
    isolated = [n for n in graph.nodes() if in_degrees[n] == 0 and out_degrees[n] == 0]

    # Top 10 most-linked pages (Fix 5.8: exclude zero-in-degree pages)
    sorted_by_in = sorted(in_degrees.items(), key=lambda x: x[1], reverse=True)
    most_linked = [(n, d) for n, d in sorted_by_in if d > 0][:10]

    # Weakly connected components (treating directed graph as undirected)
    n_components = nx.number_weakly_connected_components(graph)

    # Top 10 pages by PageRank
    # Phase 4.5 HIGH Q4: include status metadata so consumers can distinguish
    # "failed" from "no inbound links" (degenerate).
    pagerank_status = "ok"
    try:
        pr = nx.pagerank(graph)
        pagerank = sorted(pr.items(), key=lambda x: x[1], reverse=True)[:10]
        if not pagerank or all(d == 0 for _, d in pagerank):
            pagerank_status = "degenerate"
    except (nx.PowerIterationFailedConvergence, nx.NetworkXError, ValueError) as e:
        logger.warning(
            "PageRank failed to converge on %d-node graph: %s",
            graph.number_of_nodes(),
            e,
        )
        pagerank = []
        pagerank_status = "failed"

    # Top 10 pages by betweenness centrality (bridge nodes) — gated.
    # Use sampling approximation for large graphs to avoid O(V·E) stall.
    # Fix 5.4: seed=0 makes approximation deterministic across calls.
    bridge_nodes: list = []
    bridge_status = "skipped"
    if include_centrality:
        bridge_status = "ok"
        try:
            if graph.number_of_nodes() > 500:
                bc = nx.betweenness_centrality(graph, k=500, seed=0)
            else:
                bc = nx.betweenness_centrality(graph, seed=0)
            bridge_nodes = sorted(
                ((n, c) for n, c in bc.items() if c > 0),
                key=lambda x: x[1],
                reverse=True,
            )[:10]
            if not bridge_nodes:
                bridge_status = "degenerate"
        except (nx.NetworkXError, ValueError, RuntimeError) as e:
            logger.warning("betweenness_centrality failed: %s", e)
            bridge_nodes = []
            bridge_status = "failed"

    return {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "components": n_components,
        "no_inbound": no_inbound,
        "isolated": isolated,
        "orphans": isolated,  # alias for isolated (degree-zero nodes)
        "most_linked": most_linked,
        "pagerank": pagerank,
        "pagerank_status": pagerank_status,
        "bridge_nodes": bridge_nodes,
        "bridge_nodes_status": bridge_status,
    }
