# Cycle 10 — Step 16 Self-Review

**Date:** 2026-04-18
**PR:** #24 (merged at commit `5197fe0`)
**Commits shipped:** 17 total (13 code/test + 4 docs/audit)
**Test count:** 2004 → 2038 passing, +7 skipped (+34 net new tests, covering 33 ACs)
**Dependabot alerts:** 0 open at baseline; 0 open post-merge; diskcache CVE-2025-69872 remains (no upstream patch; tracked in BACKLOG).

## Scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 — Requirements + AC | yes | no (revised 28 → 33 after grep-verify) | wiki_log + kb_search ACs were STALE — already fixed in cycle 2 + R4 HIGH. Dropped mid-Step-1. |
| 2 — Threat model + CVE baseline | yes | yes | Threat model ran against 33-AC draft; I downsized to 28 before Step 5 and the threat model doc stayed partly stale until Step 5 reconciled. |
| 3 — Brainstorm | yes | yes (compact self-brainstorm, no interactive skill since cycle is cleanup-class) | — |
| 4 — Design eval (2 rounds) | yes | yes (Opus R1 + Codex R2 in parallel) | R2 Codex correctly caught `_validate_wiki_dir` lacks PROJECT_ROOT containment AND hybrid_search is dead code for production — two blockers I would've missed without R2. |
| 5 — Decision gate | yes | yes (10 open questions resolved autonomously, one Opus dispatch) | AC count grew 28 → 33 via AC0 (harden helper), AC1b (same-class kb_affected_pages), AC28.5 (pipe escape bonus). Same-class completeness + grep-verify Red Flags from cycles 8+9 fired as designed. |
| 6 — Context7 verify | skipped | n/a | pure stdlib (`secrets`, `datetime`, `pathlib`) + internal kb symbols; skill allows skip. |
| 7 — Plan | yes | no | first plan draft listed 10 commits; Step 8 gate flagged AC13 dual-mechanism collapse + AC28.5 target drift + threat out-of-scope gap + TASK 8 assertion breadth. |
| 8 — Plan gate | yes | no (REJECT PLAN-AMENDS-DESIGN first try) | 4 blockers closed by inline plan edits (no Step 5 re-run needed). Cycle-9 dual-mechanism Red Flag fired and prevented AC13a/AC13b silent collapse. |
| 9 — TDD implementation | yes | mostly (TASK 4 hit pre-existing cycle-8 test assertion drift requiring a constraint extension) | TASK 4 Codex halted on a cross-cycle assertion drift in `tests/test_cycle8_health_wiki_dir.py`; I had to explicitly allow the compat test update. TASK 5 bonus-migrated `kb_verdict_trends` as a side-effect of fixing the drift. |
| 10 — CI hard gate | yes | no | 2 ruff check errors + 17 files needed `ruff format`. Per-task Codex commits skipped formatting; bundled into `ea102f3`. |
| 11 — Security verify + PR-CVE diff | yes | no (FAIL verdict first try) | 2 security blockers: (a) `_wiki_dir_for_legacy_threading_test` test-accommodation bypass introduced by TASK 5, (b) hard-coded `/home/user/secret/path/feedback.json` in test fixture triggered generic-path-literal flag. Both closed in `1c3832e`. CVE diff: empty. |
| 11.5 — Existing-CVE opportunistic patch | yes | yes (no-op: diskcache CVE has no upstream patch) | — |
| 12 — Doc update | yes | yes | CHANGELOG + BACKLOG clean; `raw/captures/` + drift docstring already landed in TASK 8 commit per Q10 decision. |
| 13 — Branch finalise + PR | yes | yes | PR #24 opened cleanly with full review trail + commit timeline. |
| 14 — PR review (2 rounds) | yes | no (R1 APPROVE-WITH-REVISIONS with 2 Majors + 1 Nit from Codex AND 2 Majors + 2 Nits from Sonnet; R1 fix commit + R2 NEW ISSUE + CHANGELOG note residual; R2 fix commit) | R1 Codex caught RRF skew (intentional, documented). R1 Sonnet caught THREAD-SAFETY RACE on `mcp_app.PROJECT_ROOT` mutation — a real bug. R2 caught NEW regex-order regression when extracting `sanitize_error_text`. |
| 15 — Merge + cleanup + late-arrival CVE warn | yes | yes | Clean ff-merge. Remote branch auto-deleted by GitHub on merge (hence the expected `remote ref does not exist` on the explicit delete). Post-merge Dependabot: 0 alerts. |
| 16 — Self-review + skill patch | yes | yes | This file. |

