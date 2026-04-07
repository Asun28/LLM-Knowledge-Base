"""Query feedback storage — load, save, add entries to JSON."""

import json
from datetime import datetime
from pathlib import Path

from kb.config import FEEDBACK_PATH

MAX_FEEDBACK_ENTRIES = 10_000
MAX_QUESTION_LEN = 2000
MAX_NOTES_LEN = 2000
MAX_PAGE_ID_LEN = 200
MAX_CITED_PAGES = 50


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
        except json.JSONDecodeError:
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

    # Input length validation
    if len(question) > MAX_QUESTION_LEN:
        raise ValueError(f"Question too long ({len(question)} chars). Maximum: {MAX_QUESTION_LEN}")
    if len(notes) > MAX_NOTES_LEN:
        raise ValueError(f"Notes too long ({len(notes)} chars). Maximum: {MAX_NOTES_LEN}")
    if len(cited_pages) > MAX_CITED_PAGES:
        raise ValueError(f"Too many cited pages ({len(cited_pages)}). Maximum: {MAX_CITED_PAGES}")
    for page_id in cited_pages:
        if len(page_id) > MAX_PAGE_ID_LEN:
            raise ValueError(f"Page ID too long: {page_id[:50]}...")
        if ".." in page_id or page_id.startswith("/") or page_id.startswith("\\"):
            raise ValueError(f"Invalid page ID: {page_id}")

    data = load_feedback(path)

    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "rating": rating,
        "cited_pages": cited_pages,
        "notes": notes,
    }
    data["entries"].append(entry)
    # Retain only the most recent entries to prevent unbounded growth
    if len(data["entries"]) > MAX_FEEDBACK_ENTRIES:
        data["entries"] = data["entries"][-MAX_FEEDBACK_ENTRIES:]

    # Update page scores with Bayesian smoothing
    # "wrong" is weighted 2x because incorrect information is worse than incomplete
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
        weighted_negative = 2 * scores["wrong"] + scores["incomplete"]
        scores["trust"] = round(
            (scores["useful"] + 1) / (scores["useful"] + weighted_negative + 2), 4
        )

    save_feedback(data, path)
    return entry
