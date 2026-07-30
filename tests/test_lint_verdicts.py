"""Tests for the lint verdicts module (persistent verdict storage)."""

import json
import threading

import pytest

from kb.lint.verdicts import (
    VALID_VERDICT_TYPES,
    add_verdict,
    get_page_verdicts,
    get_verdict_summary,
    load_verdicts,
    save_verdicts,
)
from kb.utils.io import atomic_json_write

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
    assert result[0]["notes"] == "third"  # 2026-04-03 (most recent)
    assert result[1]["notes"] == "second"  # 2026-04-02
    assert result[2]["notes"] == "first"  # 2026-04-01


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
        "augment": 0,
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


# -- Cycle 90 fold from test_v5_verdict_augment_type.py --
# Regression: VALID_VERDICT_TYPES includes 'augment' for kb_lint --augment verdicts.


def test_augment_is_a_valid_verdict_type():
    assert "augment" in VALID_VERDICT_TYPES


def test_add_verdict_accepts_augment_type(tmp_path, monkeypatch):
    verdicts_path = tmp_path / "verdicts.json"
    monkeypatch.setattr("kb.lint.verdicts.VERDICTS_PATH", verdicts_path)
    atomic_json_write([], verdicts_path)

    add_verdict(
        page_id="concepts/mixture-of-experts",
        verdict_type="augment",
        verdict="pass",
        notes="augmented from wikipedia, body 1.2k chars, 1 citation",
        issues=[],
    )
    saved = json.loads(verdicts_path.read_text())
    assert any(v["verdict_type"] == "augment" for v in saved)


def test_add_verdict_rejects_unknown_type(tmp_path, monkeypatch):
    import pytest

    verdicts_path = tmp_path / "verdicts.json"
    monkeypatch.setattr("kb.lint.verdicts.VERDICTS_PATH", verdicts_path)
    atomic_json_write([], verdicts_path)

    with pytest.raises(ValueError, match="Invalid verdict_type"):
        add_verdict(
            page_id="concepts/foo",
            verdict_type="not_a_real_type",
            verdict="pass",
            notes="x",
            issues=[],
        )


# -- Cycle 92 fold from test_v0915_task06.py (verdict-store subset) --
# Phase 3.96 Task 6 — add_verdict threading lock + null-byte guard,
# get_page_verdicts malformed-entry tolerance.


# ── Fix 6.3 — threading.Lock in add_verdict ──────────────────────────────────


