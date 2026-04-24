"""Cycle 29 AC3 + AC4 + AC5 — documentation hygiene source-scan tests.

Source-scan tests in the cycle-11 L2 family are generally discouraged, but
these are the ACCEPTED escape hatch: the assertion IS the doc-hygiene
presence check. Reverting the comment or re-adding the BACKLOG bullet MUST
fail the paired test (divergent-fail property preserved per R1 Opus eval).

Split from `test_cycle29_rebuild_indexes_hardening.py` per design Q14: source-
scan and integration shapes have different reload-leak surfaces; isolating
the scan shape here keeps any monkey-patched import in the hardening file
from contaminating the bare-read tests here (cycle-19 L2).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# AC3 — CAPTURES_DIR carve-out comment + BACKLOG:196-197 delete
# ---------------------------------------------------------------------------


def test_captures_dir_has_carve_out_comment():
    """AC3 — at least 3 distinct architectural tokens precede CAPTURES_DIR line.

    C9 distinct-token count: the 6 lines immediately above
    ``CAPTURES_DIR = RAW_DIR / "captures"`` must contain at least 3 of the
    architectural tokens {LLM-written, carve-out, kb_capture, raw input
    for subsequent ingest}. Matches the requirement's disambiguated form
    per R1 Opus AMEND.
    """
    src = (PROJECT_ROOT / "src" / "kb" / "config.py").read_text(encoding="utf-8")
    lines = src.splitlines()
    idx = next(
        (
            i
            for i, line in enumerate(lines)
            if line.strip().startswith('CAPTURES_DIR = RAW_DIR / "captures"')
        ),
        None,
    )
    assert idx is not None, "CAPTURES_DIR line not found in config.py"
    preceding = "\n".join(lines[max(0, idx - 6) : idx])
    tokens = {"LLM-written", "carve-out", "kb_capture", "raw input for subsequent ingest"}
    matched = {t for t in tokens if t in preceding}
    assert len(matched) >= 3, (
        f"AC3: at least 3 distinct tokens from {tokens} must appear in the "
        f"6 lines above CAPTURES_DIR; matched only {matched} in preceding:\n{preceding}"
    )


def test_captures_backlog_carveout_entry_deleted():
    """AC3 (Q13 expansion) — BACKLOG.md:196-197 carveout bullet deleted.

    The `config.py:40-53` line-number substring was unique to the stale
    bullet (the actual CAPTURES_DIR declaration is at line 80). Reverting
    the deletion re-adds the substring and flips this assertion.
    """
    backlog = (PROJECT_ROOT / "BACKLOG.md").read_text(encoding="utf-8")
    assert "config.py:40-53" not in backlog, (
        "AC3: BACKLOG.md:196-197 carveout bullet must be DELETED (cycle-29 Q13); "
        "fix is shipped (config.py:80 comment + CLAUDE.md raw/ carve-out), so "
        "the BACKLOG entry is stale."
    )


# ---------------------------------------------------------------------------
# AC4 — stale _PROMPT_TEMPLATE BACKLOG bullet delete
# ---------------------------------------------------------------------------


def test_captures_backlog_entry_deleted():
    """AC4 — stale _PROMPT_TEMPLATE bullet deleted from BACKLOG.md.

    Cycle-19 AC15 already migrated the inline prompt string to a lazy
    `_get_prompt_template()` loader reading `templates/capture_prompt.txt`
    (see `src/kb/capture.py:313-318`). The BACKLOG bullet describing the
    pre-cycle-19 state is therefore stale.

    Uses the tight phrase verbatim from the stale bullet (including the
    inline-code backticks and the pre-migration file-line citation) per
    R1 Opus AMEND (C11): a future cycle legitimately referencing
    `_PROMPT_TEMPLATE` as a module cache variable would not collide with
    this assertion. Pre-delete state contains the substring; post-delete
    state does not (cycle-28 L2 divergent-fail anchor).
    """
    backlog = (PROJECT_ROOT / "BACKLOG.md").read_text(encoding="utf-8")
    needle = "`_PROMPT_TEMPLATE` inline string vs templates/"
    assert needle not in backlog, (
        "AC4: stale _PROMPT_TEMPLATE bullet must be DELETED (cycle-19 AC15 shipped)"
    )


# ---------------------------------------------------------------------------
# AC5 — stale Phase 4.5 HIGH #6 cold-load bullet delete
# ---------------------------------------------------------------------------


def _extract_high_section(backlog: str) -> str:
    """Return the text of `### HIGH` section under `## Phase 4.5`, stopping
    before `### HIGH — Deferred` (which must retain its cold-load latency
    language — C12 requires the assertion to fire only against the HIGH
    bullet list, not the HIGH-Deferred summary).
    """
    # Find the Phase 4.5 heading first, then the `### HIGH` (not `### HIGH — Deferred`) inside.
    phase_idx = backlog.find("## Phase 4.5")
    if phase_idx < 0:
        return ""
    section = backlog[phase_idx:]
    # Start of `### HIGH\n` (no suffix after HIGH).
    high_start = section.find("### HIGH\n")
    if high_start < 0:
        return ""
    # End at next `### ` heading (HIGH — Deferred, MEDIUM, LOW, etc.).
    high_end = section.find("### ", high_start + len("### HIGH\n"))
    return section[high_start:high_end] if high_end > 0 else section[high_start:]


def test_cold_load_high_entry_deleted():
    """AC5 — stale HIGH #6 cold-load bullet deleted from the HIGH section.

    The Phase 4.5 HIGH bullet described the unmitigated 0.81s cold-load +
    67 MB RSS delta + "hybrid silently degrades to BM25" problem. Cycle-26
    AC1-AC5 shipped `maybe_warm_load_vector_model` + MCP-boot warm-load +
    `_get_model` latency instrumentation; cycle-28 AC1-AC5 extended the
    observability to sqlite-vec + BM25. The HIGH bullet is therefore
    stale; HIGH-Deferred at the adjacent section authoritatively captures
    the remaining dim-mismatch AUTO-rebuild residue.

    Section-scoped per C12 — the HIGH-Deferred bullet uses
    `"cold-load latency"` phrasing which does NOT match either banned
    substring, so it survives unchanged.
    """
    backlog = (PROJECT_ROOT / "BACKLOG.md").read_text(encoding="utf-8")
    high_section = _extract_high_section(backlog)
    assert high_section, "AC5: could not locate Phase 4.5 ### HIGH section (extraction failed)"
    banned = ("0.81s + 67 MB", "cold load — measured")
    for needle in banned:
        assert needle not in high_section, (
            f"AC5: stale cold-load bullet must be DELETED from Phase 4.5 HIGH "
            f"section (cycle-26/28 shipped warm-load + observability); found "
            f"substring {needle!r} still present."
        )

    # Dual-guard — HIGH-Deferred survives with its cold-load-latency language
    # (C12 sibling check; if this assertion ever flips, the deletion was too
    # aggressive and clobbered the authoritative summary).
    assert "cold-load latency" in backlog, (
        "C12 guard: HIGH-Deferred cold-load-latency summary must survive — "
        "deletion is scoped to the HIGH section only"
    )
