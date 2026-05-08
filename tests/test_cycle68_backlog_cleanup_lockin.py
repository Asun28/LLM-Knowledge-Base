"""Cycle 68/69 BACKLOG.md cleanup lock-in regression (cumulative cross-cycle).

Cycle 68 AC15b created this file to pin two invariants:
1. Phase 4.5 / Phase 6 R2 deleted entries do NOT reappear (test 1).
2. Cycle-68 self-reference markers (AC03/AC07/AC12) ARE preserved
   pending Step 17 doc-update (test 2).

Cycle 69 retires the second invariant (Step 17 carry-over from cycle 68
per BACKLOG comment) and EXTENDS the first to lock in the cycle-69
deletions per amendments A4 (AC03/AC04 substrings) and A5 (AC22
duplicate_slug substring).
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKLOG_PATH = PROJECT_ROOT / "BACKLOG.md"

DELETED_ENTRIES = (
    # Cycle 68 cleanup (cycle-67 audit pass)
    "GitPython>=3.1.47` — only unpinned dependency",
    "_autouse_kb_path_sandbox` no-drop guard — silent breakage",
    "hardcoded lru_cache clear list",
    "_DEFAULT_MODEL_TIERS` dual mechanism",
    "_check_no_secrets_on_argv` self-DoS",
    "graph/cache.py` 6th-caller drift",
    "tests/test_cycle64_snapshots.py` tautology risk",
    "lacks an INDEX.md",
    # Cycle 69 cleanup (cycle-68 carry-over + cross-LLM-audited verified-stale)
    '`".." in page_id` is a substring match',  # AC03
    "graph/builder.py` non-lint `build_graph` callers",  # AC04
    "lint/checks/duplicate_slug.py` `check_duplicate_slugs`",  # AC22
)

DELETED_SELF_REFS = ("AC03", "AC07", "AC12")


def test_backlog_does_not_contain_shipped_phase_4_5_high_entries():
    """Cumulative cross-cycle lock-in — every cycle-67/68/69-audited stale BACKLOG
    entry has been removed.

    Cycle 69 amendments A4 + A5 extended this tuple with three new substrings
    locking in the AC03/AC04/AC22 deletions. A regression that re-adds any
    listed entry to BACKLOG.md trips this test.
    """
    backlog_text = BACKLOG_PATH.read_text(encoding="utf-8")
    found_stale = [s for s in DELETED_ENTRIES if s in backlog_text]
    assert not found_stale, "BACKLOG.md still contains stale entries:\n" + "\n".join(
        f"  - {s!r}" for s in found_stale
    )


def test_backlog_does_not_contain_cycle68_self_reference_section():
    """Cycle 69 AC01 — cycle-68 carry-over section has been deleted.

    Inverts the cycle-68 AC15b lock-in (which preserved the self-ref markers
    pending Step 17 doc-update). Cycle 69 ships the deletion.

    Asserts:
    1. The "CYCLE 68 carry-over" section heading is gone.
    2. The specific carry-over phrasing for each self-ref marker is gone
       (uses the unique "**AC03** (SHIPPED cycle 68" form so this test does
       not falsely trip on a future cycle's narrative reference to AC03).
    """
    backlog_text = BACKLOG_PATH.read_text(encoding="utf-8")
    assert "CYCLE 68 carry-over" not in backlog_text, (
        "BACKLOG.md still contains 'CYCLE 68 carry-over' section heading"
    )
    for marker in DELETED_SELF_REFS:
        bold_phrase = f"**{marker}** (SHIPPED cycle 68"
        assert bold_phrase not in backlog_text, (
            f"BACKLOG.md still contains cycle-68 self-ref phrase {bold_phrase!r}"
        )
