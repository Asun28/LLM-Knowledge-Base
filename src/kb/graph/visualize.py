"""Interactive knowledge graph visualization with pyvis."""

from pathlib import Path

import networkx as nx

from kb.config import PROJECT_ROOT


# Color mapping for wiki page types
TYPE_COLORS = {
    "entities": "#4ecdc4",
    "concepts": "#ff6b6b",
    "comparisons": "#ffd93d",
    "summaries": "#6bcb77",
    "synthesis": "#9b59b6",
}


def visualize_graph(graph: nx.DiGraph, output_path: Path | None = None) -> Path:
    """Generate an interactive HTML visualization of the wiki knowledge graph.

    Args:
        graph: The wiki knowledge graph from build_graph().
        output_path: Where to save the HTML file. Defaults to PROJECT_ROOT/.data/graph.html.

    Returns:
        Path to the generated HTML file.
    """
    from pyvis.network import Network

    output_path = output_path or (PROJECT_ROOT / ".data" / "graph.html")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    net = Network(height="800px", width="100%", directed=True, bgcolor="#1a1a2e")
    net.barnes_hut(gravity=-3000, central_gravity=0.3, spring_length=150)

    # Add nodes with colors based on page type
    for node in graph.nodes():
        page_type = node.split("/")[0] if "/" in node else "other"
        color = TYPE_COLORS.get(page_type, "#95a5a6")
        label = node.split("/")[-1] if "/" in node else node
        size = 10 + graph.in_degree(node) * 3
        net.add_node(node, label=label, color=color, size=size, title=node)

    # Add edges
    for source, target in graph.edges():
        net.add_edge(source, target, color="#ffffff44")

    net.write_html(str(output_path))
    return output_path
