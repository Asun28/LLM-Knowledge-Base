"""Tests for the feedback module (store + reliability)."""

import json
from pathlib import Path

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
    entry = add_feedback_entry(
        "What is RAG?", "useful", ["concepts/rag"], path=path
    )
    assert entry["rating"] == "useful"
    data = load_feedback(path)
    assert len(data["entries"]) == 1
    scores = data["page_scores"]["concepts/rag"]
    assert scores["useful"] == 1
    assert scores["wrong"] == 0
    # trust = (1 + 1) / (1 + 2) = 0.6667
    assert abs(scores["trust"] - 0.6667) < 0.001


def test_add_feedback_entry_wrong(tmp_path):
    """add_feedback_entry with 'wrong' rating lowers trust score."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("What is RAG?", "wrong", ["concepts/rag"], path=path)
    data = load_feedback(path)
    scores = data["page_scores"]["concepts/rag"]
    assert scores["wrong"] == 1
    # trust = (0 + 1) / (1 + 2) = 0.3333
    assert abs(scores["trust"] - 0.3333) < 0.001


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
    # trust = (2 + 1) / (3 + 2) = 0.6
    assert abs(scores["trust"] - 0.6) < 0.001


def test_add_feedback_entry_invalid_rating(tmp_path):
    """add_feedback_entry raises ValueError for invalid rating."""
    path = tmp_path / "feedback.json"
    import pytest

    with pytest.raises(ValueError, match="Invalid rating"):
        add_feedback_entry("Q1", "bad_rating", ["concepts/rag"], path=path)


def test_add_feedback_entry_multiple_pages(tmp_path):
    """add_feedback_entry updates scores for all cited pages."""
    path = tmp_path / "feedback.json"
    add_feedback_entry(
        "Q1", "useful", ["concepts/rag", "entities/openai"], path=path
    )
    data = load_feedback(path)
    assert "concepts/rag" in data["page_scores"]
    assert "entities/openai" in data["page_scores"]
    assert data["page_scores"]["concepts/rag"]["useful"] == 1
    assert data["page_scores"]["entities/openai"]["useful"] == 1
