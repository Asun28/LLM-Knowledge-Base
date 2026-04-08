"""Persistent lint and review verdict storage."""

import json
import logging
from datetime import datetime
from pathlib import Path

from kb.config import MAX_VERDICTS, VERDICTS_PATH

logger = logging.getLogger(__name__)

VALID_SEVERITIES = ("error", "warning", "info")
MAX_NOTES_LEN = 2000


def load_verdicts(path: Path | None = None) -> list[dict]:
    """Load all stored verdicts from JSON file."""
    path = path or VERDICTS_PATH
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.warning("Corrupt verdicts file %s, returning empty: %s", path, e)
            return []
        if not isinstance(data, list):
            return []
        return data
    return []


def save_verdicts(verdicts: list[dict], path: Path | None = None) -> None:
    """Save verdicts to JSON file (atomic write via temp file)."""
    from kb.utils.io import atomic_json_write

    path = path or VERDICTS_PATH
    atomic_json_write(verdicts, path)


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

    # Validate page_id against path traversal
    if ".." in page_id or page_id.startswith("/") or page_id.startswith("\\"):
        raise ValueError(f"Invalid page_id: {page_id!r}. Must not contain '..' or start with '/'.")

    # Cap notes length (consistent with feedback store MAX_NOTES_LEN)
    if len(notes) > MAX_NOTES_LEN:
        raise ValueError(f"Notes too long ({len(notes)} chars). Maximum: {MAX_NOTES_LEN}")

    if issues:
        for issue in issues:
            if not isinstance(issue, dict):
                raise ValueError(f"Each issue must be a dict, got {type(issue).__name__}")
            severity = issue.get("severity", "")
            if severity and severity not in VALID_SEVERITIES:
                raise ValueError(
                    f"Invalid issue severity '{severity}'. "
                    f"Must be one of: {', '.join(VALID_SEVERITIES)}"
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
    # Retain only the most recent verdicts to prevent unbounded growth
    if len(verdicts) > MAX_VERDICTS:
        verdicts = verdicts[-MAX_VERDICTS:]
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
