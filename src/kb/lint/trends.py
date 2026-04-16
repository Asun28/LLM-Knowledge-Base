"""Verdict trend analysis — track quality improvement over time."""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from datetime import date as _date
from datetime import time as _time
from pathlib import Path

from kb.config import VERDICT_TREND_THRESHOLD
from kb.lint.verdicts import load_verdicts


def _parse_timestamp(ts: str) -> datetime:
    """Parse ISO-8601 timestamp.

    Phase 4.5 HIGH L4: always returns UTC-aware datetimes. Naive datetimes are
    assumed UTC. Item 22 (cycle 2): the vestigial date-only fallback was
    removed — project pins `python_requires>=3.12` so `fromisoformat` parses
    both date and datetime strings natively, and tests exercising date-only
    inputs still succeed through the same call.
    """
    ts = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    # Ensure result is always aware (assume naive = UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt

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
    # Item 21 (cycle 2): accept either a path OR a list of verdict dicts.
    # Tests/direct callers can now pass verdicts without round-tripping to disk.
    verdicts = path if isinstance(path, list) else load_verdicts(path)
    if not verdicts:
        return {
            "total": 0,
            "overall": {"pass": 0, "fail": 0, "warning": 0},
            "periods": [],
            "trend": "stable",
            "parse_failures": 0,
        }

    # Overall counts and period grouping in a single pass
    overall = {"pass": 0, "fail": 0, "warning": 0}
    period_buckets: dict[str, dict] = defaultdict(
        lambda: {"pass": 0, "fail": 0, "warning": 0, "total": 0}
    )
    parse_failures = 0

    for v in verdicts:
        vrd = v.get("verdict", "")

        ts_str = v.get("timestamp", "")
        try:
            ts = _parse_timestamp(ts_str)
        except (ValueError, TypeError):
            # Phase 4.5 HIGH L5: exclude parse failures from BOTH overall
            # and period_buckets (previously counted in overall but skipped
            # in periods, causing sum mismatch).
            # Item 21 (cycle 2): count them explicitly so callers can surface
            # "N verdicts skipped due to malformed timestamps" instead of
            # leaving a silent gap between `total` and `sum(periods)`.
            parse_failures += 1
            continue

        # Count in overall only after timestamp parse succeeds
        if vrd in overall:
            overall[vrd] += 1

        # Compute period key (start of the week)
        period_start = ts - timedelta(days=ts.weekday())
        period_key = period_start.strftime("%Y-%m-%d")

        if vrd in ("pass", "fail", "warning"):
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
        recent_period = sorted_periods[-1]
        previous_period = sorted_periods[-2]
        # Require minimum 3 verdicts in BOTH periods for a meaningful trend comparison
        if recent_period["total"] >= 3 and previous_period["total"] >= 3:
            recent = recent_period["pass_rate"]
            previous = previous_period["pass_rate"]
            if recent > previous + VERDICT_TREND_THRESHOLD:
                trend = "improving"
            elif recent < previous - VERDICT_TREND_THRESHOLD:
                trend = "declining"

    return {
        "total": len(verdicts),
        "overall": overall,
        "periods": sorted_periods,
        "trend": trend,
        "parse_failures": parse_failures,
    }


def format_verdict_trends(trends: dict) -> str:
    """Format verdict trends as readable markdown text."""
    if trends["total"] == 0:
        return "# Verdict Trends\n\nNo verdict history yet."

    lines = ["# Verdict Trends\n"]

    # Overall
    o = trends["overall"]
    total = trends["total"]
    pass_rate = o["pass"] / sum(o.values()) if sum(o.values()) > 0 else 0.0
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
