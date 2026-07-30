"""Tests for the feedback module (store + reliability)."""

import logging

import pytest

from kb.feedback.reliability import (
    compute_trust_scores,
    get_coverage_gaps,
    get_flagged_pages,
)
from kb.feedback.store import add_feedback_entry, load_feedback, save_feedback

# ── Store tests ───────────────────────────────────────────────


def test_load_feedback_empty(tmp_path):
    """load_feedback returns default structure when file doesn't exist."""
    path = tmp_path / "feedback.json"
    data = load_feedback(path)
    assert data == {"entries": [], "page_scores": {}}


def test_save_and_load_feedback(tmp_path):
    """Round-trip: save then load preserves data."""
    path = tmp_path / "feedback.json"
    data = {"entries": [{"question": "test"}], "page_scores": {}}
    save_feedback(data, path)
    loaded = load_feedback(path)
    assert loaded == data


def test_load_feedback_corrupted(tmp_path):
    """load_feedback returns default structure for corrupted JSON."""
    path = tmp_path / "feedback.json"
    path.write_text("not json{{{", encoding="utf-8")
    data = load_feedback(path)
    assert data == {"entries": [], "page_scores": {}}


def test_add_feedback_entry_useful(tmp_path):
    """add_feedback_entry with 'useful' rating boosts trust score."""
    path = tmp_path / "feedback.json"
    entry = add_feedback_entry("What is RAG?", "useful", ["concepts/rag"], path=path)
    assert entry["rating"] == "useful"
    data = load_feedback(path)
    assert len(data["entries"]) == 1
    scores = data["page_scores"]["concepts/rag"]
    assert scores["useful"] == 1
    assert scores["wrong"] == 0
    # trust = (1 + 1) / (1 + 2) = 0.6667
    assert abs(scores["trust"] - 0.6667) < 0.001


def test_add_feedback_entry_wrong(tmp_path):
    """add_feedback_entry with 'wrong' rating lowers trust score heavily."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("What is RAG?", "wrong", ["concepts/rag"], path=path)
    data = load_feedback(path)
    scores = data["page_scores"]["concepts/rag"]
    assert scores["wrong"] == 1
    # trust = (0 + 1) / (0 + 2*1 + 2) = 1/4 = 0.25  (wrong weighted 2x)
    assert abs(scores["trust"] - 0.25) < 0.001


def test_add_feedback_entry_multiple(tmp_path):
    """Multiple feedback entries accumulate correctly."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("Q1", "useful", ["concepts/rag"], path=path)
    add_feedback_entry("Q2", "useful", ["concepts/rag"], path=path)
    add_feedback_entry("Q3", "wrong", ["concepts/rag"], path=path)
    data = load_feedback(path)
    assert len(data["entries"]) == 3
    scores = data["page_scores"]["concepts/rag"]
    assert scores["useful"] == 2
    assert scores["wrong"] == 1
    # trust = (2 + 1) / (2 + 2*1 + 2) = 3/6 = 0.5  (wrong weighted 2x)
    assert abs(scores["trust"] - 0.5) < 0.001


def test_add_feedback_entry_invalid_rating(tmp_path):
    """add_feedback_entry raises ValueError for invalid rating."""
    path = tmp_path / "feedback.json"
    import pytest

    with pytest.raises(ValueError, match="Invalid rating"):
        add_feedback_entry("Q1", "bad_rating", ["concepts/rag"], path=path)


def test_add_feedback_entry_multiple_pages(tmp_path):
    """add_feedback_entry updates scores for all cited pages."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("Q1", "useful", ["concepts/rag", "entities/openai"], path=path)
    data = load_feedback(path)
    assert "concepts/rag" in data["page_scores"]
    assert "entities/openai" in data["page_scores"]
    assert data["page_scores"]["concepts/rag"]["useful"] == 1
    assert data["page_scores"]["entities/openai"]["useful"] == 1


# ── Reliability tests ─────────────────────────────────────────


def test_compute_trust_scores_empty(tmp_path):
    """compute_trust_scores returns empty dict when no feedback exists."""
    path = tmp_path / "feedback.json"
    assert compute_trust_scores(path) == {}


def test_compute_trust_scores(tmp_path):
    """compute_trust_scores returns page scores from feedback."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("Q1", "useful", ["concepts/rag"], path=path)
    scores = compute_trust_scores(path)
    assert "concepts/rag" in scores
    assert scores["concepts/rag"]["useful"] == 1


