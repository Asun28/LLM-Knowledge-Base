"""Gap analysis, connection discovery, and source suggestions."""

from pathlib import Path

from kb.compile.linker import build_backlinks
from kb.config import MAX_PAGES_FOR_TERM, MIN_PAGES_FOR_TERM, MIN_SHARED_TERMS, WIKI_DIR
from kb.graph.builder import build_graph, graph_stats, page_id, scan_wiki_pages
from kb.utils.markdown import extract_wikilinks


def analyze_coverage(wiki_dir: Path | None = None) -> dict:
    """Analyze wiki coverage by page type and identify gaps.

    Returns:
        dict with keys: total_pages, by_type (dict), under_covered_types,
        orphan_concepts (concepts with no backlinks).
    """
    wiki_dir = wiki_dir or WIKI_DIR
    pages = scan_wiki_pages(wiki_dir)
    backlinks = build_backlinks(wiki_dir)

    by_type = {"entities": 0, "concepts": 0, "comparisons": 0, "summaries": 0, "synthesis": 0}
    for page_path in pages:
        subdir = page_path.parent.name
        if subdir in by_type:
            by_type[subdir] += 1

    # Find under-covered types (types with zero pages)
    under_covered = [t for t, count in by_type.items() if count == 0]

    # Find concepts with no backlinks (nobody references them)
    orphan_concepts = []
    for page_path in pages:
        pid = page_id(page_path, wiki_dir)
        if pid.startswith("concepts/") and pid not in backlinks:
            orphan_concepts.append(pid)

    return {
        "total_pages": len(pages),
        "by_type": by_type,
        "under_covered_types": under_covered,
        "orphan_concepts": orphan_concepts,
    }


def find_connection_opportunities(wiki_dir: Path | None = None) -> list[dict]:
    """Find pages that could be linked but aren't.

    Looks for pages that share entities/concepts in their content but have
    no direct wikilink between them.

    Returns:
        List of dicts: {page_a, page_b, shared_terms, suggestion}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    graph = build_graph(wiki_dir)
    pages = scan_wiki_pages(wiki_dir)

    # Build term index: which terms appear in which pages
    term_index: dict[str, list[str]] = {}
    for page_path in pages:
        content = page_path.read_text(encoding="utf-8").lower()
        pid = page_id(page_path, wiki_dir)
        # Extract significant words (longer than 4 chars, not common)
        words = set(w.strip(".,!?()[]{}\"'") for w in content.split() if len(w) > 4)
        for word in words:
            if word not in term_index:
                term_index[word] = []
            term_index[word].append(pid)

    # Find page pairs sharing terms but not linked
    opportunities = []
    seen_pairs: set[tuple[str, str]] = set()

    for term, page_ids in term_index.items():
        if len(page_ids) < MIN_PAGES_FOR_TERM or len(page_ids) > MAX_PAGES_FOR_TERM:
            continue
        for i, page_a in enumerate(page_ids):
            for page_b in page_ids[i + 1 :]:
                pair = tuple(sorted([page_a, page_b]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                # Check if they're already linked
                if not graph.has_edge(page_a, page_b) and not graph.has_edge(page_b, page_a):
                    # Count shared terms
                    shared = [
                        t
                        for t, pids in term_index.items()
                        if page_a in pids and page_b in pids and len(pids) <= MAX_PAGES_FOR_TERM
                    ]
                    if len(shared) >= MIN_SHARED_TERMS:
                        opportunities.append(
                            {
                                "page_a": page_a,
                                "page_b": page_b,
                                "shared_terms": shared[:10],  # Top 10 shared terms
                                "suggestion": f"Consider linking {page_a} ↔ {page_b} "
                                f"({len(shared)} shared terms)",
                            }
                        )

    # Sort by number of shared terms (most shared first)
    opportunities.sort(key=lambda x: len(x["shared_terms"]), reverse=True)
    return opportunities[:20]  # Top 20 suggestions


def suggest_new_pages(wiki_dir: Path | None = None) -> list[dict]:
    """Suggest new wiki pages based on dead links and graph analysis.

    Dead links (wikilinks pointing to non-existent pages) are natural
    candidates for new pages.

    Returns:
        List of dicts: {target, referenced_by, suggestion}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    pages = scan_wiki_pages(wiki_dir)
    existing_ids = {page_id(p, wiki_dir) for p in pages}

    # Find all targets that don't exist (dead links = page opportunities)
    suggestions: dict[str, dict] = {}
    for page_path in pages:
        content = page_path.read_text(encoding="utf-8")
        links = extract_wikilinks(content)
        source_id = page_id(page_path, wiki_dir)
        for link in links:
            target = link  # Already normalized by extract_wikilinks()
            if target not in existing_ids:
                if target not in suggestions:
                    suggestions[target] = {"target": target, "referenced_by": []}
                suggestions[target]["referenced_by"].append(source_id)

    result = []
    for target, info in suggestions.items():
        info["suggestion"] = (
            f"Create {target} — referenced by {len(info['referenced_by'])} page(s): "
            f"{', '.join(info['referenced_by'][:5])}"
        )
        result.append(info)

    # Sort by number of references (most referenced first)
    result.sort(key=lambda x: len(x["referenced_by"]), reverse=True)
    return result


