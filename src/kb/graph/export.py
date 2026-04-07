"""Export wiki graph as Mermaid diagram."""

import heapq
import logging
import re
from pathlib import Path

from kb.config import WIKI_DIR
from kb.graph.builder import build_graph
from kb.utils.pages import load_all_pages

logger = logging.getLogger(__name__)

# Default max nodes before auto-pruning
DEFAULT_MAX_NODES = 30


def _sanitize_label(text: str) -> str:
    """Sanitize text for use as a Mermaid node label.

    Removes quotes and special characters that break Mermaid syntax.
    """
    return re.sub(r'["\[\]{}|<>]', "", text).strip()


def _safe_node_id(node: str, seen: set[str] | None = None) -> str:
    """Convert a page ID to a Mermaid-safe node identifier.

    When ``seen`` is provided, appends a numeric suffix to avoid collisions
    (e.g. 'fine-tuning' and 'fine_tuning' would both map to 'fine_tuning'
    without deduplication).
    """
    base = node.replace("/", "_").replace("-", "_")
    if seen is None:
        return base
    candidate = base
    i = 2
    while candidate in seen:
        candidate = f"{base}_{i}"
        i += 1
    seen.add(candidate)
    return candidate


def export_mermaid(
    wiki_dir: Path | None = None,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> str:
    """Export the wiki knowledge graph as a Mermaid diagram.

    Auto-prunes to the most-connected nodes when the graph exceeds max_nodes.
    Uses node degree (in + out) for pruning priority.

    Args:
        wiki_dir: Path to wiki directory.
        max_nodes: Maximum nodes to include. Set to 0 for no limit.

    Returns:
        Mermaid diagram string (graph LR format).
    """
    wiki_dir = wiki_dir or WIKI_DIR
    graph = build_graph(wiki_dir)

    if graph.number_of_nodes() == 0:
        return "graph LR\n  %% No pages in wiki"

    # Load page titles from the already-scanned pages (avoids double disk scan)
    titles = {p["id"]: p["title"] for p in load_all_pages(wiki_dir)}

    # Auto-prune if needed
    nodes_to_include: set[str]
    if max_nodes > 0 and graph.number_of_nodes() > max_nodes:
        # Keep top N by total degree (most connected); nlargest is O(n log k) vs O(n log n) sort
        top = heapq.nlargest(max_nodes, graph.degree(), key=lambda x: x[1])
        nodes_to_include = {n for n, _ in top}
        logger.info(
            "Graph pruned from %d to %d nodes (by degree)",
            graph.number_of_nodes(),
            len(nodes_to_include),
        )
    else:
        nodes_to_include = set(graph.nodes())

    # Build Mermaid output
    lines = ["graph LR"]

    # Style subgraphs by page type
    type_groups: dict[str, list[str]] = {}
    for node in sorted(nodes_to_include):
        page_type = node.split("/")[0] if "/" in node else "other"
        type_groups.setdefault(page_type, []).append(node)

    # Pre-build node ID map with collision deduplication
    seen_ids: set[str] = set()
    node_id_map: dict[str, str] = {
        node: _safe_node_id(node, seen_ids) for node in sorted(nodes_to_include)
    }

    # Define nodes with labels
    for page_type, nodes in sorted(type_groups.items()):
        lines.append(f"  subgraph {page_type}")
        for node in nodes:
            title = _sanitize_label(titles.get(node, node.split("/")[-1]))
            lines.append(f'    {node_id_map[node]}["{title}"]')
        lines.append("  end")

    # Define edges (only between included nodes)
    for source, target in graph.edges():
        if source in nodes_to_include and target in nodes_to_include:
            lines.append(f"  {node_id_map[source]} --> {node_id_map[target]}")

    return "\n".join(lines)