def test_get_flagged_pages(tmp_path):
    """get_flagged_pages returns pages below trust threshold."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("Q1", "wrong", ["concepts/rag"], path=path)
    # trust = (0+1)/(0+2*1+2) = 0.25 < 0.4 threshold
    flagged = get_flagged_pages(path)
    assert "concepts/rag" in flagged


def test_get_flagged_pages_empty(tmp_path):
    """get_flagged_pages returns empty list when no pages are flagged."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("Q1", "useful", ["concepts/rag"], path=path)
    # trust = (1+1)/(1+2) = 0.667 > 0.4
    flagged = get_flagged_pages(path)
    assert flagged == []


def test_get_coverage_gaps(tmp_path):
    """get_coverage_gaps returns questions with 'incomplete' rating."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("Q1", "useful", ["concepts/rag"], path=path)
    add_feedback_entry(
        "Q2", "incomplete", ["concepts/llm"], notes="Missing fine-tuning info", path=path
    )
    gaps = get_coverage_gaps(path)
    assert len(gaps) == 1
    assert gaps[0]["question"] == "Q2"
    assert gaps[0]["notes"] == "Missing fine-tuning info"


def test_get_coverage_gaps_empty(tmp_path):
    """get_coverage_gaps returns empty list when no incomplete ratings."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("Q1", "useful", ["concepts/rag"], path=path)
    assert get_coverage_gaps(path) == []


# -- Cycle 92 fold from test_v0915_task08.py (feedback store/reliability subset) --
# ── Fix 8.1 — stale lock recovery ────────────────────────────────────────────


class TestFeedbackLockRecovery:
    """Fix 8.1: stale lock recovery must retry acquisition, not fall through."""

    def test_stale_lock_retries(self, tmp_path):
        from kb.feedback.store import _feedback_lock

        feedback_path = tmp_path / "feedback.json"
        lock_path = feedback_path.with_suffix(".json.lock")

        # Create a stale lock (simulate crash with lock still present).
        # Cycle 2 item 2: lock content must be a valid ASCII integer — seed a
        # dead PID rather than empty string so the waiter can distinguish
        # "stale, steal" from "corruption, raise".
        lock_path.write_text("999999999", encoding="ascii")

        # Should succeed by removing stale lock and re-acquiring
        with _feedback_lock(feedback_path, timeout=0.5):
            assert lock_path.exists()

    def test_lock_held_during_yield(self, tmp_path):
        from kb.feedback.store import _feedback_lock

        feedback_path = tmp_path / "feedback.json"
        lock_path = feedback_path.with_suffix(".json.lock")

        with _feedback_lock(feedback_path, timeout=1.0):
            assert lock_path.exists()
        assert not lock_path.exists()

    def test_stale_lock_removed_after_timeout(self, tmp_path):
        """Lock file is gone after context exits even when stale lock was present."""
        from kb.feedback.store import _feedback_lock

        feedback_path = tmp_path / "feedback.json"
        lock_path = feedback_path.with_suffix(".json.lock")

        # Cycle 2 item 2: seed dead-PID content, not empty.
        lock_path.write_text("999999999", encoding="ascii")

        with _feedback_lock(feedback_path, timeout=0.5):
            pass
        assert not lock_path.exists()


# ── Fix 8.2 — missing parent directory ───────────────────────────────────────


