"""Lint orchestrator — run all checks, produce report."""

import logging
from pathlib import Path

from kb.config import RAW_DIR, WIKI_DIR
from kb.graph.builder import build_graph, scan_wiki_pages
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

logger = logging.getLogger(__name__)


def run_all_checks(
    wiki_dir: Path | None = None,
    raw_dir: Path | None = None,
    fix: bool = False,
    *,
    verdicts_path: Path | None = None,
) -> dict:
    """Run all lint checks and produce a structured report.

    Args:
        wiki_dir: Path to wiki directory.
        raw_dir: Path to raw directory.
        fix: If True, auto-fix dead links by replacing with plain text.
        verdicts_path: Cycle 3 M18 — when set, verdict-summary reads from this
            path instead of the production ``VERDICTS_PATH``. Keyword-only so
            the public signature remains additive. Tests supplying a
            ``tmp_path`` can assert their own verdicts flow through without
            leaking production audit data into the lint report.

    Returns:
        dict with keys: checks_run, total_issues, issues (list), summary (by severity),
        fixes_applied (list of fix dicts, empty if fix=False).
    """
    wiki_dir = wiki_dir or WIKI_DIR
    raw_dir = raw_dir or RAW_DIR

    # Scan wiki pages once — shared by staleness, frontmatter, source_coverage, stub checks
    shared_pages = scan_wiki_pages(wiki_dir)

    # Build the wikilink graph once — shared by orphan and cycle checks
    shared_graph = build_graph(wiki_dir)

    all_issues = []

    # Run each check
    checks_run = []

    dead_links = check_dead_links(wiki_dir)
    all_issues.extend(dead_links)
    checks_run.append({"name": "dead_links", "issues": len(dead_links)})

    # Auto-fix dead links if requested; remove fixed issues from report
    fixes_applied: list[dict] = []
    if fix and dead_links:
        # Pass the already-computed broken list to avoid a second resolve_wikilinks() call
        # dead_link issues now use "page" key (standardized in Fix 6.14)
        broken = [
            {"source": i["page"], "target": i["target"]}
            for i in dead_links
            if i.get("check") == "dead_link"
        ]
        fixes_applied = fix_dead_links(wiki_dir, broken_links=broken)
        if fixes_applied:
            # Remove the dead link issues that were successfully fixed — both dicts use "page"
            fixed_pairs = {(f["page"], f["target"]) for f in fixes_applied}
            all_issues = [
                i
                for i in all_issues
                if not (
                    i.get("check") == "dead_link"
                    and (i.get("page"), i.get("target")) in fixed_pairs
                )
            ]

    if fix and fixes_applied:
        # Fix item 9: re-scan pages + rebuild graph so subsequent checks see post-fix state
        shared_pages = scan_wiki_pages(wiki_dir)
        shared_graph = build_graph(wiki_dir)

    orphans = check_orphan_pages(wiki_dir, graph=shared_graph)
    all_issues.extend(orphans)
    checks_run.append({"name": "orphan_pages", "issues": len(orphans)})

    stale = check_staleness(wiki_dir, pages=shared_pages)
    all_issues.extend(stale)
    checks_run.append({"name": "staleness", "issues": len(stale)})

    fm = check_frontmatter(wiki_dir, pages=shared_pages)
    all_issues.extend(fm)
    checks_run.append({"name": "frontmatter", "issues": len(fm)})

    coverage = check_source_coverage(wiki_dir, raw_dir, pages=shared_pages)
    all_issues.extend(coverage)
    checks_run.append({"name": "source_coverage", "issues": len(coverage)})

    cycles = check_cycles(wiki_dir, graph=shared_graph)
    all_issues.extend(cycles)
    checks_run.append({"name": "wikilink_cycles", "issues": len(cycles)})

    stubs = check_stub_pages(wiki_dir, pages=shared_pages)
    all_issues.extend(stubs)
    checks_run.append({"name": "stub_pages", "issues": len(stubs)})

    # Summarize by severity
    severity_counts = {"error": 0, "warning": 0, "info": 0}
    for issue in all_issues:
        sev = issue.get("severity", "info")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Include verdict audit trail summary (fail-safe).
    # Cycle 3 M18: pass verdicts_path so tests / alternate profiles don't bleed
    # production .data/lint_verdicts.json into the tmp-run report. The prior
    # code also aliased `verdict_summary = verdict_history` (dead duplicate)
    # — collapsed into a single local.
    try:
        verdict_history = get_verdict_summary(verdicts_path)
    except Exception as e:
        logger.warning("Failed to load verdict summary: %s", e)
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
