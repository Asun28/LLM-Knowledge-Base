"""Query feedback storage — load, save, add entries to JSON."""

import json
from datetime import datetime
from pathlib import Path

from kb.config import FEEDBACK_PATH


def _default_feedback() -> dict:
    """Return empty feedback structure."""
    return {"entries": [], "page_scores": {}}


def load_feedback(path: Path | None = None) -> dict:
    """Load feedback data from JSON file.

    Returns default structure if file is missing or corrupted.
    """
    path = path or FEEDBACK_PATH
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            return _default_feedback()
    return _default_feedback()


def save_feedback(data: dict, path: Path | None = None) -> None:
    """Save feedback data to JSON file."""
    path = path or FEEDBACK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def add_feedback_entry(
    question: str,
    rating: str,
    cited_pages: list[str],
    notes: str = "",
    path: Path | None = None,
) -> dict:
    """Add a feedback entry and update page trust scores.

    Args:
        question: The query that was asked.
        rating: One of 'useful', 'wrong', 'incomplete'.
        cited_pages: Page IDs cited in the answer.
        notes: Optional notes about what was wrong/missing.
        path: Path to feedback JSON file.

    Returns:
        The created entry dict.

    Raises:
        ValueError: If rating is not valid.
    """
    if rating not in ("useful", "wrong", "incomplete"):
        raise ValueError(f"Invalid rating: {rating}. Must be 'useful', 'wrong', or 'incomplete'")

    data = load_feedback(path)

    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "rating": rating,
        "cited_pages": cited_pages,
        "notes": notes,
    }
    data["entries"].append(entry)

    # Update page scores with Bayesian smoothing
    for page_id in cited_pages:
        if page_id not in data["page_scores"]:
            data["page_scores"][page_id] = {
                "useful": 0,
                "wrong": 0,
                "incomplete": 0,
                "trust": 0.5,
            }
        scores = data["page_scores"][page_id]
        scores[rating] += 1
        total = scores["useful"] + scores["wrong"] + scores["incomplete"]
        scores["trust"] = round((scores["useful"] + 1) / (total + 2), 4)

    save_feedback(data, path)
    return entry
