"""Cycle 73 AC05 — snapshot subject: ``_persist_contradictions``.

Tests for cycle-73 AC05 (PIVOTED at Step 5 — primary-session grep
confirmed 5 of 6 BACKLOG-listed deferred snapshot subjects already
shipped cycles 69/70):
- ``_render_sources`` — already pinned ``tests/test_cycle69_snapshots.py:149``
- ``build_extraction_prompt`` — already pinned ``tests/test_cycle69_snapshots.py:47``
- ``_build_summary_content`` — already pinned ``tests/test_cycle70_snapshots.py:136``
- ``build_llms_full_txt`` — already pinned ``tests/test_cycle70_snapshots.py``
- ``build_graph_jsonld`` — already pinned ``tests/test_cycle70_snapshots.py``

The ONE remaining BACKLOG-deferred subject is ``_persist_contradictions``
at ``src/kb/ingest/pipeline.py:183``. This test pins it.

Per design-decision §C-AC05-1..3 (FROZEN at Step 5):
- C-AC05-1: monkeypatch ``date.today`` to a fixed date (`2026-05-09`) for
  determinism — production code calls ``date.today().isoformat()`` in
  the block header.
- C-AC05-2: pin output via ``snapshot.assert_match(text)`` (not eq-bytes
  on the file — read it back via ``read_text``).
- C-AC05-3: paired negative-control proves the snapshot test is
  non-vacuous (different source_ref → different output).

Per cycle-67 AC09 non-vacuous-snapshot rule: every snapshot subject ships
a paired negative-control.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path


_AC05_FIXED_DATE = date(2026, 5, 9)
_AC05_CONTRADICTIONS = [
    {"claim": "X states that Y is true."},
    {"claim": "Z says Y is false."},
    {"claim": "W disputes Z's grounding."},
]
_AC05_SOURCE_REF = "raw/articles/example.md"


def _patch_date_today(monkeypatch, fixed: date) -> None:
    """Monkeypatch ``kb.ingest.pipeline.date.today`` to a fixed value.

    Production at ``src/kb/ingest/pipeline.py:207`` does
    ``date.today().isoformat()`` in the block header. We override the
    bound ``date`` class within the module so the today() call is
    deterministic.
    """
    from kb.ingest import pipeline as pipeline_mod

    class _FixedDate:
        @staticmethod
        def today() -> date:
            return fixed

    monkeypatch.setattr(pipeline_mod, "date", _FixedDate)


def test_persist_contradictions_snapshot(tmp_path: Path, monkeypatch, snapshot):
    """C-AC05-1 + C-AC05-2: ``_persist_contradictions`` rendered output
    snapshot pinned with ``date.today()`` monkeypatched to 2026-05-09.

    Determinism vectors:
    - ``date.today()`` → fixed via monkeypatch (only non-deterministic call).
    - ``sanitize_extraction_field`` is input-deterministic.
    - File-lock + atomic_text_write are I/O — output read back via
      ``read_text(encoding='utf-8')``.
    """
    from kb.ingest.pipeline import _persist_contradictions

    _patch_date_today(monkeypatch, _AC05_FIXED_DATE)

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    _persist_contradictions(
        _AC05_CONTRADICTIONS,
        _AC05_SOURCE_REF,
        wiki_dir,
    )

    contradictions_path = wiki_dir / "contradictions.md"
    assert contradictions_path.exists(), (
        "_persist_contradictions did not write contradictions.md"
    )

    content = contradictions_path.read_text(encoding="utf-8")
    # Snapshot the lines (line-list comparison is more diff-readable than
    # raw string; matches cycle-70 AC06 snapshot pattern).
    assert content.splitlines() == snapshot


def test_persist_contradictions_negative_control_different_source(
    tmp_path: Path, monkeypatch
):
    """C-AC05-3 non-vacuous control: same contradictions list + DIFFERENT
    source_ref produce DIFFERENT output (proves snapshot test is sensitive
    to inputs)."""
    from kb.ingest.pipeline import _persist_contradictions

    _patch_date_today(monkeypatch, _AC05_FIXED_DATE)

    wiki_a = tmp_path / "wiki_a"
    wiki_a.mkdir()
    _persist_contradictions(_AC05_CONTRADICTIONS, "raw/articles/a.md", wiki_a)

    wiki_b = tmp_path / "wiki_b"
    wiki_b.mkdir()
    _persist_contradictions(_AC05_CONTRADICTIONS, "raw/articles/b.md", wiki_b)

    a_text = (wiki_a / "contradictions.md").read_text(encoding="utf-8")
    b_text = (wiki_b / "contradictions.md").read_text(encoding="utf-8")

    assert a_text != b_text, (
        "different source_ref must produce different output (non-vacuous "
        "snapshot — cycle-67 AC09 rule)"
    )


def test_persist_contradictions_dedup_skip_duplicate_block(
    tmp_path: Path, monkeypatch
):
    """Production at ``pipeline.py:212`` skips dup blocks: calling twice
    with identical args MUST emit ONE block, not two (defends against
    cron-trigger doubling)."""
    from kb.ingest.pipeline import _persist_contradictions

    _patch_date_today(monkeypatch, _AC05_FIXED_DATE)

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    _persist_contradictions(
        _AC05_CONTRADICTIONS, _AC05_SOURCE_REF, wiki_dir
    )
    _persist_contradictions(  # duplicate call
        _AC05_CONTRADICTIONS, _AC05_SOURCE_REF, wiki_dir
    )

    content = (wiki_dir / "contradictions.md").read_text(encoding="utf-8")
    # Block header includes "## raw/articles/example.md — 2026-05-09".
    # If dedup works, count is exactly 1.
    block_header = f"## {_AC05_SOURCE_REF} — {_AC05_FIXED_DATE.isoformat()}"
    assert content.count(block_header) == 1, (
        f"expected 1 block header, got {content.count(block_header)} — "
        "duplicate-block dedup at pipeline.py:212 broken"
    )
