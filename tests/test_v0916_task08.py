"""Phase 3.97 Task 08 — Feedback store fixes."""

import json
from pathlib import Path

import pytest


class TestLoadFeedbackNullTypes:
    """load_feedback must reject entries/page_scores with None values."""

    def test_null_entries_returns_default(self, tmp_path):
        fb_file = tmp_path / "feedback.json"
        fb_file.write_text(
            json.dumps({"entries": None, "page_scores": {}}),
            encoding="utf-8",
        )

        from kb.feedback.store import load_feedback

        result = load_feedback(fb_file)
        assert isinstance(result["entries"], list)
        assert result["entries"] == []

    def test_null_page_scores_returns_default(self, tmp_path):
        fb_file = tmp_path / "feedback.json"
        fb_file.write_text(
            json.dumps({"entries": [], "page_scores": None}),
            encoding="utf-8",
        )

        from kb.feedback.store import load_feedback

        result = load_feedback(fb_file)
        assert isinstance(result["page_scores"], dict)
        assert result["page_scores"] == {}

    def test_both_null_returns_default(self, tmp_path):
        fb_file = tmp_path / "feedback.json"
        fb_file.write_text(
            json.dumps({"entries": None, "page_scores": None}),
            encoding="utf-8",
        )

        from kb.feedback.store import load_feedback

        result = load_feedback(fb_file)
        assert result["entries"] == []
        assert result["page_scores"] == {}


class TestAddFeedbackEntryKeyError:
    """add_feedback_entry must handle missing keys in page_scores."""

    def test_missing_wrong_key_no_crash(self, tmp_path):
        fb_file = tmp_path / "feedback.json"
        fb_file.write_text(
            json.dumps(
                {
                    "entries": [],
                    "page_scores": {
                        "concepts/test": {"useful": 5, "trust": 0.7}
                        # missing "wrong" and "incomplete"
                    },
                }
            ),
            encoding="utf-8",
        )

        from kb.feedback.store import add_feedback_entry

        # Should not raise KeyError
        entry = add_feedback_entry(
            question="test question",
            rating="useful",
            cited_pages=["concepts/test"],
            path=fb_file,
        )
        assert entry["rating"] == "useful"


class TestFeedbackLockSleep:
    """_feedback_lock must sleep after evicting a stale lock."""

    def test_lock_eviction_sleeps(self, tmp_path):
        """After evicting a stale lock, the loop should sleep before retry."""
        import time

        fb_file = tmp_path / "feedback.json"
        fb_file.write_text(json.dumps({"entries": [], "page_scores": {}}), encoding="utf-8")

        lock_file = fb_file.with_suffix(".json.lock")
        lock_file.touch()

        from kb.feedback.store import _feedback_lock

        start = time.monotonic()
        with _feedback_lock(fb_file, timeout=0.3):
            elapsed = time.monotonic() - start
            # Should have waited at least a little (the sleep after eviction)
            assert elapsed >= 0.01


class TestGetCoverageGapsDedup:
    """get_coverage_gaps must deduplicate repeated questions."""

    def test_duplicate_questions_deduplicated(self, tmp_path):
        fb_file = tmp_path / "feedback.json"
        fb_file.write_text(
            json.dumps(
                {
                    "entries": [
                        {"question": "What is RAG?", "rating": "incomplete", "notes": "missing context"},
                        {"question": "What is RAG?", "rating": "incomplete", "notes": "still incomplete"},
                        {"question": "What is RAG?", "rating": "incomplete", "notes": "again"},
                        {"question": "What is LLM?", "rating": "incomplete", "notes": "need more"},
                    ],
                    "page_scores": {},
                }
            ),
            encoding="utf-8",
        )

        from kb.feedback.reliability import get_coverage_gaps

        gaps = get_coverage_gaps(fb_file)
        questions = [g["question"] for g in gaps]
        assert questions.count("What is RAG?") == 1
        assert questions.count("What is LLM?") == 1
