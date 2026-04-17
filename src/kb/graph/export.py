"""Export wiki graph as Mermaid diagram."""

import logging
import re
from pathlib import Path

import frontmatter

from kb.config import WIKI_DIR
from kb.graph.builder import build_graph
from kb.utils.pages import load_all_pages

logger = logging.getLogger(__name__)

# Default max nodes before auto-pruning
DEFAULT_MAX_NODES = 30


def _sanitize_label(text: str) -> str:
    """Sanitize text for use as a Mermaid node label.

    Removes quotes, special characters, newlines, and backticks that break Mermaid syntax.
    """
    text = text.replace("\n", " ").replace("\r", " ")
    # Fix 5.6: include ';' — semicolons break Mermaid label parsing
    return re.sub(r'["\[\]{}|<>`\(\);]', "", text).strip()


def _safe_node_id(node: str, seen: set[str] | None = None) -> str:
    """Convert a page ID to a Mermaid-safe node identifier.

    When ``seen`` is provided, appends a numeric suffix to avoid collisions
    (e.g. 'fine-tuning' and 'fine_tuning' would both map to 'fine_tuning'
    without deduplication).
    """
    # Fix 5.7: dots in page IDs (e.g., 'v0.9') break Mermaid node identifiers
    base = node.replace("/", "_").replace("-", "_").replace(".", "_")
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
    graph=None,
    wiki_dir: Path | None = None,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> str:
    """Export the wiki knowledge graph as a Mermaid diagram.

    Auto-prunes to the most-connected nodes when the graph exceeds max_nodes.
    Uses node degree (in + out) for pruning priority.

    Args:
        graph: Pre-built nx.DiGraph. If a Path is passed here (legacy positional
            call), it is treated as ``wiki_dir`` for backwards compatibility.
        wiki_dir: Path to wiki directory.
        max_nodes: Maximum nodes to include. Set to 0 for no limit.

    Returns:
        Mermaid diagram string (graph LR format).
    """
    # Backwards-compat: callers that did export_mermaid(wiki_dir) pass a Path here
    if isinstance(graph, Path):
        wiki_dir = graph
        graph = None
    wiki_dir = wiki_dir or WIKI_DIR
    if graph is None:
        graph = build_graph(wiki_dir)

    if graph.number_of_nodes() == 0:
        return "graph LR\n  %% No pages in wiki"

    # Auto-prune if needed
    nodes_to_include: set[str]
    if max_nodes > 0 and graph.number_of_nodes() > max_nodes:
        # Item 27 (cycle 2) + PR review R1 MAJOR: deterministic tie-break
        # `(degree desc, id ASC)`. `heapq.nlargest` sorts descending on the
        # whole key, so `(x[1], x[0])` would pick id DESC on ties. Use a
        # full sort with `(-degree, id)` and slice to get degree DESC + id
        # ASC ordering regardless of CPython heap behaviour.
        ordered = sorted(graph.degree(), key=lambda x: (-x[1], x[0]))
        top = ordered[:max_nodes]
        nodes_to_include = {n for n, _ in top}
        logger.info(
            "Graph pruned from %d to %d nodes (by degree)",
            graph.number_of_nodes(),
            len(nodes_to_include),
        )
    else:
        nodes_to_include = set(graph.nodes())

    # Cycle 3 M11: prune-BEFORE-load. The comment below used to claim the
    # filter "avoids unnecessary disk reads", but load_all_pages iterates
    # EVERY wiki file regardless of the filter — on a 5k-page wiki the
    # Mermaid export did ~80MB of disk I/O even when capped at 30 nodes.
    # Now we iterate only nodes_to_include and read each page's frontmatter
    # directly via the graph's stored "path" attribute. When the graph was
    # supplied by an external caller without per-node path metadata, we fall
    # back to a single load_all_pages pass (same behaviour as before).
    missing_paths = [n for n in nodes_to_include if not graph.nodes[n].get("path")]
    if missing_paths:
        logger.warning(
            "Graph export fallback: %d node(s) lack 'path' metadata; "
            "loading all pages to resolve titles",
            len(missing_paths),
        )
        titles = {
            p["id"]: p["title"]
            for p in load_all_pages(wiki_dir)
            if p["id"] in nodes_to_include
        }
    else:
        titles = {}
        for node in nodes_to_include:
            path = graph.nodes[node].get("path")
            try:
                post = frontmatter.load(path)
            except Exception as exc:  # pragma: no cover — any corrupt page is non-fatal
                logger.debug("Graph export title load failed for %s: %s", node, exc)
                continue
            titles[node] = str(post.metadata.get("title", Path(path).stem))

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
        lines.append(f'  subgraph "{page_type}"')
        for node in nodes:
            title = _sanitize_label(titles.get(node, node.split("/")[-1]))
            if not title:
                title = node.split("/")[-1]
            lines.append(f'    {node_id_map[node]}["{title}"]')
        lines.append("  end")

    # Define edges (only between included nodes)
    subgraph = graph.subgraph(nodes_to_include)
    for source, target in sorted(subgraph.edges()):
        lines.append(f"  {node_id_map[source]} --> {node_id_map[target]}")

    return "\n".join(lines)
