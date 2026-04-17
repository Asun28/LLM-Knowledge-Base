"""Health MCP tools — lint, evolve."""

import logging
from pathlib import Path

from kb.graph.export import export_mermaid
from kb.mcp.app import mcp

logger = logging.getLogger(__name__)


@mcp.tool()
def kb_lint(
    fix: bool = False,
    augment: bool = False,
    dry_run: bool = False,
    execute: bool = False,
    auto_ingest: bool = False,
    max_gaps: int = 5,
    wiki_dir: str | None = None,
) -> str:
    """Run health checks on the wiki. Reports dead links, orphans, staleness, etc.

    Args:
        fix: If True, auto-fix dead wikilinks (replace with plain text).
        augment: If True, also run reactive gap-fill (kb_lint --augment).
        dry_run: With augment, preview without writing proposals/raw/wiki.
        execute: With augment, fetch + save raw files (no ingest). Requires augment=True.
        auto_ingest: With augment+execute, also pre-extract + ingest. Requires execute=True.
        max_gaps: Max stub gaps to attempt per augment run (default 5; hard ceiling 10).
        wiki_dir: Override wiki directory (default: kb.config.WIKI_DIR).

    Returns:
        Formatted lint report. When augment=True, appends ## Augment Summary section.
    """
    # Three-gate dependency validation — parity with CLI (cli.py:167-175).
    # MCP tools return "Error: ..." strings instead of raising to the client.
    from kb.config import AUGMENT_FETCH_MAX_CALLS_PER_RUN

    if execute and not augment:
        return "Error: --execute requires --augment"
    if auto_ingest and not execute:
        return "Error: --auto-ingest requires --execute (and --augment)"
    # B4 (Phase 5 three-round MEDIUM): reject non-positive values so negative
    # max_gaps doesn't silently truncate proposals via Python slicing.
    if max_gaps < 1:
        return f"Error: max_gaps={max_gaps} must be a positive integer"
    if max_gaps > AUGMENT_FETCH_MAX_CALLS_PER_RUN:
        return (
            f"Error: max_gaps={max_gaps} exceeds hard ceiling "
            f"AUGMENT_FETCH_MAX_CALLS_PER_RUN={AUGMENT_FETCH_MAX_CALLS_PER_RUN}"
        )

    try:
        from kb.lint.runner import format_report, run_all_checks

        wiki_path = Path(wiki_dir) if wiki_dir else None
        report = run_all_checks(wiki_dir=wiki_path, fix=fix)
        result = format_report(report)
    except Exception as e:
        logger.error("Error running lint checks: %s", e)
        return f"Error: kb_lint failed: {type(e).__name__}: {e}"

    # Append feedback-flagged pages (fail-safe)
    try:
        from kb.feedback.reliability import get_flagged_pages

        flagged = get_flagged_pages()
        if flagged:
            result += (
                "\n## Low-Trust Pages (from query feedback)\n\n"
                f"{len(flagged)} page(s) with trust score below threshold:\n"
            )
            for p in flagged:
                result += f'- {p} — run `kb_lint_deep("{p}")` for fidelity check\n'
    except Exception as e:
        logger.warning("Failed to load feedback data for lint: %s", e)

    if augment:
        try:
            from kb.lint.augment import run_augment

            mode = "auto_ingest" if auto_ingest else ("execute" if execute else "propose")
            augment_result = run_augment(
                wiki_dir=wiki_path,
                mode=mode,
                max_gaps=max_gaps,
                dry_run=dry_run,
            )
            result += "\n\n" + augment_result["summary"]
        except Exception as e:
            logger.error("Error running augment: %s", e)
            return f"Error: kb_lint failed: {type(e).__name__}: {e}"

    return result


@mcp.tool()
def kb_evolve() -> str:
    """Analyze knowledge gaps and suggest new connections, pages, and sources."""
    try:
        from kb.evolve.analyzer import format_evolution_report, generate_evolution_report

        report = generate_evolution_report()
        result = format_evolution_report(report)
    except Exception as e:
        logger.error("Error running evolution analysis: %s", e)
        return f"Error: Evolution analysis failed — {e}"

    # Append coverage gaps from query feedback (fail-safe)
    try:
        from kb.feedback.reliability import get_coverage_gaps

        gaps = get_coverage_gaps()
        if gaps:
            result += (
                "\n## Coverage Gaps (from query feedback)\n\n"
                f"{len(gaps)} query/queries returned incomplete answers:\n"
            )
            for g in gaps:
                notes = f" — {g['notes']}" if g["notes"] else ""
                result += f'- "{g["question"]}"{notes}\n'
    except Exception as e:
        logger.warning("Failed to load feedback data for evolve: %s", e)

    return result


