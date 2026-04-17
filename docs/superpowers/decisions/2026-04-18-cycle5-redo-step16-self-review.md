# Cycle 5 Redo — Step 16 Self-Review + Skill Patch

**Date:** 2026-04-18
**Owner:** Opus main (per feature-dev skill)

## Self-review scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 Requirements | yes | yes | — |
| 2 Threat model + CVE baseline | yes | yes | Opus architect surfaced an unanticipated 3rd-gap class: parallel loader implementations bypass canonical-loader greps |
| 3 Brainstorming | yes | yes | — |
| 4 Design eval (R1+R2 parallel) | collapsed to 5 | yes | Scope was small enough (6 tasks) that parallel R1+R2 eval was overkill — went straight to Opus decision gate |
| 5 Design decision gate (Opus) | yes | yes | CONDITIONAL-APPROVE with 6 conditions; Condition 1 (coordinate prompt + regex) caught the silent-regression risk that would have broken API-mode `extract_citations` |
| 6 Context7 verification | skip | — | No new library calls |
| 7 Implementation plan | inline | yes | Small enough scope to plan in the decision doc's "Final Decided Plan" table |
| 8 Plan gate | inline | yes | Self-gate: AC coverage + threat-item coverage both complete |
| 9 Implementation (TDD) | yes | yes | Mode A serial (6 tasks, interrelated files); legacy negative-assert broke as user-memory predicted and was updated in same commit |
| 10 CI hard gate | yes | yes | 1836 tests green after implementation, 1837 after R1 Unicode pin |
| 11 Security verify | yes | **no** | **Surfaced a 3rd cycle 5 gap** — `lint/augment.py:_build_proposer_prompt` bypassed `wrap_purpose`. Neither the Step 7 plan nor the 15 hardening tests had covered this callsite. Fixed inline + regression test added. |
| 12 Doc update | yes | yes | CHANGELOG Cycle-5-redo subsection; CLAUDE.md 1820 → 1836 tests |
| 12.5 Class A CVE patch | skip | — | 3 pre-existing advisories (diskcache, pip self-refs) with no action this cycle — unchanged from cycle 5 baseline |
| 13 Branch + PR | yes | yes | PR #19 opened with full summary + 3 decision-doc refs |
| 14 PR review R1+R2 | yes | yes | R1 Codex APPROVE + Sonnet APPROVE (1 LOW — Unicode pin test, addressed); R2 Codex APPROVE |
| 15 Merge + cleanup | yes | yes | Squash-merged; main at 1837 tests post-merge |
| 16 Self-review + skill patch | **this doc** | yes | Skill patched in-place; skills dir isn't a git repo on this host so recording the change here for audit trail |

## Skill patch recorded

Added to `C:\Users\Admin\.claude\skills\feature-dev\feature-dev-Opus4.6.md` Red Flags table:

> **"Step 7 plan grep'd every caller of `load_X` — coverage complete"** → **Parallel implementations bypass canonical loader greps.** Lesson from 2026-04-18 cycle 5 redo Step 11: threat model said "wrap_purpose must be called from every caller of `load_purpose`"; the Step 7 plan and all 15 hardening tests cleared that check. Step 11 security verify grep surfaced `lint/augment.py:_load_purpose_text` — a SEPARATE loader that reads `wiki/purpose.md` directly, bypassing `load_purpose` AND the `wrap_purpose` hardening. Rule: when the threat model protects an input-sanitization helper (`wrap_purpose`, `yaml_escape`, `_strip_control_chars`, etc.), Step 11's grep must use the DATA SOURCE (`wiki/purpose.md`, `raw/articles/`, etc.) as the search key, NOT just the canonical loader. Parallel file-reads to the same data source are the actual gap — the canonical loader is just one of them.

## Meta-lesson about this redo

The process itself caught a bug the original cycle didn't. Cycle 5 shipped 14 items with 15 tests and passed ruff + 1820 tests; all surface signals were green. The proper Step 2 threat model + Step 5 design gate + Step 11 security verify surfaced:

1. A real asymmetry bug (citation format mismatch between MCP and API modes) — caught at Step 2, fixed in T1.
2. A consistency bug (double-gate page-id length) — caught at Step 2, fixed in T3.
3. A third-callsite bypass (`lint/augment.py`) — caught at Step 11, not Step 2. **The threat model's checklist item was ambiguous enough that it cleared without catching this gap**, and only the broader Step 11 grep-by-data-source surfaced it.

The skill update codifies this: next time, Step 11 (and thus the Step 2 checklist feeding it) must grep by DATA SOURCE, not just canonical loader.

## Artifacts produced this cycle (all committed)

- `docs/superpowers/decisions/2026-04-18-cycle5-redo-requirements.md`
- `docs/superpowers/decisions/2026-04-18-cycle5-redo-threat-model.md`
- `docs/superpowers/decisions/2026-04-18-cycle5-redo-design.md`
- `docs/superpowers/decisions/2026-04-18-cycle5-redo-step16-self-review.md` (this file)
- `tests/test_cycle5_hardening.py` (16 tests)
- Source changes: `query/engine.py`, `query/citations.py`, `mcp/app.py`, `lint/augment.py`, `utils/text.py`, `tests/test_v0913_phase394.py`
- Doc updates: `CHANGELOG.md`, `CLAUDE.md`

## Not applicable (no action)

- `BACKLOG.md` — no new backlog items surfaced; no cycle-5-era items were shipped-but-open to delete.
- Architecture diagram — no architectural shift.
- Dep bumps — none.