## Lessons learned

### L1 — Threat model against an unlocked AC set gets stale fast
The Step 2 threat model was dispatched BEFORE my requirements doc revision (33 → 28 ACs) and produced a CHECKLIST referencing dropped ACs (AC28, AC29, AC32, AC33). Both design-eval reviewers correctly flagged this. Cost: moderate confusion; no blocker, because Step 5 decision gate reconciled. **Pattern for next cycle:** run Step 2 threat model AFTER Step 1 requirements are grep-verified and locked, not in parallel with Step 1 revisions. Alternative: instruct the threat model subagent to accept a "ACs may revise post-dispatch" preamble and regenerate if the AC set drifts >10%.

### L2 — "Same-class completeness" Red Flag is load-bearing
Cycle 9's Red Flag about scope-outs needing explicit enumeration fired TWICE in cycle 10: (a) R1 Opus caught that AC1 only closed 1 of ~2-3 silent-degradation sites → led to AC1b (`kb_affected_pages` shared-sources); (b) Codex R1 caught cycle-7 callers weren't re-tested under the new sanitised error contract → led to R1 fix's caller-boundary regression tests. Both catches prevented real regressions. **Recommendation:** add to the Step 5 decision-gate prompt a mandatory "enumerate the SAME-CLASS CALL SITES being scoped OUT with 1-line justification for each" section. Currently that's a Red Flag table check; promoting it to a mandatory decision-gate output section makes it harder to skip.

