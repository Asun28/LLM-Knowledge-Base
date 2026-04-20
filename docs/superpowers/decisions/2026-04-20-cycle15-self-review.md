# Cycle 15 — Step 16 Self-Review

**Date:** 2026-04-20
**Cycle:** 15 — backlog-by-file batch, wiring cycle-14 helpers + volatility multiplier + new lint checks.
**PR:** #29 (merged as `e7638e3`).
**Branch:** `feat/backlog-by-file-cycle15` (deleted post-merge).
**Commits:** 8 on branch (6 TASK + 1 R1 fix + 1 R3 nit fix + 1 docs) = merged as 1 PR.
**Tests:** 2245 → 2334 collected (+89); 2327 runtime + 7 skipped.
**Scope:** 26 ACs (of 32 drafted; 6 dropped at Step 5 gate).

## Step scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 Requirements | yes | yes | — |
| 2 Threat model | yes | yes | 10 items + 8 AC amendments |
| 3 Brainstorming | yes | yes | Approach A selected; 8 open Qs |
| 4 Design eval (Opus R1 + Codex R2) | yes | yes | R1 flagged 6 REJECTs (big finds — see lessons) |
| 5 Decision gate | yes | yes | 26 ACs survived; 6 dropped |
| 6 Context7 | skipped | — | pure stdlib + internal code |
| 7 Plan (primary) | yes | yes | followed cycle-14 L1 heuristic |
| 8 Plan gate | yes | yes | PLAN-AMENDS-DESIGN-DISMISSED |
| 9 Implementation | yes | yes — except two cascade-test failures on pre-existing code | pre-existing brittle tests (cycle-11 `20260101` + cycle-3 `test_tier1_budget_allows_multiple_small_summaries`) surfaced under my changes — both fixed inline |
| 10 CI gate | yes | yes | 2327 passing + 7 skipped + ruff clean |
| 11 Security verify | yes | yes — with 2 PARTIAL process gaps (not contract deviations) | Codex reported PARTIAL due to missing baseline file + 5-vs-6 commit count; non-AC gaps |
| 11.5 CVE patch | skipped | — | 0 Class A alerts |
| 12 Docs | yes | yes | — |
| 13 PR open | yes | yes | PR #29 |
| 14 R1 PR review | yes | yes | R1 Codex APPROVE; R1 Sonnet 2 MAJOR + 3 MINOR |
| 14 R2 PR review | yes | yes | R2 Codex APPROVE |
| 14 R3 PR review | yes | yes — with 1 doc nit | R3 caught CHANGELOG test count drift (2327 vs 2334 collected) |
| 15 Merge + cleanup | yes | yes | 0 new post-merge Dependabot alerts |

## Lessons learned

### L1 — Design-eval R1 Opus catches pre-shipped ACs when grep-verifying every symbol

**Observation.** R1 Opus rejected AC18 + AC19 because `load_all_pages` already emitted `authored_by` and `belief_state` keys (shipped in cycle-14 AC23 at `utils/pages.py:163-164`). R1 Opus also rejected AC1 because `_flag_stale_results` does NOT use `STALENESS_MAX_DAYS` — the AC text mis-described current semantics. R1 Opus also caught AC8 category error (`suggest_new_pages` returns dead-link targets, which have no frontmatter for `status` to apply to).

**Why this worked.** Instead of generating cover-all verdicts, R1 Opus performed grep verification on every cited symbol BEFORE scoring each AC. The grep hits surfaced the cycle-14-already-shipped claim and the AC1 semantic mismatch. Without grep verification, these would have landed in Step 7 plans and burned a full implementation task before surfacing.

**Rule to patch into feature-dev SKILL.md Step 4:** when dispatching the R1 Opus design-eval subagent, the prompt MUST include a symbol-verification checklist requiring grep hits per cited function/constant BEFORE scoring any AC. Red-flag cycle: "AC text claims X is hardcoded" → grep MUST prove X is actually the current code path. Cycle-15 caught 3 design errors this way (AC1 semantics, AC8 category, AC18/19 duplicates).

**Skill patch location:** feature-dev SKILL.md Step 4 Design Eval — add a "Symbol verification gate" bullet under the R1 Opus prompt template.

### L2 — Post-gate AC dispositions: DROP ≠ REJECT — keep the regression test when the production code already shipped

**Observation.** AC18/AC19 dropped production-side (duplicate work), but AC32 (the test for AC18/19) was KEPT as a machine-checked cycle-14 contract regression. This paid off in R3 verification: the test serves as the anchor that any future refactor dropping `authored_by`/`belief_state` from `load_all_pages` will trip.

