"""Health MCP tools — lint, evolve."""

import logging

from kb.mcp.app import mcp

logger = logging.getLogger(__name__)


@mcp.tool()
def kb_lint() -> str:
    """Run health checks on the wiki. Reports dead links, orphans, staleness, etc."""
    from kb.lint.runner import format_report, run_all_checks

    report = run_all_checks()
    result = format_report(report)

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
    from kb.evolve.analyzer import format_evolution_report, generate_evolution_report

    report = generate_evolution_report()
    result = format_evolution_report(report)

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
