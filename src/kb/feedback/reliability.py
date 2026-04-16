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


def _compute_trust_from_counts(score: dict) -> float:
    """Bayesian-smoothed trust from raw counts. Mirrors add_feedback_entry.

    Q2 (Phase 4.5 R4 HIGH): when a legacy or partially-written score entry
    lacks ``trust``, recompute it from useful/wrong/incomplete instead of
    defaulting to 0.5 (neutral). Wrong is weighted 2× — matches the
    canonical write-path formula in add_feedback_entry.
    """
    useful = int(score.get("useful", 0) or 0)
    wrong = int(score.get("wrong", 0) or 0)
    incomplete = int(score.get("incomplete", 0) or 0)
    return (useful + 1) / (useful + 2 * wrong + incomplete + 2)


def get_flagged_pages(path: Path | None = None, threshold: float | None = None) -> list[str]:
    """Get page IDs with trust score at or below threshold.

    Args:
        path: Path to feedback JSON.
        threshold: Trust threshold (default: LOW_TRUST_THRESHOLD from config).

    Returns:
        Sorted list of page IDs at or below the threshold.

    Q2 (Phase 4.5 R4 HIGH): entries missing the ``trust`` key are no longer
    silently treated as neutral (0.5); trust is recomputed from the raw
    counts so truly low-trust pages still surface even if a write was
    downgraded or a legacy entry is present.
    """
    threshold = threshold if threshold is not None else LOW_TRUST_THRESHOLD
    scores = compute_trust_scores(path)
    flagged: list[str] = []
    for pid, s in scores.items():
        trust = s.get("trust")
        if trust is None:
            trust = _compute_trust_from_counts(s)
        if trust <= threshold:
            flagged.append(pid)
    return sorted(flagged)


def get_coverage_gaps(path: Path | None = None) -> list[dict]:
    """Get questions where the answer was rated 'incomplete'.

    Item 25 (cycle 2): deduplicates by question text, keeping the entry with
    the LONGEST notes (ties broken by newest timestamp). Prior behaviour kept
    the first occurrence; because feedback is stored oldest-first, later,
    more-specific notes were silently suppressed and evolve reports
    accumulated stale/vague notes over time.

    Returns:
        List of dicts with 'question' and 'notes' keys.
    """
    data = load_feedback(path)
    best_by_question: dict[str, dict] = {}
    for e in data.get("entries", []):
        if e.get("rating") != "incomplete":
            continue
        q = e.get("question")
        if not q:
            continue
        notes = e.get("notes", "") or ""
        ts = e.get("timestamp", "")
        current = best_by_question.get(q)
        if current is None:
            best_by_question[q] = {"question": q, "notes": notes, "timestamp": ts}
            continue
        # Keep the entry with richer notes; break ties by newer timestamp.
        if len(notes) > len(current["notes"]) or (
            len(notes) == len(current["notes"]) and ts > current["timestamp"]
        ):
            best_by_question[q] = {"question": q, "notes": notes, "timestamp": ts}
    return [{"question": v["question"], "notes": v["notes"]} for v in best_by_question.values()]
