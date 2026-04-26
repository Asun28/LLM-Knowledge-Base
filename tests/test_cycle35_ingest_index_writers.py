"""Cycle 35 — `_update_sources_mapping` + `_update_index_batch` RMW lock,
empty-list early-return, and backtick-source-ref dedup.

Threats covered: T2 (sources RMW), T3 (index RMW), T4 (empty wiki_pages malformed
line), T5 (backtick dedup), T8 (no warning under empty + missing). Cycle-24 L4
revert-fail discipline: each test fails when the production fix is reverted.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from kb.ingest import pipeline


def _build_rmw_spies(monkeypatch):
    """Returns (call_log, original_read_text).

    `call_log` records `("file_lock_enter", path)` / `("file_lock_exit", path)` /
    `("read_text", path)` / `("atomic_text_write", (content, path))` in order.
    Cycle-17 L4: stdlib spy ordering, NOT artificial mid-section race injection.
    """
    call_log: list[tuple[str, object]] = []

    @contextmanager
    def _file_lock_spy(path, *args, **kwargs):
        call_log.append(("file_lock_enter", path))
        try:
            yield
        finally:
            call_log.append(("file_lock_exit", path))

    def _atomic_write_spy(content, path):
        call_log.append(("atomic_text_write", (content, path)))
        Path(path).write_text(content, encoding="utf-8")

    real_read_text = Path.read_text

    def _read_text_spy(self, *args, **kwargs):
        call_log.append(("read_text", self))
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(pipeline, "file_lock", _file_lock_spy)
    monkeypatch.setattr(pipeline, "atomic_text_write", _atomic_write_spy)
    monkeypatch.setattr(Path, "read_text", _read_text_spy)
    return call_log


# ---------------------------------------------------------------------------
# AC8 — _update_sources_mapping RMW lock, both branches
# ---------------------------------------------------------------------------


class TestUpdateSourcesMappingRMWLock:
    def test_lock_spans_rmw_new_entry_branch(self, monkeypatch, tmp_path):
        """New-entry append branch: lock entered before read, exited after write."""
        sources = tmp_path / "_sources.md"
        sources.write_text("# Sources\n\n", encoding="utf-8")
        log = _build_rmw_spies(monkeypatch)

        pipeline._update_sources_mapping("raw/articles/new.md", ["e/new"], wiki_dir=tmp_path)

        names = [name for name, _ in log]
        assert names[0] == "file_lock_enter"
        assert names[-1] == "file_lock_exit"
        assert "read_text" in names
        assert "atomic_text_write" in names
        # Lock entered BEFORE read; lock exited AFTER write.
        assert names.index("file_lock_enter") < names.index("read_text")
        assert names.index("atomic_text_write") < names.index("file_lock_exit")

    def test_lock_spans_rmw_merge_branch(self, monkeypatch, tmp_path):
        """Existing-line dedup/merge branch: same lock-spans-RMW invariant."""
        sources = tmp_path / "_sources.md"
        sources.write_text("- `raw/articles/old.md` → [[e/old]]\n", encoding="utf-8")
        log = _build_rmw_spies(monkeypatch)

        # Re-call with NEW page IDs on the SAME source_ref → merge branch fires.
        pipeline._update_sources_mapping(
            "raw/articles/old.md", ["e/old", "e/new"], wiki_dir=tmp_path
        )

        names = [name for name, _ in log]
        assert names[0] == "file_lock_enter"
        assert names[-1] == "file_lock_exit"
        assert names.index("file_lock_enter") < names.index("read_text")
        assert names.index("atomic_text_write") < names.index("file_lock_exit")


# ---------------------------------------------------------------------------
# AC9 — _update_index_batch RMW lock
# ---------------------------------------------------------------------------


class TestUpdateIndexBatchRMWLock:
    def test_lock_spans_rmw(self, monkeypatch, tmp_path):
        index_path = tmp_path / "index.md"
        index_path.write_text("## Entities\n\n*No pages yet.*\n", encoding="utf-8")
        log = _build_rmw_spies(monkeypatch)

        pipeline._update_index_batch([("entity", "new-entity", "New Entity")], wiki_dir=tmp_path)

        names = [name for name, _ in log]
        assert names[0] == "file_lock_enter"
        assert names[-1] == "file_lock_exit"
        assert names.index("file_lock_enter") < names.index("read_text")
        assert "atomic_text_write" in names
        assert names.index("atomic_text_write") < names.index("file_lock_exit")

    def test_no_lock_when_entries_empty(self, monkeypatch, tmp_path):
        """Early-return at empty entries STAYS BEFORE lock (no-op shouldn't lock)."""
        index_path = tmp_path / "index.md"
        index_path.write_text("## Entities\n\n", encoding="utf-8")
        log = _build_rmw_spies(monkeypatch)

        pipeline._update_index_batch([], wiki_dir=tmp_path)

        names = {name for name, _ in log}
        assert "file_lock_enter" not in names
        assert "atomic_text_write" not in names


# ---------------------------------------------------------------------------
# AC10 — empty wiki_pages skips silently (T4 + T8)
# ---------------------------------------------------------------------------


class TestUpdateSourcesMappingEmptyList:
    def test_byte_equal_snapshot_existing_file(self, monkeypatch, tmp_path):
        """AC10 — byte-equal snapshot before/after empty-pages call on EXISTING file.

        Plus: assert no lock acquired, no atomic_text_write fires (early-return
        BEFORE any I/O). Cycle-24 L4: revert AC6 (place the early-return AFTER
        sources_file.exists() check) → file is read and the early-return short-
        circuits BEFORE write, so the byte-equal still holds — but the lock-
        absence assertion would fail because the lock wraps the existence check.
        Reverting further (deleting the early-return entirely) writes a
        malformed `→ \\n` line and the byte-equal snapshot fails.
        """
        sources = tmp_path / "_sources.md"
        original = "# Sources\n\n- `raw/articles/old.md` → [[e/old]]\n"
        sources.write_text(original, encoding="utf-8")
        snap_before = sources.read_bytes()

        log = _build_rmw_spies(monkeypatch)

        pipeline._update_sources_mapping("raw/articles/empty.md", [], wiki_dir=tmp_path)

        # Byte-equal: file content unchanged.
        assert sources.read_bytes() == snap_before
        # No I/O fired (early-return before file_lock + read_text).
        names = {name for name, _ in log}
        assert "file_lock_enter" not in names
        assert "atomic_text_write" not in names

    def test_silent_on_absent_file(self, monkeypatch, tmp_path, caplog):
        """T8 — empty wiki_pages with sources_file absent: silent no-op, no warning."""
        log = _build_rmw_spies(monkeypatch)

        with caplog.at_level("WARNING"):
            pipeline._update_sources_mapping("raw/articles/empty.md", [], wiki_dir=tmp_path)

        names = {name for name, _ in log}
        assert "atomic_text_write" not in names
        # T8: no `_sources.md not found` warning under empty wiki_pages.
        assert not any("not found" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# AC11 — backtick in source_ref doesn't double-write
# ---------------------------------------------------------------------------


class TestUpdateSourcesMappingBacktickDedup:
    def test_dedups_backtick_in_source_ref(self, tmp_path):
        """AC11 — backtick-bearing source_ref deduplicates on re-call.

        Cycle-24 L4 dual-anchor:
          - Single-call invariant: escaped form on disk after call 1.
          - Two-call invariant: re-call with same source_ref → single line.
        Revert AC7 (membership/per-line scan back to raw `source_ref`):
          call 2 fails to find the escaped form already on disk → second entry
          appended → 2 lines instead of 1.
        """
        sources = tmp_path / "_sources.md"
        sources.write_text("# Sources\n\n", encoding="utf-8")
        ref = r"raw/has`backtick.md"

        # Call 1: writes the entry with escaped backtick.
        pipeline._update_sources_mapping(ref, ["e/foo"], wiki_dir=tmp_path)
        content_after_1 = sources.read_text(encoding="utf-8")
        # Single-call invariant: escaped form on disk.
        assert r"`raw/has\`backtick.md`" in content_after_1
        n_entries_1 = content_after_1.count(r"raw/has\`backtick.md")
        assert n_entries_1 == 1

        # Call 2 with identical inputs: dedup branch hits, no second entry.
        pipeline._update_sources_mapping(ref, ["e/foo"], wiki_dir=tmp_path)
        content_after_2 = sources.read_text(encoding="utf-8")
        n_entries_2 = content_after_2.count(r"raw/has\`backtick.md")
        assert n_entries_2 == 1, f"expected 1 entry, got {n_entries_2}: {content_after_2!r}"

    def test_dedup_extends_with_new_pages(self, tmp_path):
        """Merge-branch sanity: re-call with NEW pages adds them to the same line."""
        sources = tmp_path / "_sources.md"
        sources.write_text("# Sources\n\n", encoding="utf-8")
        ref = r"raw/has`backtick.md"

        pipeline._update_sources_mapping(ref, ["e/foo"], wiki_dir=tmp_path)
        pipeline._update_sources_mapping(ref, ["e/foo", "e/bar"], wiki_dir=tmp_path)

        content = sources.read_text(encoding="utf-8")
        # Still exactly one line for this source_ref.
        assert content.count(r"raw/has\`backtick.md") == 1
        # Both wiki pages present.
        assert "[[e/foo]]" in content
        assert "[[e/bar]]" in content