def generate_evolution_report(wiki_dir: Path | None = None) -> dict:
    """Generate a comprehensive evolution/gap analysis report.

    Args:
        wiki_dir: Path to wiki directory.

    Returns:
        dict with keys: coverage, connection_opportunities, new_page_suggestions,
        graph_stats, recommendations.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    graph = build_graph(wiki_dir)

    coverage = analyze_coverage(wiki_dir)
    connections = find_connection_opportunities(wiki_dir)
    new_pages = suggest_new_pages(wiki_dir)
    stats = graph_stats(graph)

    # Build recommendations
    recommendations = []

    if coverage["under_covered_types"]:
        recommendations.append(
            f"Missing page types: {', '.join(coverage['under_covered_types'])}. "
            "Consider adding these to improve wiki structure."
        )

    if coverage["orphan_concepts"]:
        recommendations.append(
            f"{len(coverage['orphan_concepts'])} concept(s) have no backlinks. "
            "Link them from other pages to improve discoverability."
        )

    if connections:
        recommendations.append(
            f"{len(connections)} potential connections found between unlinked pages. "
            "Review and add wikilinks where appropriate."
        )

    if new_pages:
        recommendations.append(
            f"{len(new_pages)} new page(s) suggested from dead links. "
            "Create these pages to resolve broken references."
        )

    if stats["components"] > 1:
        recommendations.append(
            f"Wiki has {stats['components']} disconnected components. "
            "Consider adding cross-links to improve connectivity."
        )

    # Suggest enriching stubs
    try:
        from kb.lint.checks import check_stub_pages

        stubs = check_stub_pages(wiki_dir)
        if stubs:
            stub_pages = [s["page"] for s in stubs]
            recommendations.append(
                f"{len(stubs)} stub page(s) need enrichment. "
                f"Top stubs: {', '.join(stub_pages[:5])}. "
                "Use kb_review_page to get context, then kb_refine_page to add content."
            )
    except Exception as e:
        import logging

        logging.getLogger(__name__).debug("Stub check failed in evolve: %s", e)

    return {
        "coverage": coverage,
        "connection_opportunities": connections,
        "new_page_suggestions": new_pages,
        "graph_stats": {
            "nodes": stats["nodes"],
            "edges": stats["edges"],
            "components": stats["components"],
        },
        "recommendations": recommendations,
    }


def format_evolution_report(report: dict) -> str:
    """Format an evolution report as readable text."""
    lines = ["# Wiki Evolution Report\n"]

    # Coverage
    cov = report["coverage"]
    lines.append("## Coverage\n")
    lines.append(f"**Total pages:** {cov['total_pages']}")
    for ptype, count in cov["by_type"].items():
        lines.append(f"  - {ptype}: {count}")
    lines.append("")

    if cov["under_covered_types"]:
        lines.append(f"**Missing types:** {', '.join(cov['under_covered_types'])}")
        lines.append("")

    # Graph stats
    gs = report["graph_stats"]
    lines.append("## Graph\n")
    lines.append(
        f"**Nodes:** {gs['nodes']} | **Edges:** {gs['edges']} | **Components:** {gs['components']}"
    )
    lines.append("")

    # New page suggestions
    if report["new_page_suggestions"]:
        lines.append("## Suggested New Pages\n")
        for np in report["new_page_suggestions"][:10]:
            lines.append(f"- **{np['target']}** — referenced by {len(np['referenced_by'])} page(s)")
        lines.append("")

    # Connection opportunities
    if report["connection_opportunities"]:
        lines.append("## Connection Opportunities\n")
        for co in report["connection_opportunities"][:10]:
            lines.append(
                f"- {co['page_a']} ↔ {co['page_b']} ({len(co['shared_terms'])} shared terms)"
            )
        lines.append("")

    # Recommendations
    if report["recommendations"]:
        lines.append("## Recommendations\n")
        for rec in report["recommendations"]:
            lines.append(f"- {rec}")
        lines.append("")
    else:
        lines.append("No recommendations — wiki is in good shape!\n")

    return "\n".join(lines)