**Rule.** When Step-5 decision gate DROPs an AC because the production code already shipped in a prior cycle, KEEP the corresponding test AC as a contract regression. Never drop both — the test becomes the machine-checked anchor for the prior cycle's invariant. Cycle-14 L3 lesson (loader-side atomic fields ship together) is now machine-enforced via AC32 for future cycles.

**Skill patch location:** feature-dev SKILL.md Step 5 — add a sub-bullet under the "DROP" option about keeping the test anchor when production code is already shipped.

### L3 — Double-partition bug caught by R1 Sonnet edge-case review, not by CI or R1 Codex arch review

**Observation.** R1 Codex (architecture focus) APPROVED with 0 issues. R1 Sonnet (edge-case focus) caught a MAJOR: all three publish builders called `_partition_pages(pages)` twice — once before the skip check (return value discarded), once after. The "T2 filter runs before skip" comment I wrote was aspirational — in the skip case, partitioning never happened for the caller. The first call was dead code.

**Why R1 Codex missed it.** Codex arch review focused on contract adherence (cycle-14 pattern match), integration (imports wired correctly), and same-class completeness (all 3 builders patched). Codex did NOT run the skip-path end-to-end and observe that the first `_partition_pages` call had no downstream consumer. Sonnet's edge-case focus ("what happens when skip fires?") caught the dead-code pattern.

**Rule.** Dual-reviewer pattern (Codex arch + Sonnet edge-case) catches different classes of bugs. Do NOT short-circuit to single-reviewer on "small" cycles — even a 6-file cycle can hide a dead-code-with-misleading-comment pattern that arch review approves.

**Generalisation:** any function that takes a value-returning pure helper, discards its result, and then calls the same helper again should set off a Red Flag. Add to SKILL.md Red Flag table: "Called `_pure_helper(x)` and discarded result, then called `_pure_helper(x)` again — the first call is dead code; unpack once."

**Skill patch location:** feature-dev SKILL.md Red Flags table — add "Dead double-call of a pure helper".

### L4 — CHANGELOG test count drift caught only by R3 independent review

**Observation.** R1 Sonnet (edge-case) and R2 Codex (R1 fix verify) both focused on code/tests. Neither cross-checked the CHANGELOG header line against `pytest --collect-only`. R3 Sonnet (independent verify) caught it: CHANGELOG claimed "2245 → 2327 (+82)" but actual collected was 2334 (+89). The drift happened because Step 12 docs were drafted BEFORE the R1 fix commit added 1 new test; the runtime count (2327 passed + 7 skipped) is not the same as the collected count (2334 including some skipped/deselected).

**Rule.** Step 12 docs agent should run `pytest --collect-only | tail -1` and cite THAT number as the test count, not the runtime "passed + skipped" number. For a cycle with R1 fixes that add tests, re-run the collect count AFTER the fix commit before merging.

**Skill patch location:** feature-dev SKILL.md Step 12 — add sub-bullet: "use `pytest --collect-only | tail -1` for the CHANGELOG stat, not runtime pass count; re-verify after R1/R2 fixes".

## Cycle summary

- **21 ACs shipped straight from plan** (AC2, AC4, AC5, AC7, AC9, AC10, AC11, AC13, AC14, AC17 [dropped]→AC31 [moot]—kept test AC32, AC22, AC24, AC27, AC29, AC30, AC32 plus 4 infra ACs).
- **5 ACs amended from plan but still shipped** per Step 5 decisions.
- **6 ACs dropped at Step 5** (AC8, AC17, AC18, AC19, AC26, AC31) — all correctly dropped per grep evidence.
- **2 MAJOR + 3 MINOR R1 Sonnet findings** fixed in commit 065c1f0.
- **1 R3 doc nit** fixed in commit 1655f24.
- **Net code:** ~650 LoC source + ~1200 LoC tests across 11 new test files.
- **Test baseline:** 2245 → 2334 collected (+89); 2327 runtime pass.
- **CVE status:** Class A 0 (pre-merge + post-merge); Class B 0 (no new deps); pre-existing diskcache informational.
- **Post-merge alerts:** 0 (late-CVE check clean).

## Skill patches (to apply)

Four patches queued for `C:\Users\Admin\.claude\skills\feature-dev\SKILL.md`:

1. **L1** — Step 4 R1 Opus dispatch prompt must require grep-verification per symbol BEFORE scoring.
2. **L2** — Step 5 DROP option must explicitly KEEP the test AC when production already shipped.
3. **L3** — Red Flags table: "Dead double-call of a pure helper — unpack once."
4. **L4** — Step 12 doc-agent must use `pytest --collect-only | tail -1` for test count, and re-verify after R1/R2 fix commits.

Patch will be applied in a follow-up commit after this self-review lands.
