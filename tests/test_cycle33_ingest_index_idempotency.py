"""Cycle 33 AC6-AC8 — pin the serial dedup-on-recall contract for
``_update_sources_mapping`` and ``_update_index_batch`` via ``atomic_text_write``
spy + final-content assertions.

Threats covered: T7 (silent regression of dedup guard), T8 (merge-branch
regression). Per cycle-24 L4 + cycle-30 L1, the spy assertion is what makes
the test revert-resistant — without the spy a refactor that re-writes the
SAME content after dedup reordering would still pass a content-only check.

Also covers R1-09 IN-CYCLE: missing-_sources.md early-out at pipeline.py:773-775.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest import mock

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _seed_sources_file(wiki_dir: Path) -> Path:
    """Seed an empty `_sources.md` with minimal frontmatter."""
    path = wiki_dir / "_sources.md"
    path.write_text(
        "---\ntitle: Source Mapping\nsource: []\ntype: index\n---\n\n# Source Mapping\n",
        encoding="utf-8",
    )
    return path


def _seed_index_file(wiki_dir: Path) -> Path:
    """Seed an empty `index.md` with the section headers used by ``_update_index_batch``."""
    path = wiki_dir / "index.md"
    path.write_text(
        "---\ntitle: Wiki Index\nsource: []\ntype: index\n---\n\n"
        "# Knowledge Base Index\n\n"
        "## Pages\n\n*No pages yet.*\n\n"
        "## Entities\n\n*No pages yet.*\n\n"
        "## Concepts\n\n*No pages yet.*\n\n"
        "## Comparisons\n\n*No pages yet.*\n\n"
        "## Summaries\n\n*No pages yet.*\n\n"
        "## Synthesis\n\n*No pages yet.*\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# AC7 — repeat-call idempotency on _update_sources_mapping + _update_index_batch
# ---------------------------------------------------------------------------


class TestSourcesMappingIdempotency:
    """AC7 — `_update_sources_mapping` second identical call is a no-op (no write)."""

    def test_repeat_call_no_duplicate_and_no_extra_write(self, tmp_wiki, monkeypatch):
        from kb.ingest import pipeline

        sources_path = _seed_sources_file(tmp_wiki)

        # Spy that delegates to the real atomic_text_write (so the file actually
        # lands) but counts invocations so we can pin "no-op on second call".
        real_atomic_write = pipeline.atomic_text_write
        spy = mock.MagicMock(side_effect=real_atomic_write)
        monkeypatch.setattr("kb.ingest.pipeline.atomic_text_write", spy)

        pages = ["entities/foo", "concepts/bar"]

        # First call writes the new entry.
        pipeline._update_sources_mapping("raw/articles/x.md", pages, wiki_dir=tmp_wiki)
        # Second call (identical args) hits the dedup branch at pipeline.py:781-791
        # and finds `missing == []`, so no atomic_text_write should fire.
        pipeline._update_sources_mapping("raw/articles/x.md", pages, wiki_dir=tmp_wiki)

        # Content contract: exactly ONE line referencing the source-ref.
        text = sources_path.read_text(encoding="utf-8")
        assert text.count("`raw/articles/x.md`") == 1
        assert "[[entities/foo]]" in text
        assert "[[concepts/bar]]" in text

        # Behavioural contract (Q11): exactly ONE write — the second call short-circuits.
        assert spy.call_count == 1, (
            f"Expected exactly 1 atomic_text_write call across two identical "
            f"_update_sources_mapping invocations; got {spy.call_count}. "
            f"This indicates the dedup-on-recall contract regressed (T7)."
        )

    def test_missing_sources_file_warns_and_skips(self, tmp_wiki, monkeypatch, caplog):
        """R1-09 IN-CYCLE — `_sources.md` missing-file early-out at pipeline.py:773-775."""
        from kb.ingest import pipeline

        caplog.set_level(logging.WARNING, logger="kb.ingest.pipeline")
        # Do NOT seed `_sources.md`.

        spy = mock.MagicMock(side_effect=pipeline.atomic_text_write)
        monkeypatch.setattr("kb.ingest.pipeline.atomic_text_write", spy)

        pipeline._update_sources_mapping(
            "raw/articles/x.md", ["entities/foo"], wiki_dir=tmp_wiki
        )

        # Contract: file is NOT created and the warning fires.
        assert not (tmp_wiki / "_sources.md").exists()
        assert "_sources.md not found" in caplog.text
        # And no write happened.
        assert spy.call_count == 0


class TestIndexBatchIdempotency:
    """AC7 — `_update_index_batch` second identical call is a no-op (no write)."""

    def test_repeat_call_no_duplicate_and_no_extra_write(self, tmp_wiki, monkeypatch):
        from kb.ingest import pipeline

        index_path = _seed_index_file(tmp_wiki)

        spy = mock.MagicMock(side_effect=pipeline.atomic_text_write)
        monkeypatch.setattr("kb.ingest.pipeline.atomic_text_write", spy)

        entries = [("entity", "foo", "Foo Title"), ("concept", "bar", "Bar Title")]

        # First call writes; second call hits the dedup at pipeline.py:818
        # (`if f"[[{subdir}/{slug}|" in content: continue`).
        pipeline._update_index_batch(entries, wiki_dir=tmp_wiki)
        pipeline._update_index_batch(entries, wiki_dir=tmp_wiki)

        text = index_path.read_text(encoding="utf-8")
        assert text.count("[[entities/foo|Foo Title]]") == 1
        assert text.count("[[concepts/bar|Bar Title]]") == 1

        # Behavioural contract (Q11): only the first call writes.
        assert spy.call_count == 1, (
            f"Expected exactly 1 atomic_text_write across two identical "
            f"_update_index_batch invocations; got {spy.call_count}. "
            f"Index dedup-on-recall contract regressed (T7)."
        )


# ---------------------------------------------------------------------------
# AC8 — crash-recovery scenario: dedup branch + merge-on-new-pages branch
# ---------------------------------------------------------------------------


class TestSourcesMappingCrashRecovery:
    """AC8 — manifest-agnostic re-call (dedup) + merge-on-new-pages branch.

    The test docstrings note: ``_update_sources_mapping`` does NOT consult the
    manifest at all (Q5 design decision), so a "crash before manifest-save"
    is functionally equivalent to "second call with same args" — no separate
    failure simulation is needed.
    """

    def test_crash_then_reingest_dedup_branch_is_noop(self, tmp_wiki, monkeypatch):
        """AC8 step (a)-(d) — crash-then-reingest with same pages → no second write."""
        from kb.ingest import pipeline

        sources_path = _seed_sources_file(tmp_wiki)

        spy = mock.MagicMock(side_effect=pipeline.atomic_text_write)
        monkeypatch.setattr("kb.ingest.pipeline.atomic_text_write", spy)

        pages = ["entities/foo", "concepts/bar"]

        # (a) First ingest — writes the entry.
        pipeline._update_sources_mapping("raw/articles/x.md", pages, wiki_dir=tmp_wiki)
        first_content = sources_path.read_text(encoding="utf-8")

        # (b)+(c) Manifest never updated → simulates crash-before-manifest-save.
        # `_update_sources_mapping` is manifest-agnostic by construction (Q5).
        # (d) Re-ingest with identical args.
        pipeline._update_sources_mapping("raw/articles/x.md", pages, wiki_dir=tmp_wiki)
        second_content = sources_path.read_text(encoding="utf-8")

        # Content unchanged.
        assert first_content == second_content
        # Q11 — no second write fired.
        assert spy.call_count == 1

    def test_reingest_with_added_pages_merges_branch_writes_again(
        self, tmp_wiki, monkeypatch
    ):
        """AC8 step (e)-(f) — merge-on-new-pages branch DOES write a second time."""
        from kb.ingest import pipeline

        sources_path = _seed_sources_file(tmp_wiki)

        spy = mock.MagicMock(side_effect=pipeline.atomic_text_write)
        monkeypatch.setattr("kb.ingest.pipeline.atomic_text_write", spy)

        # (a) First call — initial pages.
        pipeline._update_sources_mapping(
            "raw/articles/x.md", ["entities/foo", "concepts/bar"], wiki_dir=tmp_wiki
        )

        # (e) Re-call with ADDED `concepts/baz`. Must hit the merge branch
        # at pipeline.py:781-791 which appends only the missing IDs.
        pipeline._update_sources_mapping(
            "raw/articles/x.md",
            ["entities/foo", "concepts/bar", "concepts/baz"],
            wiki_dir=tmp_wiki,
        )

        text = sources_path.read_text(encoding="utf-8")

        # (f) Existing line MERGED — single line with all three page IDs.
        assert text.count("`raw/articles/x.md`") == 1
        assert "[[entities/foo]]" in text
        assert "[[concepts/bar]]" in text
        assert "[[concepts/baz]]" in text

        # Q11 merge-branch contract: TWO writes (initial + merge).
        assert spy.call_count == 2, (
            f"Expected 2 atomic_text_writes across initial + merge re-call; "
            f"got {spy.call_count}. Merge branch regressed (T8) — new pages "
            f"may have been silently dropped."
        )


# ---------------------------------------------------------------------------
# Cycle-22 L5 self-check — every Step-5 CONDITION must map to an assertion above
# ---------------------------------------------------------------------------

# Map of design CONDITIONS → tests that pin them:
#   spy.call_count == 1 (dedup) → TestSourcesMappingIdempotency,
#                                 TestIndexBatchIdempotency,
#                                 TestSourcesMappingCrashRecovery
#                                   ::test_crash_then_reingest_dedup_branch_is_noop
#   spy.call_count == 2 (merge) → TestSourcesMappingCrashRecovery
#                                   ::test_reingest_with_added_pages_merges_branch_writes_again
#   missing-file warning        → TestSourcesMappingIdempotency
#                                   ::test_missing_sources_file_warns_and_skips
#   tmp_wiki fixture            → all tests
#   wiki_dir= keyword           → all tests
