"""Lint orchestrator — run all checks, produce report."""

from pathlib import Path

from kb.config import RAW_DIR, WIKI_DIR
from kb.lint.checks import (
    check_cycles,
    check_dead_links,
    check_frontmatter,
    check_orphan_pages,
    check_source_coverage,
    check_staleness,
    check_stub_pages,
    fix_dead_links,
)
from kb.lint.verdicts import get_verdict_summary


def run_all_checks(
    wiki_dir: Path | None = None,
    raw_dir: Path | None = None,
    fix: bool = False,
) -> dict:
    """Run all lint checks and produce a structured report.

    Args:
        wiki_dir: Path to wiki directory.
        raw_dir: Path to raw directory.
        fix: If True, auto-fix dead links by replacing with plain text.

    Returns:
        dict with keys: checks_run, total_issues, issues (list), summary (by severity),
        fixes_applied (list of fix dicts, empty if fix=False).
    """
    wiki_dir = wiki_dir or WIKI_DIR
    raw_dir = raw_dir or RAW_DIR

    all_issues = []

    # Run each check
    checks_run = []

    dead_links = check_dead_links(wiki_dir)
    all_issues.extend(dead_links)
    checks_run.append({"name": "dead_links", "issues": len(dead_links)})

    # Auto-fix dead links if requested; remove fixed issues from report
    fixes_applied: list[dict] = []
    if fix and dead_links:
        fixes_applied = fix_dead_links(wiki_dir)
        if fixes_applied:
            # Remove the dead link issues that were successfully fixed
            fixed_pairs = {(f["page"], f["target"]) for f in fixes_applied}
            all_issues = [
                i
                for i in all_issues
                if not (
                    i.get("check") == "dead_link"
                    and (i.get("source"), i.get("target")) in fixed_pairs
                )
            ]

    orphans = check_orphan_pages(wiki_dir)
    all_issues.extend(orphans)
    checks_run.append({"name": "orphan_pages", "issues": len(orphans)})

    stale = check_staleness(wiki_dir)
    all_issues.extend(stale)
    checks_run.append({"name": "staleness", "issues": len(stale)})

    fm = check_frontmatter(wiki_dir)
    all_issues.extend(fm)
    checks_run.append({"name": "frontmatter", "issues": len(fm)})

    coverage = check_source_coverage(wiki_dir, raw_dir)
    all_issues.extend(coverage)
    checks_run.append({"name": "source_coverage", "issues": len(coverage)})

    cycles = check_cycles(wiki_dir)
    all_issues.extend(cycles)
    checks_run.append({"name": "wikilink_cycles", "issues": len(cycles)})

    stubs = check_stub_pages(wiki_dir)
    all_issues.extend(stubs)
    checks_run.append({"name": "stub_pages", "issues": len(stubs)})

    # Summarize by severity
    severity_counts = {"error": 0, "warning": 0, "info": 0}
    for issue in all_issues:
        sev = issue.get("severity", "info")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Include verdict audit trail summary (fail-safe)
    try:
        verdict_summary = get_verdict_summary()
        verdict_history = verdict_summary
    except Exception:
        verdict_history = None

    summary = severity_counts
    summary["verdict_history"] = verdict_history

    return {
        "checks_run": checks_run,
        "total_issues": len(all_issues),
        "issues": all_issues,
        "summary": summary,
        "fixes_applied": fixes_applied,
    }


def format_report(report: dict) -> str:
    """Format a lint report as readable text.

    Args:
        report: The report dict from run_all_checks().

    Returns:
        Formatted string report.
    """
    lines = ["# Wiki Lint Report\n"]

    # Summary
    summary = report["summary"]
    lines.append(f"**Total issues:** {report['total_issues']}")
    lines.append(f"  - Errors: {summary.get('error', 0)}")
    lines.append(f"  - Warnings: {summary.get('warning', 0)}")
    lines.append(f"  - Info: {summary.get('info', 0)}")
    lines.append("")

    # Checks run
    lines.append("## Checks Run\n")
    for check in report["checks_run"]:
        status = "PASS" if check["issues"] == 0 else f"{check['issues']} issues"
        lines.append(f"- {check['name']}: {status}")
    lines.append("")

    # Issues by severity
    if report["issues"]:
        for severity in ("error", "warning", "info"):
            sev_issues = [i for i in report["issues"] if i.get("severity") == severity]
            if sev_issues:
                lines.append(f"## {severity.upper()}S\n")
                for issue in sev_issues:
                    lines.append(f"- [{issue['check']}] {issue['message']}")
                lines.append("")
    else:
        lines.append("No issues found. Wiki is healthy!\n")

    # Fixes applied
    fixes = report.get("fixes_applied", [])
    if fixes:
        lines.append(f"\n## Auto-Fixes Applied ({len(fixes)})\n")
        for fix_item in fixes:
            lines.append(f"- {fix_item['message']}")
        lines.append("")

    # Verdict audit trail
    vh = report["summary"].get("verdict_history")
    if vh and vh["total"] > 0:
        lines.append("\n## Verdict Audit Trail\n")
        lines.append(f"**Total verdicts:** {vh['total']}")
        lines.append(
            f"  Pass: {vh['by_verdict']['pass']}, "
            f"Fail: {vh['by_verdict']['fail']}, "
            f"Warning: {vh['by_verdict']['warning']}"
        )
        if vh["pages_with_failures"]:
            lines.append(f"\n**Pages with failures:** {', '.join(vh['pages_with_failures'])}")

    return "\n".join(lines)