### L3 — Test-accommodation bypasses introduced during TDD get flagged by security verify
During TASK 5, Codex introduced `_wiki_dir_for_legacy_threading_test` in `mcp/health.py` to accommodate legacy tests that monkeypatched `export_mermaid` / `detect_source_drift`. That helper returned `Path(wiki_dir)` unvalidated — a path-traversal bypass that Step 11 security verify caught. **Pattern to codify:** when Step 9 Codex encounters a test-assertion drift during TDD implementation, the correct response is to UPDATE THE TEST (as in TASK 4's `tests/test_cycle8_health_wiki_dir.py`), not to INTRODUCE A BYPASS in production code. Codex's default behaviour was reasonable (preserve test-green invariant) but wrong for security-class changes. Worth a dedicated Red Flag row: "Step 9 introduces a helper-with-bypass to keep legacy tests green → that helper IS the bug; update the tests instead."

### L4 — R1 Sonnet catches concurrency bugs R1 Codex misses
Sonnet M1 (thread-race on `mcp_app.PROJECT_ROOT` mutation) was invisible to Codex R1's architecture/contract pass but obvious to Sonnet R1's concurrency-focused prompt. Same pattern as cycle 6 (sqlite3 thread-affine connection) and cycle 9 (vacuous test gate). **Recommendation:** continue running the Codex+Sonnet parallel pair in Round 1; the orthogonal focus dimensions keep paying off. Cost is ~3 min wall-clock, payoff is 1 concurrency-class bug per cycle caught.

### L5 — Regex order breaks during extraction-refactor
R2 caught a NEW issue where extracting `sanitize_error_text` from `_sanitize_error_str` moved per-path substitution AFTER the regex sweep, silently rewriting explicit-path args to `<path>` instead of the intended relative form. **Pattern:** when extracting a helper from an existing function whose body has ORDERED operations (per-path substitution → filename substitution → regex sweep), the extracted helper must preserve the same order. Cheap way to catch this in future cycles: require at least one unit test of the extracted helper that exercises ALL steps of the original function in sequence — if the order is reversed, the test fails.

## Proposed feature-dev skill patches

### Patch 1 — Red Flag: test-accommodation bypass during TDD

Add row to Red Flags table in `feature-dev/SKILL.md`:

> | "My Step-9 task needs a helper that returns the raw input unchanged when tests monkeypatch the target — just so legacy tests pass" | **Step-9 test-accommodation bypasses ARE the bug, not a feature.** Lesson from 2026-04-18 cycle 10 TASK 5: Codex introduced `_wiki_dir_for_legacy_threading_test` in `mcp/health.py` to return `Path(wiki_dir)` unvalidated when tests monkeypatched `export_mermaid` / `detect_source_drift`. Step 11 security verify correctly flagged it as a path-traversal bypass. Rule: when Step 9 Codex encounters a test-assertion drift that depends on a helper returning un-validated input, the FIX is to update the legacy test (as in cycle 10 TASK 4's `tests/test_cycle8_health_wiki_dir.py`), NEVER to introduce a bypass in production code. Explicit prompt to Step-9 Codex: "If a legacy test depends on bypass semantics, update the test to use the new production validator properly — do not add a production bypass." Self-check before commit: `grep -rnE "def _\w*_for_legacy|bypass|unsafe_" src/` in your diff should return zero hits. |

### Patch 2 — Red Flag: helper extraction preserves operation order

Add row to Red Flags table:

> | "I extracted this helper function from the larger body — same code, just moved" | **Extracting a helper from an ORDERED operation sequence silently reverses the order if you inline-return early.** Lesson from 2026-04-18 cycle 10 R2: extracting `sanitize_error_text` from `_sanitize_error_str` moved the per-path substitution AFTER the regex sweep, because the new helper ran its own regex sweep BEFORE being called by the old function's per-path loop. Callers that passed explicit `paths=` args got `<path>` masks instead of relative-form substitution. Rule: when extracting a helper from an ordered multi-step function (e.g., substitute-A → substitute-B → regex-sweep), the extracted helper must EITHER (a) take optional args and preserve the full sequence internally, OR (b) leave the original function's sequence untouched and only extract the INDIVIDUAL steps, not the final-step wrapper. Self-check: for any Step-9 or Step-14-fix commit that introduces a "move logic from function F to new helper H" change, write 1 unit test of H that exercises all N steps of F in their original order. If the assertion about step-order is reversed, the test fails. |

### Patch 3 — Workflow amendment: run Step 2 AFTER Step 1 grep-verify

Amend Step 1 / Step 2 section of feature-dev/SKILL.md:

> After Step 1 writes the requirements doc, **grep-verify every named function, line number, and symbol** before dispatching Step 2 threat model. Cycle 10 saw the threat model dispatched against a 33-AC draft that shrunk to 28 after grep-verify; the downstream threat CHECKLIST referenced AC28/AC29/AC32/AC33 that no longer existed. Fix: in Step 1's last paragraph, add a grep-verify checklist (every `mcp/*.py:LINE` reference, every helper symbol, every existing-feature claim). Only then dispatch Step 2. If grep-verify changes the AC set, STOP — rewrite Step 1 before firing Step 2.

## Red Flag patches to commit

Both patches land in `C:\Users\Admin\.claude\skills\feature-dev\SKILL.md`. Commit message:

```
skill(feature-dev): cycle 10 Red Flags — test-accommodation bypass + helper-extraction order
```

## Cycle 10 summary stats

- **ACs shipped:** 33 across 14 files (AC0, AC1, AC1b, AC1s, AC2 regression-pin, AC3-AC28.5)
- **Commits:** 17 total on branch
- **Tests:** +34 new passing + 7 skipped (FS-capability / symlink skips)
- **Files touched:** 16 source, 12 test, 3 doc (CHANGELOG, BACKLOG, CLAUDE.md), 11 decision-trail
- **Review rounds:** R1 (Codex+Sonnet parallel) → 4 Majors → R1 fix → R2 Codex → 1 OPEN + 1 NEW → R2 fix → clean APPROVE
- **Security blockers caught & closed:** 2 in Step 11 (+1 in R1 Sonnet M1 that would've become a concurrency bug post-merge)
- **Dependabot:** 0 → 0
- **Stale BACKLOG items surfaced:** 2 (torn-line wiki_log, kb_search stale marker + length cap) — deleted from BACKLOG as already-fixed.

**Overall:** 4 steps required rework (Steps 1, 7, 9, 11, 14). No step failed hard. Workflow end-to-end in ~3 hours wall-clock (including background subagent latencies).
