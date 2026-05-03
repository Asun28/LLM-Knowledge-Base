# Cycle 61 Design eval R2 (DeepSeek V4 Pro)

## Analysis

Adversarial review of 10 cross-family signal areas:

1. D2 gitignore contradiction vs AC7 "checked into git"
2. AC6 lazy-accessor function vs module-top variable ambiguity
3. AC9/AC10 snapshot semantics — false distinction
4. AC12/T12 material threat deferral without formalization
5. AC18 stub-test "different outcomes" — vague assertion
6. AC14-AC17 rework risk if fold cycle deletes versioned files
7. AC11 cycle-59 EOF format compatibility unverified
8. Cycle-62 parallel existence at d7a98b7 — uncoordinated
9. D5 assertion tautological (constant-protected)
10. D1+D2 interdependent, treated independently

## Findings

### Finding 1: D2 gitignore violation (AC7) — HIGH

D2 recommends wiki/_lint.yml. AC7 says "checked into git". But .gitignore:21 excludes wiki/. Contradiction.

Fix: Move to project_root/_lint.yml or docs/_lint.yml. Or add !wiki/_lint.yml exception.

### Finding 2: AC6 lazy-accessor underspecified — MED

AC6 says "introduce" but doesn't enforce @lru_cache function shape. Could be module-top variable (reload-leak).

Fix: Amend AC6: "Introduce @lru_cache-decorated function. Forbid module-top file-read."

### Finding 3: AC9/AC10 snapshot contradiction — HIGH

AC9 computes KB_DISABLE_VECTORS at config.py import (frozen). AC10 says read "at CALL time". Both are snapshots. T13 threat remains.

Fix: Make KB_DISABLE_VECTORS a @property that re-reads os.environ, OR reword AC10 to accept snapshot.

### Finding 4: AC12/T12 deferral without acceptance — HIGH

T12 is MATERIAL (Repudiation). AC12 omits caller="mcp" audit-tag. D4 defers without explicit AC12 acceptance.

Fix: Add to AC12: "T12 audit-tag deferred to BACKLOG per D4; Step 14 verifies gap filed." Or implement now.

### Finding 5: AC18 divergence assertion vague — LOW

AC18 says "different prune outcomes" but doesn't define "different". Could pass on accidental divergence.

Fix: Specify: "Assert stale entry NOT pruned (len==0) after no-op, proving load-bearing."

### Finding 6: AC14-AC17 versioned files rework risk — MED

Upgrading inspect.getsource → behavioral in versioned test files (v092, v0911, v0915). Fold cycle may delete these files.

Fix: Check fold roadmap. Defer AC14-AC17 to fold cycle if applicable.

### Finding 7: AC11 cycle-59 EOF marker unverified — HIGH

AC11 appends to test_query.py. Cycle-59 also appends ~600 lines to same file. EOF marker format compatibility not verified.

Fix: Step 7 task: inspect cycle-59's EOF marker style. Align AC11. Document in design.

### Finding 8: Cycle-62 exists uncoordinated — HIGH

git worktree list shows cycle-62 at d7a98b7 (base). Design assumes cycle-59→61 linearity. Parallel cycle may claim Steps 9,17,20+.

Fix: Check cycle-62 scope. If overlapping, synchronize. Establish file/step ownership.

### Finding 9: D5 assertion redundant — LOW

D5 extends test to assert sandbox flags. But CLI_TOOL_COMMANDS["codex"] (immutable constant) already guarantees them. Tautology.

Fix: Drop assertion. Test constant composition separately if runtime variation is a concern.

### Finding 10: D1+D2 interdependent, unreconciled — HIGH

D1 recommends config.py location. D2 recommends wiki/_lint.yml (not config.py). If D2 chosen, D1 is moot. Design doesn't reconcile.

Fix: State: "D2 chosen. D1's config.py location NOT implemented." Update AC6/AC7 to wiki/_lint.yml only.

## Conditions for plan-gate

1. Resolve D2 gitignore (F1)
2. Enforce AC6 function shape (F2)
3. Resolve AC9/AC10 snapshot (F3)
4. Formalize AC12/T12 deferral (F4)
5. Specify AC18 assertion (F5)
6. Coordinate AC14-AC17 fold timing (F6)
7. Verify cycle-59 EOF format (F7)
8. Coordinate cycle-62 scope (F8)
9. Drop/justify D5 assertion (F9)
10. Reconcile D1/D2 (F10)

## Verdict

NEEDS_REVISION

10 gaps identified. 6 are HIGH-severity (F1,F3,F4,F7,F8,F10). Design otherwise sound but requires explicit reconciliation of interdependencies before Step 7 plan-gate.