class TestAddVerdictThreadingLock:
    """Fix 6.3 — concurrent add_verdict calls do not lose entries."""

    def test_concurrent_add_verdict_no_lost_writes(self, tmp_path):
        """Multiple threads adding verdicts concurrently should all be persisted."""
        from kb.lint.verdicts import add_verdict, load_verdicts

        path = tmp_path / "verdicts.json"
        n_threads = 10

        errors = []

        def add_one(i):
            try:
                add_verdict(
                    f"concepts/page-{i}",
                    "review",
                    "pass",
                    notes=f"thread {i}",
                    path=path,
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_one, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent write: {errors}"
        result = load_verdicts(path)
        assert len(result) == n_threads

    def test_concurrent_writes_trim_at_max_verdicts(self, tmp_path):
        """Concurrent writes near MAX_VERDICTS cap should trim correctly, not overflow."""
        import json

        from kb.config import MAX_VERDICTS
        from kb.lint.verdicts import add_verdict, load_verdicts

        path = tmp_path / "verdicts.json"
        # Pre-fill to (MAX_VERDICTS - 3) entries so the cap is hit during the test.
        pre = [
            {
                "page_id": f"concepts/pre-{i}",
                "verdict_type": "review",
                "verdict": "pass",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "issues": [],
                "notes": "",
            }
            for i in range(MAX_VERDICTS - 3)
        ]
        path.write_text(json.dumps(pre), encoding="utf-8")

        errors = []

        def add_one(i):
            try:
                add_verdict(f"concepts/new-{i}", "review", "pass", path=path)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_one, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during trim-path concurrent write: {errors}"
        result = load_verdicts(path)
        assert len(result) <= MAX_VERDICTS, f"Trim failed: {len(result)} > {MAX_VERDICTS}"

    def test_lock_module_attribute_does_not_use_threading(self):
        """_verdicts_lock (old name) must not exist; _VERDICTS_WRITE_LOCK is the successor."""
        import threading

        import kb.lint.verdicts as verdicts_mod

        # Old name must be absent.
        assert not hasattr(verdicts_mod, "_verdicts_lock") or not hasattr(
            getattr(verdicts_mod, "_verdicts_lock", None), "acquire"
        ), "_verdicts_lock is still present — remove it (use _VERDICTS_WRITE_LOCK + file_lock)"
        # New in-process guard must be present and be a threading.Lock.
        assert hasattr(verdicts_mod, "_VERDICTS_WRITE_LOCK"), (
            "_VERDICTS_WRITE_LOCK missing from verdicts module"
        )
        assert isinstance(verdicts_mod._VERDICTS_WRITE_LOCK, type(threading.Lock())), (
            "_VERDICTS_WRITE_LOCK is not a threading.Lock"
        )


# ── Fix 6.11 — get_page_verdicts KeyError ────────────────────────────────────


class TestGetPageVerdictsKeyError:
    """Fix 6.11 — get_page_verdicts uses .get() to tolerate malformed entries."""

    def test_malformed_entry_no_page_id_key_is_skipped(self, tmp_path):
        """Entry missing 'page_id' key should not raise KeyError."""
        import json

        from kb.lint.verdicts import get_page_verdicts

        path = tmp_path / "verdicts.json"
        # Write a malformed entry (no page_id key)
        malformed = [
            {"verdict_type": "review", "verdict": "pass", "timestamp": "2026-01-01T00:00:00"}
        ]
        path.write_text(json.dumps(malformed), encoding="utf-8")

        # Should not raise
        result = get_page_verdicts("concepts/rag", path=path)
        assert result == []

    def test_malformed_entry_mixed_with_valid(self, tmp_path):
        """Valid entries are returned even when malformed entries are present."""
        import json

        from kb.lint.verdicts import get_page_verdicts

        path = tmp_path / "verdicts.json"
        data = [
            # malformed — no page_id
            {"verdict_type": "review", "verdict": "pass", "timestamp": "2026-01-01T00:00:00"},
            # valid
            {
                "page_id": "concepts/rag",
                "verdict_type": "review",
                "verdict": "pass",
                "timestamp": "2026-01-02T00:00:00",
            },
        ]
        path.write_text(json.dumps(data), encoding="utf-8")

        result = get_page_verdicts("concepts/rag", path=path)
        assert len(result) == 1
        assert result[0]["page_id"] == "concepts/rag"


# ── Fix 6.15 — null byte check in add_verdict ────────────────────────────────


class TestAddVerdictNullByte:
    """Fix 6.15 — add_verdict rejects page_id containing null bytes."""

    def test_null_byte_raises_value_error(self, tmp_path):
        """page_id with null byte should raise ValueError."""
        import pytest

        from kb.lint.verdicts import add_verdict

        path = tmp_path / "verdicts.json"
        with pytest.raises(ValueError, match="Invalid page_id"):
            add_verdict("concepts/rag\x00evil", "review", "pass", path=path)

    def test_valid_page_id_not_rejected(self, tmp_path):
        """Normal page_id should still work after adding null byte check."""
        from kb.lint.verdicts import add_verdict, load_verdicts

        path = tmp_path / "verdicts.json"
        entry = add_verdict("concepts/rag", "review", "pass", path=path)
        assert entry["page_id"] == "concepts/rag"
        assert len(load_verdicts(path)) == 1



# -- Cycle 93 fold from test_v0913_phase394.py (verdicts) --


class TestVerdictPathTraversal:
    """lint/verdicts.py add_verdict: rejects path traversal in page_id."""

    def test_add_verdict_rejects_path_traversal(self, tmp_path):
        """add_verdict must raise ValueError for page_ids with '..' or leading '/'."""
        import pytest

        from kb.lint.verdicts import add_verdict

        with pytest.raises(ValueError, match="Invalid page_id"):
            add_verdict("../etc/passwd", "fidelity", "pass", path=tmp_path / "v.json")

        with pytest.raises(ValueError, match="Invalid page_id"):
            add_verdict("/absolute/path", "fidelity", "pass", path=tmp_path / "v.json")


class TestVerdictNotesCap:
    """lint/verdicts.py add_verdict: notes length is capped via truncation."""

    def test_add_verdict_truncates_oversized_notes(self, tmp_path):
        """add_verdict must truncate notes that exceed MAX_NOTES_LEN (not raise)."""
        from kb.lint.verdicts import MAX_NOTES_LEN, add_verdict

        entry = add_verdict(
            "concepts/test",
            "fidelity",
            "pass",
            notes="x" * 2001,
            path=tmp_path / "v.json",
        )
        assert len(entry["notes"]) <= MAX_NOTES_LEN


# -- Cycle 93 fold from test_v0914_phase395.py (verdicts) --


class TestAddVerdictTruncatesNotes:
    """add_verdict must truncate long notes instead of raising ValueError."""

    def test_long_notes_truncated(self, tmp_path):
        from kb.lint.verdicts import MAX_NOTES_LEN, add_verdict

        verdict_path = tmp_path / "verdicts.json"
        long_notes = "x" * (MAX_NOTES_LEN + 500)

        result = add_verdict(
            "concepts/test",
            "fidelity",
            "pass",
            notes=long_notes,
            path=verdict_path,
        )
        assert len(result["notes"]) <= MAX_NOTES_LEN
