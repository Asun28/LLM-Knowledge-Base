"""Query feedback storage — load, save, add entries to JSON."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from kb.config import (
    FEEDBACK_PATH,
    MAX_CITED_PAGES,
    MAX_FEEDBACK_ENTRIES,
    MAX_NOTES_LEN,
    MAX_PAGE_ID_LEN,
    MAX_PAGE_SCORES,
    MAX_QUESTION_LEN,
)
from kb.utils.io import atomic_json_write, file_lock

logger = logging.getLogger(__name__)

# Delegate to the shared file_lock utility (PID-verified, cross-process safe)
_feedback_lock = file_lock


def _default_feedback() -> dict:
    """Return empty feedback structure."""
    return {"entries": [], "page_scores": {}}


def load_feedback(path: Path | None = None) -> dict:
    """Load feedback data from JSON file.

    Returns default structure if file is missing, corrupted, unreadable, or
    wrong shape.

    Q1 (Phase 4.5 R5 HIGH): widen except from `json.JSONDecodeError` only to
    also catch `OSError` (file locked by AV mid-write, EACCES on read,
    race with atomic rename on Windows) and `UnicodeDecodeError` (byte
    corruption). The design intent is corruption-recovery: always return a
    default and let the next write replace it, never raise through the MCP
    tool boundary.
    """
    path = path or FEEDBACK_PATH
    if not path.exists():
        return _default_feedback()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except PermissionError:
        # PR review round 1 (Codex M-NEW-3): propagate EACCES so callers
        # can't silently overwrite an unreadable file on the next write.
        # Permission-denied is an operator bug, not corruption; recovery
        # would destroy state the user might want to inspect first.
        raise
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        logger.warning("Feedback file unreadable, using defaults: %s", e)
        return _default_feedback()
    if (
        not isinstance(data, dict)
        or "entries" not in data
        or "page_scores" not in data
        or not isinstance(data["entries"], list)
        or not isinstance(data["page_scores"], dict)
    ):
        return _default_feedback()
    # Item 24 (cycle 2): one-shot schema migration — legacy entries written by
    # older code may be missing useful/wrong/incomplete/trust keys. Backfill
    # once at load so add_feedback_entry doesn't have to re-setdefault on
    # every write.
    _migrate_page_scores(data["page_scores"])
    return data


def _migrate_page_scores(page_scores: dict) -> None:
    """Backfill missing useful/wrong/incomplete/trust keys in-place."""
    _defaults = (("useful", 0), ("wrong", 0), ("incomplete", 0), ("trust", 0.5))
    for scores in page_scores.values():
        if not isinstance(scores, dict):
            continue
        for key, default in _defaults:
            if key not in scores:
                scores[key] = default


def save_feedback(data: dict, path: Path | None = None) -> None:
    """Save feedback data to JSON file (atomic write via temp file)."""
    path = path or FEEDBACK_PATH
    atomic_json_write(data, path)


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
        if (
            ".." in page_id
            or page_id.startswith("/")
            or page_id.startswith("\\")
            or os.path.isabs(page_id)
        ):
            raise ValueError(f"Invalid page ID: {page_id}")

    effective_path = path or FEEDBACK_PATH

    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "rating": rating,
        "cited_pages": cited_pages,
        "notes": notes,
    }

    with _feedback_lock(effective_path):
        data = load_feedback(effective_path)

        data["entries"].append(entry)
        # Retain only the most recent entries to prevent unbounded growth
        if len(data["entries"]) > MAX_FEEDBACK_ENTRIES:
            logger.warning(
                "Feedback store at capacity (%d entries), evicting oldest", MAX_FEEDBACK_ENTRIES
            )
            data["entries"] = data["entries"][-MAX_FEEDBACK_ENTRIES:]

        # Update page scores with Bayesian smoothing
        # "wrong" is weighted 2x because incorrect information is worse than incomplete
        # Deduplicate cited_pages to prevent inflated trust scores
        unique_cited = list(dict.fromkeys(cited_pages))
        for page_id in unique_cited:
            if page_id not in data["page_scores"]:
                data["page_scores"][page_id] = {
                    "useful": 0,
                    "wrong": 0,
                    "incomplete": 0,
                    "trust": 0.5,
                }
            scores = data["page_scores"][page_id]
            # Item 24 (cycle 2): per-write `setdefault` loop removed — migration
            # now runs once in load_feedback. Legacy files written before the
            # migration are normalized on next load; on cold start the create
            # path above inserts all four keys.
            scores[rating] += 1
            weighted_negative = 2 * scores["wrong"] + scores["incomplete"]
            scores["trust"] = round(
                (scores["useful"] + 1) / (scores["useful"] + weighted_negative + 2), 4
            )
            # Phase 4.5 HIGH D4: track last-touched for timestamp-based eviction
            scores["last_touched"] = datetime.now().isoformat(timespec="seconds")

        # Cap page_scores dict to prevent unbounded growth
        if len(data["page_scores"]) > MAX_PAGE_SCORES:
            # Phase 4.5 HIGH D4: evict by last-touched timestamp (oldest first).
            # Previous activity-count eviction allowed attackers to flood useful
            # ratings for sacrificial page IDs, aging out genuinely flagged pages.
            sorted_pages = sorted(
                data["page_scores"].items(),
                key=lambda x: x[1].get("last_touched", ""),
            )
            # Keep newest entries (highest last_touched values)
            data["page_scores"] = dict(sorted_pages[-MAX_PAGE_SCORES:])

        save_feedback(data, effective_path)

    return entry
