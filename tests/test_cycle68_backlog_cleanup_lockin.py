"""Cycle 68 AC15b — BACKLOG.md cleanup lock-in regression (R1-F5 + FW-10).

Locks AC10's deletion of stale Phase 4.5 / Phase 6 R2 entries against future
re-introduction. The cycle-68 self-reference entries (AC03 / AC07 / AC12
carry-over markers) are NOT deleted at AC10 per FW-9 — Step 17 doc-update
deletes them post-merge. This file pins both invariants.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKLOG_PATH = PROJECT_ROOT / "BACKLOG.md"

DELETED_ENTRIES = (
    "GitPython>=3.1.47` — only unpinned dependency",
    "_autouse_kb_path_sandbox` no-drop guard — silent breakage",
    "hardcoded lru_cache clear list",
    "_DEFAULT_MODEL_TIERS` dual mechanism",
    "_check_no_secrets_on_argv` self-DoS",
    "graph/cache.py` 6th-caller drift",
    "tests/test_cycle64_snapshots.py` tautology risk",
    "lacks an INDEX.md",
)

PRESERVED_SELF_REFS = ("AC03", "AC07", "AC12")


def test_backlog_does_not_contain_shipped_phase_4_5_high_entries():
    """AC15b — every cycle-67-audited stale BACKLOG entry has been removed."""
    backlog_text = BACKLOG_PATH.read_text(encoding="utf-8")
    found_stale = [s for s in DELETED_ENTRIES if s in backlog_text]
    assert not found_stale, "BACKLOG.md still contains stale entries:\n" + "\n".join(
        f"  - {s!r}" for s in found_stale
    )


def test_backlog_preserves_cycle68_self_reference_entries():
    """AC15b / FW-9 — AC10 must NOT over-delete cycle-68 self-reference entries.

    Step 17 doc-update deletes AC03/AC07/AC12 markers post-merge; AC10 only
    cleans cycle-67-audited stale entries.
    """
    backlog_text = BACKLOG_PATH.read_text(encoding="utf-8")
    assert "CYCLE 68 carry-over" in backlog_text, (
        "BACKLOG.md missing 'CYCLE 68 carry-over' section — FW-9 over-deletion"
    )
    for marker in PRESERVED_SELF_REFS:
        bold_marker = f"**{marker}**"
        assert bold_marker in backlog_text, (
            f"BACKLOG.md missing cycle-68 self-ref {bold_marker} — FW-9 violation"
        )
