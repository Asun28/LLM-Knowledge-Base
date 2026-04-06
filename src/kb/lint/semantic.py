"""Semantic lint checks — build contexts for LLM-powered quality evaluation."""

from pathlib import Path

import frontmatter

from kb.config import MAX_CONSISTENCY_GROUP_SIZE, WIKI_DIR
from kb.graph.builder import build_graph, page_id, scan_wiki_pages
from kb.review.context import pair_page_with_sources


def build_fidelity_context(
    page_id_str: str, wiki_dir: Path | None = None, raw_dir: Path | None = None
) -> str:
    """Build source fidelity check context: page content paired with source content.

    Returns formatted text for Claude Code to evaluate whether each claim
    in the wiki page traces to a specific passage in the raw source(s).
    """
    paired = pair_page_with_sources(page_id_str, wiki_dir, raw_dir)

    if "error" in paired and "page_content" not in paired:
        return f"Error: {paired['error']}"

    lines = [
        f"# Source Fidelity Check: {page_id_str}\n",
        "Evaluate whether each factual claim in the wiki page can be traced "
        "to a specific passage in the raw source(s).\n",
        "---\n",
        "## Wiki Page\n",
        paired["page_content"],
        "\n---\n",
    ]

    for i, source in enumerate(paired["source_contents"], 1):
        lines.append(f"## Source {i}: {source['path']}\n")
        if source.get("content"):
            lines.append(source["content"])
        else:
            lines.append(f"*Not available: {source.get('error', 'unknown')}*")
        lines.append("\n---\n")

    lines.append(
        "For each factual claim in the wiki page, identify whether it is:\n"
        "- **Traced**: directly supported by a passage in the source\n"
        "- **Inferred**: reasonably deduced from the source but not stated\n"
        "- **Unsourced**: not found in the source material\n"
    )

    return "\n".join(lines)


def _group_by_shared_sources(wiki_dir: Path) -> list[list[str]]:
    """Group pages that share raw sources (from frontmatter source: fields)."""
    pages = scan_wiki_pages(wiki_dir)
    source_to_pages: dict[str, list[str]] = {}

    for page_path in pages:
        try:
            post = frontmatter.load(str(page_path))
            pid = page_id(page_path, wiki_dir)
            sources = post.metadata.get("source", [])
            if isinstance(sources, str):
                sources = [sources]
            for src in sources:
                source_to_pages.setdefault(src, []).append(pid)
        except Exception:
            continue

    return [pids for pids in source_to_pages.values() if len(pids) >= 2]


def _group_by_wikilinks(wiki_dir: Path) -> list[list[str]]:
    """Group pages connected by wikilinks (direct neighbors in the graph)."""
    graph = build_graph(wiki_dir)
    groups = []
    seen: set[str] = set()

    for node in graph.nodes():
        if node in seen:
            continue
        neighbors = set(graph.successors(node)) | set(graph.predecessors(node))
        # Only keep neighbors that exist as graph nodes
        existing_neighbors = {n for n in neighbors if graph.has_node(n)}
        if existing_neighbors:
            group = sorted(existing_neighbors | {node})
            groups.append(group)
            seen.update(group)

    return [g for g in groups if len(g) >= 2]


def _group_by_term_overlap(wiki_dir: Path) -> list[list[str]]:
    """Group pages with high term overlap (>= 3 shared significant terms)."""
    pages = scan_wiki_pages(wiki_dir)
    page_terms: dict[str, set[str]] = {}

    for page_path in pages:
        content = page_path.read_text(encoding="utf-8").lower()
        pid = page_id(page_path, wiki_dir)
        words = {w.strip(".,!?()[]{}\"'") for w in content.split() if len(w) > 4}
        page_terms[pid] = words

    groups = []
    page_ids_list = list(page_terms.keys())
    seen_pairs: set[tuple[str, str]] = set()

    for i, pid_a in enumerate(page_ids_list):
        for pid_b in page_ids_list[i + 1 :]:
            pair = (pid_a, pid_b)
            if pair in seen_pairs:
                continue
            shared = page_terms[pid_a] & page_terms[pid_b]
            if len(shared) >= 3:
                groups.append(sorted([pid_a, pid_b]))
                seen_pairs.add(pair)

    return groups


def build_consistency_context(
    page_ids: list[str] | None = None,
    wiki_dir: Path | None = None,
    raw_dir: Path | None = None,
) -> str:
    """Build cross-page consistency check context.

    If page_ids is provided, uses them as a single group.
    Otherwise, auto-selects groups using shared sources and wikilinks.

    Returns formatted text for Claude Code to check for contradictions.
    """
    wiki_dir = wiki_dir or WIKI_DIR

    if page_ids:
        groups = [page_ids[:MAX_CONSISTENCY_GROUP_SIZE]]
    else:
        # Auto-select using three strategies (priority order per spec)
        all_groups: list[list[str]] = []
        all_groups.extend(_group_by_shared_sources(wiki_dir))
        all_groups.extend(_group_by_wikilinks(wiki_dir))
        all_groups.extend(_group_by_term_overlap(wiki_dir))

        # Deduplicate by sorted tuple
        seen: set[tuple[str, ...]] = set()
        groups = []
        for group in all_groups:
            key = tuple(sorted(group))
            if key not in seen:
                seen.add(key)
                groups.append(list(key)[:MAX_CONSISTENCY_GROUP_SIZE])

    if not groups:
        return "No page groups found for consistency checking."

    lines = [
        "# Cross-Page Consistency Check\n",
        f"Found {len(groups)} group(s) of related pages to check for contradictions.\n",
        "For each group, identify any claims that contradict each other.\n",
    ]

    for gi, group in enumerate(groups, 1):
        lines.append(f"## Group {gi} ({len(group)} pages)\n")
        for pid in group:
            page_path = wiki_dir / f"{pid}.md"
            if page_path.exists():
                content = page_path.read_text(encoding="utf-8")
                lines.append(f"### {pid}\n")
                lines.append(content)
                lines.append("\n---\n")

    return "\n".join(lines)


def build_completeness_context(
    page_id_str: str, wiki_dir: Path | None = None, raw_dir: Path | None = None
) -> str:
    """Build completeness check context: source alongside page for gap detection.

    Returns formatted text for Claude Code to identify key claims from the
    source that are NOT represented in the wiki page.
    """
    paired = pair_page_with_sources(page_id_str, wiki_dir, raw_dir)

    if "error" in paired and "page_content" not in paired:
        return f"Error: {paired['error']}"

    lines = [
        f"# Completeness Check: {page_id_str}\n",
        "Evaluate whether key claims from the raw source(s) are represented "
        "in the wiki page. Identify important omissions.\n",
        "---\n",
        "## Wiki Page\n",
        paired["page_content"],
        "\n---\n",
    ]

    for i, source in enumerate(paired["source_contents"], 1):
        lines.append(f"## Source {i}: {source['path']}\n")
        if source.get("content"):
            lines.append(source["content"])
        else:
            lines.append(f"*Not available: {source.get('error', 'unknown')}*")
        lines.append("\n---\n")

    lines.append(
        "List any key claims, facts, or arguments from the source(s) that are "
        "NOT represented in the wiki page.\n"
    )

    return "\n".join(lines)
