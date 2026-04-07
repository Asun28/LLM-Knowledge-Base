"""Health MCP tools — lint, evolve."""

import logging

from kb.mcp.app import mcp

logger = logging.getLogger(__name__)


@mcp.tool()
def kb_lint() -> str:
    """Run health checks on the wiki. Reports dead links, orphans, staleness, etc."""
    try:
        from kb.lint.runner import format_report, run_all_checks

        report = run_all_checks()
        result = format_report(report)
    except Exception as e:
        logger.error("Error running lint checks: %s", e)
        return f"Error running lint checks: {e}"

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
        logger.debug("Failed to load feedback data for lint: %s", e)

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
        return f"Error running evolution analysis: {e}"

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
        logger.debug("Failed to load feedback data for evolve: %s", e)

    return result


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
        return f"Error computing verdict trends: {e}"


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
        return f"Error detecting source drift: {e}"

    lines = ["# Source Drift Detection\n", result["summary"], ""]

    if result["changed_sources"]:
        lines.append(f"## Changed Sources ({len(result['changed_sources'])})\n")
        for src in result["changed_sources"]:
            lines.append(f"- {src}")
        lines.append("")

    if result["affected_pages"]:
        lines.append(f"## Affected Wiki Pages ({len(result['affected_pages'])})\n")
        for ap in result["affected_pages"]:
            sources_str = ", ".join(ap["changed_sources"])
            lines.append(f"- **{ap['page_id']}** ← {sources_str}")
        lines.append("")
        lines.append("Run `kb_review_page(page_id)` on affected pages to check for stale content.")

    return "\n".join(lines)
