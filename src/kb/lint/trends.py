"""Verdict trend analysis — track quality improvement over time."""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from kb.lint.verdicts import load_verdicts

logger = logging.getLogger(__name__)


def compute_verdict_trends(path: Path | None = None) -> dict:
    """Analyze verdict history to identify quality trends.

    Groups verdicts into weekly periods and computes pass/fail/warning
    rates. Determines overall trend direction (improving/stable/declining).

    Args:
        path: Path to verdicts JSON file. Uses default if None.

    Returns:
        dict with keys: total, overall (pass/fail/warning counts),
        periods (list of period dicts), trend (improving/stable/declining).
    """
    verdicts = load_verdicts(path)
    if not verdicts:
        return {
            "total": 0,
            "overall": {"pass": 0, "fail": 0, "warning": 0},
            "periods": [],
            "trend": "stable",
        }

    # Overall counts and period grouping in a single pass
    overall = {"pass": 0, "fail": 0, "warning": 0}
    period_buckets: dict[str, dict] = defaultdict(
        lambda: {"pass": 0, "fail": 0, "warning": 0, "total": 0}
    )

    for v in verdicts:
        vrd = v.get("verdict", "")
        if vrd in overall:
            overall[vrd] += 1

        ts_str = v.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            continue

        # Compute period key (start of the week)
        period_start = ts - timedelta(days=ts.weekday())
        period_key = period_start.strftime("%Y-%m-%d")

        if vrd in period_buckets[period_key]:
            period_buckets[period_key][vrd] += 1
        period_buckets[period_key]["total"] += 1

    # Sort periods chronologically
    sorted_periods = []
    for key in sorted(period_buckets.keys()):
        bucket = period_buckets[key]
        total = bucket["total"]
        pass_rate = bucket["pass"] / total if total > 0 else 0.0
        sorted_periods.append(
            {
                "period": key,
                "pass": bucket["pass"],
                "fail": bucket["fail"],
                "warning": bucket["warning"],
                "total": total,
                "pass_rate": round(pass_rate, 2),
            }
        )

    # Determine trend from last 2 periods
    trend = "stable"
    if len(sorted_periods) >= 2:
        recent = sorted_periods[-1]["pass_rate"]
        previous = sorted_periods[-2]["pass_rate"]
        if recent > previous + 0.1:
            trend = "improving"
        elif recent < previous - 0.1:
            trend = "declining"

    return {
        "total": len(verdicts),
        "overall": overall,
        "periods": sorted_periods,
        "trend": trend,
    }


def format_verdict_trends(trends: dict) -> str:
    """Format verdict trends as readable markdown text."""
    if trends["total"] == 0:
        return "# Verdict Trends\n\nNo verdict history yet."

    lines = ["# Verdict Trends\n"]

    # Overall
    o = trends["overall"]
    total = trends["total"]
    pass_rate = o["pass"] / total if total > 0 else 0.0
    lines.append(f"**Total verdicts:** {total}")
    lines.append(f"**Overall pass rate:** {pass_rate:.0%}")
    lines.append(f"  Pass: {o['pass']} | Fail: {o['fail']} | Warning: {o['warning']}")
    lines.append(f"**Trend:** {trends['trend']}")
    lines.append("")

    # Period breakdown
    if trends["periods"]:
        lines.append("## Weekly Breakdown\n")
        lines.append("| Period | Pass | Fail | Warn | Total | Pass Rate |")
        lines.append("|--------|------|------|------|-------|-----------|")
        for p in trends["periods"]:
            lines.append(
                f"| {p['period']} | {p['pass']} | {p['fail']} | "
                f"{p['warning']} | {p['total']} | {p['pass_rate']:.0%} |"
            )
        lines.append("")

    return "\n".join(lines)