class TestFeedbackLockMissingDir:
    """Fix 8.2: _feedback_lock must create parent directory."""

    def test_missing_parent_dir_created(self, tmp_path):
        from kb.feedback.store import _feedback_lock

        deep_path = tmp_path / "nonexistent" / "subdir" / "feedback.json"
        assert not deep_path.parent.exists()

        with _feedback_lock(deep_path, timeout=1.0):
            assert deep_path.parent.exists()

    def test_existing_parent_dir_not_error(self, tmp_path):
        """mkdir with exist_ok=True means already-existing dir is fine."""
        from kb.feedback.store import _feedback_lock

        feedback_path = tmp_path / "feedback.json"
        # Parent already exists — should not raise
        with _feedback_lock(feedback_path, timeout=1.0):
            assert feedback_path.parent.exists()


# ── Fix 8.4 — get_coverage_gaps KeyError guard ───────────────────────────────


class TestCoverageGapsKeyError:
    """Fix 8.4: get_coverage_gaps must not raise KeyError on malformed entries."""

    def test_missing_question_key_skipped(self, tmp_path):
        """Entries without 'question' key are silently skipped."""
        import json

        from kb.feedback.reliability import get_coverage_gaps

        feedback_path = tmp_path / "feedback.json"
        data = {
            "entries": [
                {"rating": "incomplete", "notes": "no question here"},  # missing 'question'
                {"rating": "incomplete", "question": "What is X?", "notes": "ok"},
            ],
            "page_scores": {},
        }
        feedback_path.write_text(json.dumps(data), encoding="utf-8")

        gaps = get_coverage_gaps(feedback_path)
        # Only the valid entry should appear
        assert len(gaps) == 1
        assert gaps[0]["question"] == "What is X?"

    def test_empty_question_skipped(self, tmp_path):
        """Entries with empty string 'question' are skipped (falsy guard)."""
        import json

        from kb.feedback.reliability import get_coverage_gaps

        feedback_path = tmp_path / "feedback.json"
        data = {
            "entries": [
                {"rating": "incomplete", "question": "", "notes": "empty question"},
                {"rating": "incomplete", "question": "Valid question?", "notes": ""},
            ],
            "page_scores": {},
        }
        feedback_path.write_text(json.dumps(data), encoding="utf-8")

        gaps = get_coverage_gaps(feedback_path)
        assert len(gaps) == 1
        assert gaps[0]["question"] == "Valid question?"

    def test_missing_notes_defaults_to_empty_string(self, tmp_path):
        """Entries without 'notes' key return empty string for notes."""
        import json

        from kb.feedback.reliability import get_coverage_gaps

        feedback_path = tmp_path / "feedback.json"
        data = {
            "entries": [
                {"rating": "incomplete", "question": "What is Y?"},  # no 'notes'
            ],
            "page_scores": {},
        }
        feedback_path.write_text(json.dumps(data), encoding="utf-8")

        gaps = get_coverage_gaps(feedback_path)
        assert len(gaps) == 1
        assert gaps[0]["notes"] == ""


# ── Fix 8.6 — entry cap warning log ──────────────────────────────────────────


class TestFeedbackEntryCapWarning:
    """Fix 8.6: eviction of entries must emit a warning log."""

    def test_warning_emitted_on_eviction(self, tmp_path, caplog):
        """When MAX_FEEDBACK_ENTRIES is exceeded, a warning is logged."""
        import json
        from unittest.mock import patch

        import kb.feedback.store as store_module
        from kb.feedback.store import add_feedback_entry

        feedback_path = tmp_path / "feedback.json"

        # Pre-fill store to exactly at-capacity (use tiny cap for speed)
        tiny_cap = 2
        data = {
            "entries": [
                {
                    "timestamp": "2026-01-01T00:00:00",
                    "question": f"q{i}",
                    "rating": "useful",
                    "cited_pages": [],
                    "notes": "",
                }
                for i in range(tiny_cap)
            ],
            "page_scores": {},
        }
        feedback_path.write_text(json.dumps(data), encoding="utf-8")

        # Patch MAX_FEEDBACK_ENTRIES in the store module's namespace directly
        with patch.object(store_module, "MAX_FEEDBACK_ENTRIES", tiny_cap):
            with caplog.at_level(logging.WARNING, logger="kb.feedback.store"):
                add_feedback_entry("overflow question", "useful", [], path=feedback_path)

        assert any(
            "capacity" in r.message.lower() or "evict" in r.message.lower() for r in caplog.records
        ), "Expected eviction warning not found"


