"""Tests for the lint verdicts module (persistent verdict storage)."""

import pytest

from kb.lint.verdicts import (
    add_verdict,
    get_page_verdicts,
    get_verdict_summary,
    load_verdicts,
    save_verdicts,
)

# ── load_verdicts ────────────────────────────────────────────────


def test_load_verdicts_empty_file(tmp_path):
    """load_verdicts returns [] when file does not exist."""
    path = tmp_path / "verdicts.json"
    result = load_verdicts(path)
    assert result == []


def test_load_verdicts_corrupted_json(tmp_path):
    """load_verdicts returns [] when file contains invalid JSON."""
    path = tmp_path / "verdicts.json"
    path.write_text("not valid json{{{", encoding="utf-8")
    result = load_verdicts(path)
    assert result == []


# ── save_verdicts / round-trip ───────────────────────────────────


def test_save_and_load_roundtrip(tmp_path):
    """Round-trip: save then load returns the same data."""
    path = tmp_path / "verdicts.json"
    data = [
        {
            "timestamp": "2026-04-07T10:00:00",
            "page_id": "concepts/rag",
            "verdict_type": "fidelity",
            "verdict": "pass",
            "issues": [],
            "notes": "",
        }
    ]
    save_verdicts(data, path)
    loaded = load_verdicts(path)
    assert loaded == data


def test_save_creates_parent_dirs(tmp_path):
    """save_verdicts creates parent directories if they don't exist."""
    path = tmp_path / "nested" / "deep" / "verdicts.json"
    assert not path.parent.exists()
    save_verdicts([{"test": True}], path)
    assert path.exists()
    loaded = load_verdicts(path)
    assert loaded == [{"test": True}]


# ── add_verdict ──────────────────────────────────────────────────


def test_add_verdict_basic(tmp_path):
    """add_verdict creates an entry with all expected fields and a timestamp."""
    path = tmp_path / "verdicts.json"
    entry = add_verdict(
        page_id="concepts/rag",
        verdict_type="fidelity",
        verdict="pass",
        issues=[{"severity": "info", "description": "minor style issue"}],
        notes="Looks good overall",
        path=path,
    )
    assert entry["page_id"] == "concepts/rag"
    assert entry["verdict_type"] == "fidelity"
    assert entry["verdict"] == "pass"
    assert entry["issues"] == [{"severity": "info", "description": "minor style issue"}]
    assert entry["notes"] == "Looks good overall"
    assert "timestamp" in entry
    # Timestamp should be an ISO string with seconds precision
    assert "T" in entry["timestamp"]


def test_add_verdict_invalid_verdict(tmp_path):
    """add_verdict raises ValueError for an invalid verdict value."""
    path = tmp_path / "verdicts.json"
    with pytest.raises(ValueError, match="Invalid verdict: bad"):
        add_verdict(
            page_id="concepts/rag",
            verdict_type="fidelity",
            verdict="bad",
            path=path,
        )


def test_add_verdict_invalid_type(tmp_path):
    """add_verdict raises ValueError for an invalid verdict_type value."""
    path = tmp_path / "verdicts.json"
    with pytest.raises(ValueError, match="Invalid verdict_type: bad_type"):
        add_verdict(
            page_id="concepts/rag",
            verdict_type="bad_type",
            verdict="pass",
            path=path,
        )


def test_add_verdict_accumulates(tmp_path):
    """Adding multiple verdicts accumulates them in the file."""
    path = tmp_path / "verdicts.json"
    add_verdict("concepts/rag", "fidelity", "pass", path=path)
    add_verdict("concepts/rag", "consistency", "warning", path=path)
    add_verdict("entities/openai", "review", "fail", path=path)
    verdicts = load_verdicts(path)
    assert len(verdicts) == 3


# ── get_page_verdicts ────────────────────────────────────────────


def test_get_page_verdicts_filters(tmp_path):
    """get_page_verdicts returns only verdicts for the specified page_id."""
    path = tmp_path / "verdicts.json"
    add_verdict("concepts/rag", "fidelity", "pass", path=path)
    add_verdict("entities/openai", "review", "fail", path=path)
    add_verdict("concepts/rag", "consistency", "warning", path=path)

    rag_verdicts = get_page_verdicts("concepts/rag", path)
    assert len(rag_verdicts) == 2
    assert all(v["page_id"] == "concepts/rag" for v in rag_verdicts)

    openai_verdicts = get_page_verdicts("entities/openai", path)
    assert len(openai_verdicts) == 1
    assert openai_verdicts[0]["verdict"] == "fail"

    # Non-existent page returns empty list
    assert get_page_verdicts("concepts/nonexistent", path) == []


def test_get_page_verdicts_sorted_desc(tmp_path):
    """get_page_verdicts returns results sorted by timestamp descending (most recent first)."""
    path = tmp_path / "verdicts.json"
    # Manually create entries with known timestamps to guarantee ordering
    verdicts = [
        {
            "timestamp": "2026-04-01T10:00:00",
            "page_id": "concepts/rag",
            "verdict_type": "fidelity",
            "verdict": "fail",
            "issues": [],
            "notes": "first",
        },
        {
            "timestamp": "2026-04-03T10:00:00",
            "page_id": "concepts/rag",
            "verdict_type": "consistency",
            "verdict": "pass",
            "issues": [],
            "notes": "third",
        },
        {
            "timestamp": "2026-04-02T10:00:00",
            "page_id": "concepts/rag",
            "verdict_type": "review",
            "verdict": "warning",
            "issues": [],
            "notes": "second",
        },
    ]
    save_verdicts(verdicts, path)

    result = get_page_verdicts("concepts/rag", path)
    assert len(result) == 3
    assert result[0]["notes"] == "third"   # 2026-04-03 (most recent)
    assert result[1]["notes"] == "second"  # 2026-04-02
    assert result[2]["notes"] == "first"   # 2026-04-01


# ── get_verdict_summary ──────────────────────────────────────────


def test_get_verdict_summary_counts(tmp_path):
    """get_verdict_summary returns correct totals, by_verdict, and by_type counts."""
    path = tmp_path / "verdicts.json"
    add_verdict("concepts/rag", "fidelity", "pass", path=path)
    add_verdict("concepts/rag", "consistency", "warning", path=path)
    add_verdict("entities/openai", "review", "fail", path=path)
    add_verdict("entities/openai", "completeness", "pass", path=path)

    summary = get_verdict_summary(path)
    assert summary["total"] == 4
    assert summary["by_verdict"] == {"pass": 2, "fail": 1, "warning": 1}
    assert summary["by_type"] == {
        "fidelity": 1,
        "consistency": 1,
        "completeness": 1,
        "review": 1,
    }


def test_get_verdict_summary_pages_with_failures(tmp_path):
    """get_verdict_summary lists page IDs that have at least one 'fail' verdict."""
    path = tmp_path / "verdicts.json"
    add_verdict("concepts/rag", "fidelity", "pass", path=path)
    add_verdict("concepts/rag", "consistency", "fail", path=path)
    add_verdict("entities/openai", "review", "fail", path=path)
    add_verdict("entities/anthropic", "review", "pass", path=path)

    summary = get_verdict_summary(path)
    # Sorted alphabetically
    assert summary["pages_with_failures"] == ["concepts/rag", "entities/openai"]
