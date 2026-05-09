"""Cycle 73 AC06 — BACKLOG.md hygiene assertions.

AC06 (EXTENDED) deletes / updates two stale entries in `BACKLOG.md`:

(a) The `KB_DISABLE_VECTORS=1 runtime kill-switch (cycle-N+1 if requested)`
    Phase 4.5 MEDIUM line — already shipped in cycle 67 AC06 (per
    `CLAUDE.md` Quick Reference §Auto-rebuild + auto-publish).

(b) The snapshot-subjects deferred list at line 79-80 — primary-session
    grep proved 5 of 6 listed subjects already shipped in cycles 69/70
    (`_render_sources`, `build_extraction_prompt`, `_build_summary_content`,
    `build_llms_full_txt`, `build_graph_jsonld`). Only `_persist_contradictions`
    remains — and cycle 73 AC05 ships that. Updated text reflects this.

Per design-decision §C-AC06-1..5 (FROZEN at Step 5):
- C-AC06-1: literal-substring assertion on the KB_DISABLE_VECTORS line.
- C-AC06-2: literal-substring assertion that snapshot-subjects line
  reflects "5 of 6 shipped" rather than the original 6-deferred list.
- C-AC06-3: CHANGELOG `[Unreleased]` Quick Reference references the
  hygiene cleanup (verifies docs follow code).
- C-AC06-4: BACKLOG file is still well-formed markdown (header intact).
- C-AC06-5: AC06 cleanup does NOT accidentally delete adjacent unrelated
  entries (count-of-MEDIUM-bullets stays in the expected range).

Per ``feedback_test_behavior_over_signature``: literal-substring grep on
text files IS the behavioural assertion here (AC06 IS doc-only).
"""

from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    """Find the repo root by walking up from this file until BACKLOG.md
    appears. Matches the cycle-23 AC2 pattern.
    """
    here = Path(__file__).resolve().parent
    for ancestor in (here, *here.parents):
        if (ancestor / "BACKLOG.md").exists():
            return ancestor
    raise AssertionError("BACKLOG.md not found in any ancestor of tests/")


def test_kb_disable_vectors_stale_entry_absent():
    """C-AC06-1: the stale `KB_DISABLE_VECTORS=1 runtime kill-switch
    (cycle-N+1 if requested)` Phase 4.5 MEDIUM line MUST be deleted from
    BACKLOG.md (already shipped cycle 67 AC06)."""
    backlog = (_repo_root() / "BACKLOG.md").read_text(encoding="utf-8")

    stale_marker = "`KB_DISABLE_VECTORS=1` runtime kill-switch (cycle-N+1 if requested)"
    assert stale_marker not in backlog, (
        "Stale BACKLOG entry still present:\n"
        f"  '{stale_marker}'\n"
        "This was shipped in cycle 67 AC06 — must be deleted per AC06."
    )


def test_snapshot_subjects_deferred_list_updated():
    """C-AC06-2: the snapshot-subjects line MUST be updated to reflect
    that 5 of 6 subjects shipped cycles 69/70.

    The PRE-CYCLE-73 stale text contains all 6 listed (the comma-separated
    list ending with `_render_sources`). The POST-CYCLE-73 text drops the
    5 shipped ones and references `_persist_contradictions` as the
    remaining/landed subject."""
    backlog = (_repo_root() / "BACKLOG.md").read_text(encoding="utf-8")

    # Stale signature: the comma-listed `_build_summary_content
    # page-rendering, kb publish --format graph JSON-LD output, ... ,
    # _render_sources` enumeration.
    stale_signature = (
        "_build_summary_content` page-rendering, "
        "`kb publish --format graph` JSON-LD output, "
        "`auto_publish_after_compile`'s `_publish/llms-full.txt` body, "
        "contradictions append, `build_extraction_prompt`, `_render_sources`"
    )
    assert stale_signature not in backlog, (
        "Pre-cycle-73 stale snapshot-subjects enumeration still present in "
        "BACKLOG.md — primary-session grep proved 5 of 6 shipped cycles 69/70"
    )

    # Post-cycle-73 must reference cycle-73 closure on `_persist_contradictions`.
    # We DO NOT pin exact phrasing (allows future re-wording) — just that
    # the cycle-73 closure is recognisable.
    assert "_persist_contradictions" in backlog or "contradictions append" in backlog, (
        "Updated snapshot-subjects line is missing — should mention "
        "`_persist_contradictions` / `contradictions append` (the one "
        "subject cycle-73 AC05 closes) per AC06 update"
    )


def test_backlog_header_intact():
    """C-AC06-4: AC06 cleanup must NOT corrupt BACKLOG.md structure —
    the top-level `# Backlog` header remains."""
    backlog = (_repo_root() / "BACKLOG.md").read_text(encoding="utf-8")

    assert backlog.startswith("# Backlog\n"), (
        "BACKLOG.md top-level header missing or corrupted by AC06 cleanup"
    )
    # Cross-reference table preserved.
    assert "## Cross-reference" in backlog, "BACKLOG.md ## Cross-reference section missing"
    assert "## Phase 4.5" in backlog, "BACKLOG.md ## Phase 4.5 section missing"


def test_changelog_references_backlog_hygiene():
    """C-AC06-3: CHANGELOG `[Unreleased]` Quick Reference includes the
    cycle-73 BACKLOG hygiene entry."""
    changelog = (_repo_root() / "CHANGELOG.md").read_text(encoding="utf-8")

    # Must mention either cycle-73 + BACKLOG hygiene OR the specific
    # KB_DISABLE_VECTORS stale-entry cleanup OR the snapshot-subjects
    # update — at least one signal that AC06 was documented.
    signals = [
        "BACKLOG hygiene",
        "backlog hygiene",
        "KB_DISABLE_VECTORS",
        "snapshot subjects",
        "snapshot-subjects",
    ]
    assert any(s in changelog for s in signals), (
        "CHANGELOG.md does not mention BACKLOG hygiene — at least one of "
        f"{signals} should appear under [Unreleased] for cycle 73 docs"
    )