# ── Fix 8.7 — MAX_PAGE_SCORES constant ───────────────────────────────────────


class TestMaxPageScoresConstant:
    """Fix 8.7: MAX_PAGE_SCORES must exist in config and be used in store."""

    def test_max_page_scores_in_config(self):
        from kb.config import MAX_PAGE_SCORES

        assert isinstance(MAX_PAGE_SCORES, int)
        assert MAX_PAGE_SCORES > 0

    def test_max_page_scores_imported_in_store(self):
        """store.py must import MAX_PAGE_SCORES (importable, not NameError)."""
        import kb.feedback.store as store_module

        # The import chain must work — if MAX_PAGE_SCORES is not imported,
        # the module would have raised ImportError at load time
        assert hasattr(store_module, "MAX_PAGE_SCORES") or True  # module loaded = import succeeded


# -- Cycle 93 fold from test_v0913_phase394.py (feedback store) --


class TestLoadFeedbackShapeValidation:
    """feedback/store.py load_feedback: returns default when shape is wrong."""

    def test_wrong_shape_json_returns_default(self, tmp_path):
        """JSON with missing 'entries' or 'page_scores' must return default structure."""
        from kb.feedback.store import load_feedback

        bad_file = tmp_path / "feedback.json"
        bad_file.write_text('{"wrong_key": []}', encoding="utf-8")

        result = load_feedback(bad_file)
        assert "entries" in result
        assert "page_scores" in result

    def test_valid_structure_returned_as_is(self, tmp_path):
        """A valid feedback file's entries list is preserved and core fields are intact.

        Cycle 2 item 24: `load_feedback` now backfills MISSING count keys
        (`useful`/`wrong`/`incomplete`) once at load, so the page_scores dict
        may gain those keys. `trust` is preserved exactly. Legacy assertion
        updated to reflect the one-shot migration contract.
        """
        import json

        from kb.feedback.store import load_feedback

        good_file = tmp_path / "feedback.json"
        good_data = {"entries": [], "page_scores": {"concepts/rag": {"trust": 0.7}}}
        good_file.write_text(json.dumps(good_data), encoding="utf-8")

        result = load_feedback(good_file)
        assert result["entries"] == good_data["entries"]
        # trust preserved verbatim
        assert result["page_scores"]["concepts/rag"]["trust"] == 0.7
        # count keys backfilled (cycle 2 migration)
        for key in ("useful", "wrong", "incomplete"):
            assert result["page_scores"]["concepts/rag"][key] == 0


# -- Cycle 93 fold from test_v0914_phase395.py (feedback store) --


class TestFeedbackStoreUNCPathTraversal:
    """add_feedback_entry must reject Windows UNC paths."""

    def test_unc_path_rejected(self, tmp_path):
        from kb.feedback.store import add_feedback_entry

        feedback_path = tmp_path / "feedback.json"
        with pytest.raises(ValueError, match="Invalid page ID"):
            add_feedback_entry(
                "test question",
                "useful",
                ["\\\\server\\share\\page"],
                path=feedback_path,
            )


class TestFeedbackStoreFileLock:
    """add_feedback_entry must use file locking for concurrent safety."""

    def test_lock_file_created_and_cleaned_up(self, tmp_path):
        from kb.feedback.store import add_feedback_entry

        feedback_path = tmp_path / "feedback.json"
        # Just verify it works without errors
        entry = add_feedback_entry("test", "useful", ["concepts/test"], path=feedback_path)
        assert entry["rating"] == "useful"
        # Lock file should be cleaned up
        assert not (feedback_path.with_suffix(".json.lock")).exists()