@mcp.tool()
def kb_graph_viz(max_nodes: int = 30) -> str:
    """Export the wiki knowledge graph as a Mermaid diagram.

    Renders the knowledge graph as a Mermaid flowchart (graph LR).
    Auto-prunes to the most-connected nodes when graph exceeds max_nodes.
    Compatible with Obsidian, GitHub, VS Code Mermaid previews.

    Note: Large node counts (> 100) may produce diagrams too large to render
    in some tools. Use max_nodes to limit output size.

    Args:
        max_nodes: Maximum nodes to include (1–500; default 30).

    Cycle 3 M16: rejects ``max_nodes=0`` with an explicit error instead of
    silently remapping to 30. The prior silent-remap docstring advertised 0
    as "all nodes" while the code quietly returned a 30-node slice — agents
    following the docstring got an incomplete graph with no signal.
    """
    if max_nodes == 0:
        return (
            "Error: max_nodes=0 is not allowed; use a positive integer (1–500). "
            "Previously this silently remapped to 30 — cycle 3 M16 surfaces the "
            "inconsistency so callers can choose a valid cap explicitly."
        )
    max_nodes = max(1, min(max_nodes, 500))
    try:
        return export_mermaid(max_nodes=max_nodes)
    except Exception as e:
        logger.error("Error exporting graph: %s", e)
        return f"Error: Graph export failed — {e}"


@mcp.tool()
def kb_verdict_trends() -> str:
    """Show verdict quality trends over time.

    Analyzes the verdict history to show pass/fail/warning rates by week
    and whether quality is improving, stable, or declining.
    """
    try:
        from kb.lint.trends import compute_verdict_trends, format_verdict_trends

        trends = compute_verdict_trends()
        return format_verdict_trends(trends)
    except Exception as e:
        logger.error("Error computing verdict trends: %s", e)
        return f"Error: Verdict trends failed — {e}"


@mcp.tool()
def kb_detect_drift() -> str:
    """Detect wiki pages that may be stale due to raw source changes.

    Compares current source content hashes against the compile manifest
    to find changed sources, then identifies which wiki pages reference
    those sources. Use this before re-compiling to understand impact.
    """
    try:
        from kb.compile.compiler import detect_source_drift

        result = detect_source_drift()
    except Exception as e:
        logger.error("Error detecting source drift: %s", e)
        return f"Error: Source drift detection failed — {e}"

    lines = ["# Source Drift Detection\n", result["summary"], ""]

    if result["changed_sources"]:
        lines.append(f"## Changed Sources ({len(result['changed_sources'])})\n")
        for src in result["changed_sources"]:
            lines.append(f"- {src}")
        lines.append("")

    # Cycle 4 item #14 — source-deleted category. Wiki pages whose source:
    # frontmatter points at a now-deleted raw file are the drift case most
    # likely to corrupt lint fidelity (the page still cites a source that
    # no longer exists). Surface them distinctly so operators can either
    # delete the page or re-point the source ref.
    if result.get("deleted_sources"):
        lines.append(f"## Deleted Sources ({len(result['deleted_sources'])})\n")
        for src in result["deleted_sources"]:
            lines.append(f"- {src} (source-deleted)")
        lines.append("")

    if result["affected_pages"]:
        lines.append(f"## Affected Wiki Pages ({len(result['affected_pages'])})\n")
        for ap in result["affected_pages"]:
            sources_str = ", ".join(ap.get("changed_sources") or [])
            lines.append(f"- **{ap['page_id']}** ← {sources_str}")
        lines.append("")
        lines.append("Run `kb_review_page(page_id)` on affected pages to check for stale content.")

    if result.get("deleted_affected_pages"):
        lines.append(
            f"## Pages Referencing Deleted Sources ({len(result['deleted_affected_pages'])})\n"
        )
        for ap in result["deleted_affected_pages"]:
            sources_str = ", ".join(ap.get("deleted_sources") or [])
            lines.append(f"- **{ap['page_id']}** ← deleted: {sources_str}")
        lines.append("")
        lines.append(
            "These pages cite sources that no longer exist. Consider deleting the pages "
            "or updating their source refs."
        )

    return "\n".join(lines)
