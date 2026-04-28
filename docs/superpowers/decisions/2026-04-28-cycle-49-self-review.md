# Cycle 49 — Self-review + skill patches

**Date:** 2026-04-28
**PR:** [#72](https://github.com/Asun28/llm-wiki-flywheel/pull/72) — squash-merged as `94d44a9`
**Branch:** `cycle-49-batch` (deleted post-merge)
**Worktree:** `D:/Projects/llm-wiki-flywheel-c49` (created at start, removed at end per C42-L4)
**Commits:** 6 implementation + 0 PR-fix (R1+R2 both APPROVE first-try) = 6 pre-merge total
**Wall-clock:** ~3.5h end-to-end (Step 1 → Step 15 cleanup)

---

## Step scorecard

| Step | Executed? | First-try? | Surprised by? |
|------|-----------|------------|---------------|
| 1 — Requirements + ACs | yes | yes | — |
| 2 — Threat model + dep-CVE baseline | partial (TM skipped per skip-eligibility, baseline captured) | yes | — |
| 3 — Brainstorming | yes | yes | — |
| 4 — Design eval R1 | yes | APPROVE-WITH-CONDITIONS (5 conditions) | **R1 missed AC3 host-shape (purely bare-function receiver); primary caught at receiver inspection between Step 4 and Step 5** → C49-L1 |
| 5 — Design decision gate | yes (primary-session per cycle-21 L1) | yes | — |
| 6 — Context7 | SKIP per skip-eligibility (no third-party libs) | n/a | — |
| 7 — Implementation plan | yes (primary-session per cycle-14 L1) | yes | — |
| 8 — Plan gate | yes (primary self-check per cycle-21 L1) | yes | — |
| 9 — Implementation | yes (primary-session per C37-L5) | yes | Each fold revert-verify took ~3 min wall-clock; clean cadence |
| 9.5 — Simplify | SKIP per skip-eligibility (zero src/ diff) | n/a | — |
| 10 — CI hard gate | yes | yes | 3014 passed + 11 skipped; ruff clean |
| 11 — PR-CVE diff | yes | yes | INTRODUCED=[] REMOVED=[] |
| 11.5 — Existing-CVE patch | SKIP per skip-eligibility (all advisories blocked-no-fix) | n/a | — |
| 12 — Doc update | yes | **partial — initial parallel Edit batch on CLAUDE.md/README.md failed "File has not been read yet"; required re-Read + re-Edit. CHANGELOG.md edit was missed entirely on first pass; caught via grep-verify (`grep -c "cycle 49" CHANGELOG.md` returned 0) and added in second pass.** Not a new lesson — existing rule "Read before Edit" applies. |
| 13 — Branch finalise + PR | yes | **`gh pr create` from main worktree CWD failed with "head branch 'main' is the same as base branch 'main'" — required explicit `--base main --head cycle-49-batch` flags** → C49-L2 |
| 14 — PR review (R1 DeepSeek + R2 Codex) | yes | both APPROVE | R2 dispatched same time as R1; R2 returned ~30s after R1 (274s vs ~270s); per-cycle-20 L4 manual verify executed in parallel during R2 wait, all 10 items pass |
| 15 — Merge + cleanup | yes | yes | Squash merge clean; worktree + branch removed; editable install restored to main |

**Steps with surprises:** 4 (R1 host-shape miss), 12 (Edit-without-Read drift on CHANGELOG.md), 13 (gh pr create CWD/branch mismatch). 12 of 15 steps ran clean first-try.

**Patterns to preserve (zero-surprise streak):**
- Primary-session for ≤15 ACs / 0 src files / primary holds context (C37-L5) — cycle 49 is the textbook case; confirmed faster + more accurate than dispatch.
- `assert False` revert-verify per C40-L3 — proves the moved test method is collected + run (not silently skipped). All 4 folds revert-verified in <30 seconds each.
- Direct DeepSeek CLI dispatch per cycle-39 L1 — R1 returned in ~7 min with structured per-AC scoring; no fabrication-preamble symptoms.
- Worktree-from-the-start per C42-L4 — main worktree never touched during cycle 49.
- Multi-site grep for count drift per C26-L2 + C39-L3 — caught the missing CHANGELOG.md entry on first verification pass.

---

## Skill patches

### C49-L1 — Step-4 R1 design-eval prompt MUST include host-shape inspection BEFORE scoring class-vs-bare-function ACs

**Refines C40-L5.** Cycle-40 L5 added "Source file inspection results" to Step-5 (design decision gate) prompts — but the receiver host-shape question lives EARLIER, at Step-4 (R1 design-eval). R1 DeepSeek for cycle 49 confirmed all 4 fold receivers existed (test_v070.py, test_capture.py) and confirmed semantic fit (MCP tests → test_v070.py is the right home), but did NOT report the receiver's STRUCTURAL shape (28 bare functions / 0 classes pre-cycle-49). The original AC3 design proposed wrapping a single test in a new class — host-shape mismatch with the purely bare-function receiver. R1 emitted APPROVE on AC3 because it scored the question "is this the right semantic home?" not "does this match the host-shape?" Primary caught the issue at receiver-inspection between Step 4 and Step 5; design-gate AMENDED AC3 from class to bare function.

**Self-check (concrete grep additions for Step-4 R1 prompt):** For each AC proposing a `class TestX:` wrapper in a receiver file, the R1 prompt MUST require:
```
For each receiver file cited by an AC, run:
  grep -c "^class " <receiver>     # class count
  grep -c "^def test_" <receiver>  # bare-function count
  grep -c "^    def test_" <receiver>  # method count

If class count >10 AND bare-function count <5 → receiver is class-shaped; class-wrapped AC is correct.
If class count <5 AND bare-function count >10 → receiver is bare-function-shaped; class-wrapped AC needs amendment unless (a) ≥3 cohesive tests, OR (b) helper homing requires a class container with @staticmethod.
If both counts are >5 → mixed shape; either form acceptable.

Report the per-receiver shape table at the top of the design-eval output.
```

**Evidence:** cycle-49 PR #72; R1 DeepSeek output at `.data/cycle-49/design-eval-r1.txt` (line 95 verdict APPROVE without host-shape note); primary's amend recorded in `2026-04-28-cycle-49-batch-design.md` Section "Binding amendment — AC3 host-shape (R1 missed)".

**Connection chain:** refines `cycle-40 L5` (Step-5 design-gate "Source file inspection results" requirement) by extending it upstream to Step-4 R1 prompts. Same insight, earlier gate.

---

### C49-L2 — `gh pr create` resolves `--head` from the CWD's branch, NOT the worktree being committed to

**New lesson.** When running `gh pr create` from the MAIN worktree's directory (the bash CWD when no explicit `cd` was performed), `gh` reads the current branch via `git symbolic-ref HEAD` from that CWD — which returns `main`, not the cycle-49-batch worktree's branch. Result: `gh pr create` fails with "head branch 'main' is the same as base branch 'main', cannot create a pull request" even though the actual commits live on `cycle-49-batch` in a separate worktree.

**Cycle-49 evidence:** Step 13 first-try `gh pr create --title "..." --body "..."` failed because the Bash tool's CWD was `D:/Projects/llm-wiki-flywheel` (main worktree) but the cycle's commits were on `cycle-49-batch` in the `D:/Projects/llm-wiki-flywheel-c49` worktree. Fix: pass explicit `gh -R Asun28/llm-wiki-flywheel pr create --base main --head cycle-49-batch ...` flags. Workaround works without changing CWD.

**Self-check (concrete prompt addition for Step-13 PR-creation guidance):**
```
When opening a PR from a parallel-worktree cycle:
- ALWAYS pass `--base main --head <cycle-N-batch>` to `gh pr create` explicitly
- ALWAYS pass `-R <owner>/<repo>` to scope `gh` to the right repo (matters in multi-clone setups)
- DO NOT rely on `gh` autodiscovering the branch from CWD; CWD-vs-worktree-branch mismatch is silent
- Self-check before dispatch: `git -C <worktree-path> branch --show-current` should match the `--head` arg
```

**Evidence:** cycle-49 PR #72 first dispatch failed with exit code 1; second dispatch with explicit flags succeeded → PR #72 created.

**Connection chain:** complements `C42-L4` (parallel-cycle worktree discipline). C42-L4 covers branch-aware Edits; C49-L2 covers branch-aware `gh pr create`. Same root cause class — CWD-vs-worktree drift in tooling — different surface.

---

### C49-L3 — multi-site doc-sync grep MUST run BEFORE staging, not just after

**New lesson.** Cycle-49 Step 12 doc sync had a missed CHANGELOG.md edit. The Edit attempt was issued in a parallel batch with CLAUDE.md / README.md / docs/reference/* edits, but the CHANGELOG.md Edit silently failed because: (a) initial parallel Edit batch hit "File has not been read yet" on multiple files; (b) the recovery batch re-Read CLAUDE.md and README.md but accidentally skipped CHANGELOG.md re-Read; (c) the CHANGELOG.md edit was attempted but never landed; (d) only caught when manual grep `grep -c "cycle 49" CHANGELOG.md` returned 0 instead of expected ≥1.

**Self-check (concrete sequence for Step 12 doc-sync):**
```
1. List all sites that need updating (typically 6-7 files per C26-L2 + C39-L3 + C49-L3).
2. Read EACH file once (parallel batch).
3. Edit each file (parallel or sequential — but verify NO Edit returned "File has not been read yet").
4. After edits, grep ALL sites for the OLD pattern → expected 0 hits per site.
5. After edits, grep ALL sites for the NEW pattern → expected ≥1 hit per site.
6. Stage + diff before commit; verify all expected files present in `git status --short`.
7. ONLY commit after step 6 confirms.
```

**Evidence:** cycle-49 Step 12 sequence required two doc-sync rounds (initial + cleanup); caught by `grep -c "cycle 49" CHANGELOG.md` returning 0 after the first round.

**Connection chain:** refines `C26-L2 + C39-L3` (multi-site test-count grep). The grep rule existed; the lesson is to run it BEFORE commit, as a gate, not just AFTER as verification. Specifically: post-Edit-pre-commit grep is the gate, not a comfort check.

---

## Cycle stats

- **PR:** #72 merged as `94d44a9`
- **Commits:** 6 (4 fold commits + 1 BACKLOG.md update + 1 doc-sync; zero PR fix-commits)
- **Tests:** 3025 → 3025 (preserved); Windows local 3014 passed + 11 skipped
- **File count:** 241 → 237 (-4 source-file deletions in folds)
- **Lines:** +566 / -145 across 16 files (3 new decision docs ~360 LOC; 4 fold rewrites ~140 LOC each across receiver + delete; doc updates small)
- **Reviewer time:** R1 DeepSeek ~7 min, R2 Codex 274s, total parallel wall-clock ~7 min
- **Wall-clock:** ~3.5h end-to-end including all wakeup waits

---

## Operator follow-up (skill infrastructure)

The skill-patch lessons above (C49-L1, C49-L2, C49-L3) are documented HERE in the project repo per cycle-39 L5. The user-global skill infrastructure update — appending these blocks to `~/.claude/skills/dev_ds/references/cycle-lessons.md` and adding one-liner index entries in `~/.claude/skills/dev_ds/SKILL.md` per the Step-16 split convention — requires operator action. This document is the source-of-truth artifact for that follow-up.

Specifically:
1. C49-L1 → "Design CONDITIONS" subsection of the index (refines C40-L5)
2. C49-L2 → new "Tooling — gh CLI" subsection or under "CI hard-gate hygiene"
3. C49-L3 → "Docs and count drift" subsection (refines C26-L2 + C39-L3)

---

## Final state

- main: 94d44a9 (cycle 49 squash merge)
- Worktree count: 1 (main only)
- Editable install: D:/Projects/llm-wiki-flywheel/src/kb/__init__.py ✓
- Open PRs: 0
- Late-arrival CVEs during cycle: 0 (post-merge alert IDs `[12,13,14,15]` matched baseline)
