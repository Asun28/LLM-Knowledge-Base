"""Trust score computation, flagged pages, coverage gaps."""

from pathlib import Path

from kb.config import LOW_TRUST_THRESHOLD
from kb.feedback.store import load_feedback


def compute_trust_scores(path: Path | None = None) -> dict[str, dict]:
    """Compute trust scores for all pages with feedback.

    Returns:
        Dict mapping page_id to score dict {useful, wrong, incomplete, trust}.
    """
    data = load_feedback(path)
    return data.get("page_scores", {})


def get_flagged_pages(path: Path | None = None, threshold: float | None = None) -> list[str]:
    """Get page IDs with trust score below threshold.

    Args:
        path: Path to feedback JSON.
        threshold: Trust threshold (default: LOW_TRUST_THRESHOLD from config).

    Returns:
        Sorted list of page IDs below the threshold.
    """
    threshold = threshold if threshold is not None else LOW_TRUST_THRESHOLD
    scores = compute_trust_scores(path)
    return sorted(pid for pid, s in scores.items() if s.get("trust", 0.5) < threshold)


def get_coverage_gaps(path: Path | None = None) -> list[dict]:
    """Get questions where the answer was rated 'incomplete'.

    Returns:
        List of dicts with 'question' and 'notes' keys.
    """
    data = load_feedback(path)
    return [
        {"question": e["question"], "notes": e.get("notes", "")}
        for e in data.get("entries", [])
        if e.get("rating") == "incomplete"
    ]
