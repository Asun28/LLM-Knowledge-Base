# Cycle 5 Redo — Requirements + Acceptance Criteria

**Date:** 2026-04-18
**Context:** Cycle 5 (PR #18) shipped 14 items but shortcut the feature-dev pipeline — no Step 1 requirements doc, no Step 2 threat model artifact, no Step 4 design eval, no Step 5 decision gate doc, no Step 7 plan artifact, no Step 8 plan gate verdict, and only 1 round of PR review (spec requires 2). The `wrap_purpose` newline-stripping bug caught in R1 is direct evidence of gaps the missing process would have prevented.

## Problem

Cycle 5's 14 items are correctly shipped in source code but lack the process artifacts the feature-dev skill prescribes. This creates three concrete risks:

1. **Threat coverage uncertainty.** No documented threat model for the 14 changes means no checklist to audit against at Step 11. Control-char rejection, purpose sentinel, and citation format all have security implications that were not formally reasoned about.
2. **Design decision opacity.** Chose reject-with-error for control chars over silent strip; chose wikilink format over post-synthesis linker; chose in-place purpose sentinel over pre-LLM sanitization — these were judgment calls with no written rationale, making them hard to revisit or defend under review.
3. **Test coverage gaps.** The R1 newline-stripping bug landed because tests covered only `\x00`-`\x02` control chars, not the full C0 range. Parallel gaps may exist for the other 13 items.

## Non-goals

- Do NOT revert any cycle 5 code. The fixes are correct in direction.
- Do NOT re-implement items that are already working.
- Do NOT introduce new features. This is a process-compliance and hardening pass.
- Do NOT open PRs against already-closed backlog items (all 14 are closed).

## Acceptance criteria

Each criterion testable as pass/fail:

| # | Criterion | Verification |
|---|-----------|-------------|
| AC1 | Threat model doc exists covering all 14 cycle 5 items' trust boundaries, data classification, and audit needs | File at `docs/superpowers/decisions/2026-04-18-cycle5-redo-threat-model.md` with 1 row per item |
| AC2 | Design decision doc records per-item rationale (why reject vs strip, wikilink vs linker, etc.) | File at `docs/superpowers/decisions/2026-04-18-cycle5-redo-design.md` with VERDICT/DECISIONS/CONDITIONS blocks |
| AC3 | Every cycle 5 item has end-to-end wiring verified (not signature-only tests) | Codex security verify report lists IMPLEMENTED for all 14 items |
| AC4 | Test coverage extends beyond happy path for each item | New tests in `tests/test_cycle5_hardening.py` exercise edge cases: full C0 range, Unicode entity names, whitespace-only page_id, empty User-Agent version, nested purpose sentinels |
| AC5 | Any bug found gets a regression test that fails pre-fix | `git log` shows paired test+fix commits |
| AC6 | Full test suite passes with ruff clean | `python -m pytest -q` → 1821+ passed, `ruff check` clean |
| AC7 | 2-round PR review recorded (R1 parallel Codex+Sonnet, R2 Codex) | PR comments show both rounds; each blocker has a fix commit |
| AC8 | Docs synchronized: CHANGELOG entry for hardening pass, BACKLOG unchanged (no new items unless found), CLAUDE.md counts accurate | `git diff` on merge shows the three doc files touched appropriately |

## Blast radius

- `src/kb/` — potentially touched: `utils/text.py` (wrap_purpose hardening), `ingest/pipeline.py` (word-boundary edge cases), `mcp/app.py` (control-char edge cases), `mcp/core.py` (citation format), `utils/llm.py` (User-Agent format). No new modules.
- `tests/` — new file `test_cycle5_hardening.py` and possibly additions to `test_v09_cycle5_fixes.py`.
- `docs/superpowers/decisions/` — 3 new markdown artifacts (requirements, threat model, design).
- `CHANGELOG.md` + `BACKLOG.md` + `CLAUDE.md` — small updates.

## Feeds Step 4 (design eval scoring)

Design options must score against AC1-AC8. An option that ships less than AC1+AC2 fails even if code is cleaner.

## Feeds Step 8 (plan coverage check)

Every task in Step 7 plan must reference at least one AC. Every AC must have at least one task.
