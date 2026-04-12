"""Build a networkx graph from wiki pages and their wikilinks."""

import logging
from pathlib import Path

import networkx as nx

from kb.config import WIKI_DIR, WIKI_SUBDIR_TO_TYPE
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
    """Convert a wiki page path to a graph node ID (e.g., 'concepts/rag')."""
    wiki_dir = wiki_dir or WIKI_DIR
    return str(page_path.relative_to(wiki_dir)).replace("\\", "/").removesuffix(".md").lower()


def build_graph(wiki_dir: Path | None = None) -> nx.DiGraph:
    """Build a directed graph from wiki pages and their wikilinks.

    Nodes are wiki page IDs (e.g., 'concepts/rag', 'entities/openai').
    Edges represent wikilinks from one page to another.

    Args:
        wiki_dir: Path to wiki directory. Uses config default if None.

    Returns:
        nx.DiGraph with page nodes and wikilink edges.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    graph = nx.DiGraph()
    pages = scan_wiki_pages(wiki_dir)

    # Add all pages as nodes
    for page_path in pages:
        pid = page_id(page_path, wiki_dir)
        graph.add_node(pid, path=str(page_path))

    # Add edges from wikilinks (only to existing nodes)
    existing_ids = set(graph.nodes())
    for page_path in pages:
        try:
            content = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read %s: %s", page_path, e)
            continue
        # Strip frontmatter before extracting wikilinks to avoid false matches in YAML values
        fm_match = _FRONTMATTER_RE.match(content)
        body = fm_match.group(2) if fm_match else content
        links = extract_wikilinks(body)
        source_id = page_id(page_path, wiki_dir)
        for link in links:
            target = link
            # Resolve bare slugs (e.g. [[foo]] → entities/foo) by trying known subdirs
            if target not in existing_ids:
                for subdir in WIKI_SUBDIR_TO_TYPE:
                    candidate = f"{subdir}/{target}"
                    if candidate in existing_ids:
                        logger.debug(
                            "Resolved bare-slug [[%s]] → %s in %s",
                            link, candidate, source_id,
                        )
                        target = candidate
                        break
            # Fix 5.1: guard against self-loops (page linking to itself)
            if target in existing_ids and target != source_id:
                graph.add_edge(source_id, target)

    return graph


def graph_stats(graph: nx.DiGraph) -> dict:
    """Compute basic graph statistics.

    Returns:
        dict with keys: nodes, edges, components, no_inbound (0 in-degree),
        isolated (0 degree), most_linked (highest in-degree nodes),
        pagerank (top 10 by PageRank), bridge_nodes (top 10 by betweenness centrality).
    """
    in_degrees = dict(graph.in_degree())
    no_inbound = [n for n, d in in_degrees.items() if d == 0 and graph.out_degree(n) > 0]
    isolated = [n for n in graph.nodes() if graph.degree(n) == 0]

    # Top 10 most-linked pages (Fix 5.8: exclude zero-in-degree pages)
    sorted_by_in = sorted(in_degrees.items(), key=lambda x: x[1], reverse=True)
    most_linked = [(n, d) for n, d in sorted_by_in if d > 0][:10]

    # Weakly connected components (treating directed graph as undirected)
    n_components = nx.number_weakly_connected_components(graph)

    # Top 10 pages by PageRank
    try:
        pr = nx.pagerank(graph)
        pagerank = sorted(pr.items(), key=lambda x: x[1], reverse=True)[:10]
    except (nx.PowerIterationFailedConvergence, nx.NetworkXError, ValueError) as e:
        logger.warning(
            "PageRank failed to converge on %d-node graph: %s",
            graph.number_of_nodes(), e,
        )
        pagerank = []

    # Top 10 pages by betweenness centrality (bridge nodes)
    # Use sampling approximation for large graphs to avoid O(V·E) stall.
    # Fix 5.4: seed=0 makes approximation deterministic across calls.
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
    except (nx.NetworkXError, ValueError, RuntimeError) as e:
        logger.warning("betweenness_centrality failed: %s", e)
        bridge_nodes = []

    return {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "components": n_components,
        "no_inbound": no_inbound,
        "isolated": isolated,
        "most_linked": most_linked,
        "pagerank": pagerank,
        "bridge_nodes": bridge_nodes,
    }
