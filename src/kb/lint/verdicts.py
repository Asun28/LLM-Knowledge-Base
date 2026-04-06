"""Persistent lint and review verdict storage."""

import json
from datetime import datetime
from pathlib import Path

from kb.config import PROJECT_ROOT

VERDICTS_PATH = PROJECT_ROOT / ".data" / "lint_verdicts.json"


def load_verdicts(path: Path | None = None) -> list[dict]:
    """Load all stored verdicts from JSON file."""
    path = path or VERDICTS_PATH
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def save_verdicts(verdicts: list[dict], path: Path | None = None) -> None:
    """Save verdicts to JSON file."""
    path = path or VERDICTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(verdicts, indent=2), encoding="utf-8")


def add_verdict(
    page_id: str,
    verdict_type: str,
    verdict: str,
    issues: list[dict] | None = None,
    notes: str = "",
    path: Path | None = None,
) -> dict:
    """Record a lint or review verdict for a page.

    Args:
        page_id: Wiki page ID (e.g., 'concepts/rag').
        verdict_type: Type of check ('fidelity', 'consistency', 'completeness', 'review').
        verdict: Result ('pass', 'fail', 'warning').
        issues: List of issue dicts with severity/description.
        notes: Free-text notes.
        path: Path to verdicts JSON file.

    Returns:
        The created verdict dict.

    Raises:
        ValueError: If verdict is not valid.
    """
    if verdict not in ("pass", "fail", "warning"):
        raise ValueError(f"Invalid verdict: {verdict}. Must be 'pass', 'fail', or 'warning'")
    if verdict_type not in ("fidelity", "consistency", "completeness", "review"):
        raise ValueError(
            f"Invalid verdict_type: {verdict_type}. "
            "Must be 'fidelity', 'consistency', 'completeness', or 'review'"
        )

    verdicts = load_verdicts(path)
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "page_id": page_id,
        "verdict_type": verdict_type,
        "verdict": verdict,
        "issues": issues or [],
        "notes": notes,
    }
    verdicts.append(entry)
    save_verdicts(verdicts, path)
    return entry


def get_page_verdicts(page_id: str, path: Path | None = None) -> list[dict]:
    """Get all verdicts for a specific page, most recent first."""
    verdicts = load_verdicts(path)
    return sorted(
        [v for v in verdicts if v["page_id"] == page_id],
        key=lambda v: v["timestamp"],
        reverse=True,
    )


def get_verdict_summary(path: Path | None = None) -> dict:
    """Get summary statistics of all verdicts.

    Returns:
        Dict with total, by_verdict (pass/fail/warning counts),
        by_type (fidelity/consistency/completeness/review counts),
        pages_with_failures (list of page IDs that have at least one 'fail').
    """
    verdicts = load_verdicts(path)
    summary = {
        "total": len(verdicts),
        "by_verdict": {"pass": 0, "fail": 0, "warning": 0},
        "by_type": {"fidelity": 0, "consistency": 0, "completeness": 0, "review": 0},
        "pages_with_failures": [],
    }
    failed_pages = set()
    for v in verdicts:
        vrd = v.get("verdict", "")
        vtype = v.get("verdict_type", "")
        if vrd in summary["by_verdict"]:
            summary["by_verdict"][vrd] += 1
        if vtype in summary["by_type"]:
            summary["by_type"][vtype] += 1
        if vrd == "fail":
            failed_pages.add(v["page_id"])
    summary["pages_with_failures"] = sorted(failed_pages)
    return summary
