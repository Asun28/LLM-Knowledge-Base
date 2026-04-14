"""Gap analysis, connection discovery, and source suggestions."""

import logging
import re
from pathlib import Path

from kb.compile.linker import build_backlinks
from kb.config import (
    MAX_PAGES_FOR_TERM,
    MIN_PAGES_FOR_TERM,
    MIN_SHARED_TERMS,
    UNDER_COVERED_TYPE_THRESHOLD,
    WIKI_DIR,
)
from kb.graph.builder import build_graph, graph_stats, page_id, scan_wiki_pages
from kb.lint.checks import check_stub_pages
from kb.utils.markdown import extract_wikilinks
from kb.utils.pages import WIKI_SUBDIRS

logger = logging.getLogger(__name__)


def analyze_coverage(wiki_dir: Path | None = None, pages: list | None = None) -> dict:
    """Analyze wiki coverage by page type and identify gaps.

    Args:
        wiki_dir: Path to wiki directory.
        pages: Pre-scanned page list from scan_wiki_pages(). If None, scans internally.

    Returns:
        dict with keys: total_pages, by_type (dict), under_covered_types,
        orphan_concepts (concepts with no backlinks).
    """
    wiki_dir = wiki_dir or WIKI_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)
    backlinks = build_backlinks(wiki_dir)

    by_type = {subdir: 0 for subdir in WIKI_SUBDIRS}
    for page_path in pages:
        subdir = page_path.parent.name
        if subdir in by_type:
            by_type[subdir] += 1

    # Find under-covered types (types with fewer than threshold pages)
    under_covered = [t for t, count in by_type.items() if count < UNDER_COVERED_TYPE_THRESHOLD]

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


MAX_CONNECTION_PAIRS = 50_000


def find_connection_opportunities(
    wiki_dir: Path | None = None, pages: list | None = None
) -> list[dict]:
    """Find pages that could be linked but aren't.

    Looks for pages that share entities/concepts in their content but have
    no direct wikilink between them.

    Args:
        wiki_dir: Path to wiki directory.
        pages: Pre-scanned page list from scan_wiki_pages(). If None, scans internally.

    Returns:
        List of dicts: {page_a, page_b, shared_terms, suggestion}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    graph = build_graph(wiki_dir)
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)

    # Build term index: which terms appear in which pages
    term_index: dict[str, list[str]] = {}
    for page_path in pages:
        try:
            raw = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            logger.warning("Skipping unreadable page %s in connection analysis", page_path)
            continue
        # Strip YAML frontmatter to avoid false-positive matches on structural keywords
        content = re.sub(r"\A---\r?\n.*?\r?\n---\r?\n?", "", raw, count=1, flags=re.DOTALL).lower()
        pid = page_id(page_path, wiki_dir)
        # Extract significant words (longer than 4 chars, not common)
        words = {
            stripped
            for w in content.split()
            if len(stripped := re.sub(r"[^\w]", "", w)) > 4
        }
        for word in words:
            if word not in term_index:
                term_index[word] = []
            term_index[word].append(pid)

    # Accumulate shared terms per pair incrementally (avoids O(V×T) re-scan)
    pair_shared_terms: dict[tuple, list[str]] = {}
    _pairs_truncated = False

    for term, page_ids in term_index.items():
        if _pairs_truncated:
            break
        if len(page_ids) < MIN_PAGES_FOR_TERM or len(page_ids) > MAX_PAGES_FOR_TERM:
            continue
        for i, page_a in enumerate(page_ids):
            if _pairs_truncated:
                break
            for page_b in page_ids[i + 1 :]:
                pair = tuple(sorted([page_a, page_b]))
                if pair not in pair_shared_terms:
                    if len(pair_shared_terms) >= MAX_CONNECTION_PAIRS:
                        logger.warning(
                            "pair_shared_terms exceeded %d pairs; connection analysis truncated",
                            MAX_CONNECTION_PAIRS,
                        )
                        _pairs_truncated = True
                        break
                    pair_shared_terms[pair] = []
                pair_shared_terms[pair].append(term)

    opportunities = []
    for pair, shared in pair_shared_terms.items():
        page_a, page_b = pair
        if len(shared) < MIN_SHARED_TERMS:
            continue
        if graph.has_edge(page_a, page_b) or graph.has_edge(page_b, page_a):
            continue
        opportunities.append(
            {
                "page_a": page_a,
                "page_b": page_b,
                "shared_term_count": len(shared),
                "shared_terms": shared[:10],
                "suggestion": f"Consider linking {page_a} ↔ {page_b} ({len(shared)} shared terms)",
            }
        )

    # Sort by number of shared terms (most shared first)
    opportunities.sort(key=lambda x: x["shared_term_count"], reverse=True)
    return opportunities[:20]  # Top 20 suggestions


def suggest_new_pages(wiki_dir: Path | None = None, pages: list | None = None) -> list[dict]:
    """Suggest new wiki pages based on dead links and graph analysis.

    Dead links (wikilinks pointing to non-existent pages) are natural
    candidates for new pages.

    Args:
        wiki_dir: Path to wiki directory.
        pages: Pre-scanned page path list from scan_wiki_pages(). If None, scans internally.

    Returns:
        List of dicts: {target, referenced_by, suggestion}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)
    existing_ids = {page_id(p, wiki_dir) for p in pages}

    # Find all targets that don't exist (dead links = page opportunities)
    suggestions: dict[str, dict] = {}
    for page_path in pages:
        try:
            content = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            logger.warning("Skipping unreadable page %s in page suggestions", page_path)
            continue
        links = extract_wikilinks(content)
        source_id = page_id(page_path, wiki_dir)
        for link in links:
            target = link  # Already normalized by extract_wikilinks()
            # Skip empty targets (e.g. "[[   ]]" artifact from LLM extraction) —
            # they would produce a ghost "Create  — referenced by…" suggestion.
            if not target:
                continue
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
    pages = scan_wiki_pages(wiki_dir)
    graph = build_graph(wiki_dir)

    coverage = analyze_coverage(wiki_dir, pages=pages)
    connections = find_connection_opportunities(wiki_dir, pages=pages)
    new_pages = suggest_new_pages(wiki_dir, pages=pages)
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
        stubs = check_stub_pages(wiki_dir)
        if stubs:
            stub_pages = [s["page"] for s in stubs]
            recommendations.append(
                f"{len(stubs)} stub page(s) need enrichment. "
                f"Top stubs: {', '.join(stub_pages[:5])}. "
                "Use kb_review_page to get context, then kb_refine_page to add content."
            )
    except (ImportError, AttributeError, RuntimeError, OSError) as e:
        logger.warning("Stub check failed in evolve: %s", e)

    # Surface low-trust pages from feedback (closes the feedback loop)
    flagged_pages: list[str] = []
    try:
        from kb.feedback.reliability import get_flagged_pages

        flagged_pages = get_flagged_pages()
        if flagged_pages:
            recommendations.append(
                f"{len(flagged_pages)} page(s) flagged as low-trust from query feedback. "
                f"Pages: {', '.join(flagged_pages[:5])}. "
                "Run kb_lint_deep on these to verify source fidelity."
            )
    except (ImportError, AttributeError, OSError, ValueError) as e:
        logger.warning("Feedback data unavailable for evolve report: %s", e)

    return {
        "coverage": coverage,
        "connection_opportunities": connections,
        "new_page_suggestions": new_pages,
        "graph_stats": {
            "nodes": stats["nodes"],
            "edges": stats["edges"],
            "components": stats["components"],
        },
        "flagged_pages": flagged_pages,
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
                f"- {co['page_a']} ↔ {co['page_b']} ({co['shared_term_count']} shared terms)"
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
