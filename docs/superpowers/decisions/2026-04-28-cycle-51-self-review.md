# Cycle 51 — Self-review + skill patches

**Date:** 2026-04-28
**PR:** #74 (squash-merged at 6c421a9)
**Branch:** cycle-51-batch (deleted post-merge)
**Worktree:** D:/Projects/llm-wiki-flywheel-c51 (removed post-merge)

## Step scorecard

| Step | Executed | First-try | Surprised by anything? |
|------|----------|-----------|------------------------|
| 1. Requirements | yes | yes | — |
| 2. Threat model + dep-CVE baseline | partial (SKIP) | yes | — (pure-test-fold; only baseline captured) |
| 3. Brainstorming | SKIP | yes | — (established cadence) |
| 4. Design eval R1 | yes | yes | — (~3-5 min, 34.7 KB output, 1 amendment + 4 questions) |
| 5. Design decision gate | yes | yes | — (primary-session per C21-L1; all 4 R1 questions resolved by greps) |
| 6. Context7 | SKIP | yes | — (no third-party libs) |
| 7. Implementation plan | yes | yes | — |
| 8. Plan gate | yes | yes | — (inline self-check; all 25 ACs covered) |
| 9. Implementation | yes | **NO — fold 2 surprise** | **YES — see C51-L1** |
| 9.5. Simplify | SKIP | yes | — (zero src/ diff) |
| 10. CI hard gate | yes | yes | — (3014 + 11 skipped, 151.95s, ruff clean) |
| 11. Security verify | partial (PR-CVE only) | yes | — (Step 2 SKIP; Class B diff = empty) |
| 11.5. Existing-CVE patch | SKIP | yes | — (no patchable upstream) |
| 12. Doc sync | yes | **NO — Edit-tool surprise** | **YES — see C51-L3** |
| 13. Branch finalize + PR | yes | yes | — (PR #74 created cleanly) |
| 14. PR review | yes (R1 only, R2 SKIP) | yes | — (R1 APPROVE clean; R2 SKIP per cycle-49/50 precedent) |
| 15. Merge + cleanup | yes | **NO — worktree cleanup ordering surprise** | **YES — see C51-L2** |
| 16. Self-review | this | — | — |

3 surprises → 3 skill patches (C51-L1, C51-L2, C51-L3).

## Skill patches

### C51-L1 — Per-fold isolation pytest run surfaces latent test-ordering bugs that full-file runs mask (extends C41-L1 + cycle-19 L2)

**Incident.** Fold 2 (`test_cycle17_capture_prompt.py` → `test_capture.py::TestCapturePromptFile`) initially failed 3 of 5 tests when run in isolation (`pytest tests/test_capture.py::TestCapturePromptFile -v`) — `'NoneType' object has no attribute 'startswith'/'format'`. The 3 tests directly read `capture_module._PROMPT_TEMPLATE` which is `None` until the lazy accessor `_get_prompt_template()` is called (cycle-19 L2 lazy-load wrap).

**Why it didn't surface earlier.** When run in full-file context (`pytest tests/test_capture.py -q`), all 163 tests pass — earlier tests in the file (`TestCaptureItems`, `TestCaptureTemplate`, etc.) trigger `capture_items()` which calls `_get_prompt_template()` and populates `_PROMPT_TEMPLATE` as a side effect. Pytest runs tests in file-collection order; the original `test_cycle17_capture_prompt.py` lived after these other test files alphabetically and rode the side effect. Fold-isolation broke the ordering, exposed the bug.

**Same shape as C41-L1.** "fold cycles migrating KNOWN-WEAK tests MUST file BACKLOG.md upgrade candidate". The cycle-17 capture-prompt tests are weak in disguise — they only pass by accidental ordering. C41-L1 says fix in-fold rather than perpetuate. Cycle 51 did fix in-fold by switching to the canonical accessor.

**Rule.** Every fold MUST run `pytest <receiver>::<new_class_or_function>` in **ISOLATION** before commit, not just `pytest <receiver>` (full file). Isolation surfaces latent test-ordering bugs the moved test was riding. If isolation fails:
1. **Diagnose** — read the source/receiver to identify the lazy-init dependency or other side-effect contract.
2. **Fix in-fold** per C41-L1 — switch to the canonical accessor / explicit setup, NOT a `pytest.fixture` workaround that re-introduces ordering coupling.
3. **Document** the upgrade in the fold commit body so reviewers see it as an in-fold behavioral upgrade, not a silent move.
4. **Revert-check** the upgraded test (still per C40-L3) to confirm the fix is anchored to behavior, not just imports.

**Self-check.** After every fold, run BOTH:
```bash
pytest <receiver>::<new_target> -v        # ISOLATION — catches ordering bugs
pytest <receiver> -q                      # full-file — catches collisions
```
The pair takes <5s combined for small folds and is the cheapest way to catch this class of bug at fold time.

**Refines:** cycle-19 L2 (lazy-load reload-leak hazard), C41-L1 (vacuous-test upgrade requires docstring-vs-code sanity check), `feedback_inspect_source_tests`.

---

### C51-L2 — Worktree+squash-merge cleanup ordering: worktree-remove BEFORE branch-delete

**Incident.** Step 15 of cycle 51 ran `gh pr merge 74 --squash --delete-branch`. Squash-merge succeeded server-side, but local branch deletion failed:
```
failed to delete local branch cycle-51-batch: failed to run git:
error: cannot delete branch 'cycle-51-batch' used by worktree at 'D:/Projects/llm-wiki-flywheel-c51'
```

Manual recovery: `git worktree remove <path> --force` first, then `git branch -D <branch>`. This worked but added 2 commands + a thinking step that isn't in the dev_ds Step 15 template.

**Why current Step 15 docs don't mention it.** The original Step 15 template (skill SKILL.md) says:
```
gh pr merge <PR> --merge
git fetch origin main && git checkout main && git pull --ff-only
git branch -d <branch>
```
This was written before C42-L4 (worktree isolation became the default in cycles 42+). Worktrees hold branch refs, so `git branch -d` AND `gh pr merge --delete-branch` both fail when the worktree exists.

**Rule.** When the cycle ran in a worktree (per C42-L4), Step 15 MUST follow this order:
1. **`gh pr merge <PR> --squash`** (no `--delete-branch` flag — worktree holds the local branch ref).
2. **`git fetch origin main`** in MAIN worktree (cd to main path explicitly via `git -C <main-path>` if your shell still has the worktree as cwd).
3. **`git -C <main-path> checkout main && git -C <main-path> pull --ff-only origin main`** to advance main worktree to the squash-merge SHA.
4. **`git worktree remove <cycle-N-worktree-path> --force`** to release the branch ref.
5. **`git branch -D <branch>`** to delete the local branch (use `-D` not `-d` — squash-merge means the branch's commits don't appear in main's history as-is).
6. **`git worktree list`** to confirm only main remains.

**Self-check.** Before running `gh pr merge`, run `git worktree list` — if any worktree besides main is listed, you're in worktree mode and MUST follow the ordered cleanup above. Don't pass `--delete-branch` to `gh pr merge` in this mode.

**The dev_ds skill SKILL.md Step 15 template should be updated** to encode this ordering as the default (worktree mode is now the default per C42-L4).

**Refines:** C42-L4 (worktree isolation discipline).

---

### C51-L3 — Edit tool tracks Read state per file PATH, not per file CONTENT — worktree files need their own Read before Edit

**Incident.** Cycle 51 attempted to update CLAUDE.md, README.md, BACKLOG.md, etc. inside the worktree at `D:/Projects/llm-wiki-flywheel-c51/`. Even though I had Read these files at the top of the session via `D:/Projects/llm-wiki-flywheel/<path>` (main worktree paths in the gitStatus context), the Edit tool refused with:
```
File has not been read yet. Read it first before writing to it.
```

This fired on at least 4 files in cycle 51 (CLAUDE.md, README.md, docs/reference/testing.md, docs/reference/implementation-status.md) requiring quick `Read` calls before each Edit. ~4 wasted tool calls.

**Why it happens.** The Claude Code harness tracks file-state by absolute PATH, not by content hash. Worktree paths and main-repo paths are DIFFERENT absolute paths even when content is identical (`D:/Projects/llm-wiki-flywheel/CLAUDE.md` vs `D:/Projects/llm-wiki-flywheel-c51/CLAUDE.md`). The `Read` of the main path doesn't unlock the worktree path.

**Rule.** In worktree-isolated cycles (per C42-L4), at the entry of Step 12 (doc sync) — or any other step that will Edit multiple "shared" files — pre-Read EVERY target file in the worktree first, even if you've Read the same content from the main path:
```python
# At Step 12 entry, batch-Read all doc targets in the worktree:
Read(<worktree>/CLAUDE.md, limit=15)         # just enough to unlock Edit
Read(<worktree>/README.md, offset=358, limit=10)
Read(<worktree>/docs/reference/testing.md, limit=20)
Read(<worktree>/docs/reference/implementation-status.md, limit=15)
Read(<worktree>/CHANGELOG.md, limit=35)
Read(<worktree>/CHANGELOG-history.md, limit=35)
Read(<worktree>/BACKLOG.md, offset=85, limit=5)  # already partial-Read
```

**Better still:** put this batch-Read into the Step 12 plan template so the plan-gate catches missing Reads before they fail.

**Self-check.** When `Edit` returns "File has not been read yet" on a worktree file, the cause is not "read again" but "read THIS path" — verify the Edit's `file_path` matches the recently-Read path exactly (same drive letter case, same separator style, same trailing slashes).

**Refines:** C42-L4 (worktree isolation).

## Cycle stats

- **Items:** 25 ACs
- **Commits:** 5 (4 fold + 1 doc sync), squash-merged as 6c421a9
- **Source files modified:** 0 (zero `src/kb/` changes)
- **Test files deleted:** 4 (cycle12_conftest, cycle17_capture_prompt, cycle17_validators, cycle8_package_exports)
- **Receivers edited:** 2 (test_v070.py, test_capture.py)
- **Doc files edited:** 7 (CLAUDE.md, README.md, BACKLOG.md, CHANGELOG.md, CHANGELOG-history.md, docs/reference/testing.md, docs/reference/implementation-status.md)
- **Tests:** 3025 → 3025 (preserved)
- **File count:** 233 → 229 (-4)
- **Full suite:** 3014 passed + 11 skipped (151.95s Windows local)
- **CVEs:** 0 introduced (Class B diff empty); 4 known no-fix CVEs re-confirmed cycle-50 → cycle-51
- **Wall clock:** ~80 min (Step 1-15) including 2 cache-warm wakes for R1 dispatches

## Notes for cycle 52+

1. **Start fold cycles by reading the receiver's structure.** C40-L5 says Step 5 must include grep-results on host file structure. Cycle 51 did this and it paid off — confirmed TestMcpAppInstructions location, ruled out collisions in advance. Continue.

2. **Always run isolation pytest after each fold.** Even when full-file passes. C51-L1 shows the cost of skipping isolation.

3. **Pre-Read worktree files at Step 12 entry.** C51-L3. Add to the Step 7 plan template as a checklist line.

4. **Worktree cleanup is its own cleanup sequence.** C51-L2. Update Step 15 SKILL.md template.

5. **Continue C41-L1 fold-with-fix discipline.** When fold isolation fails because of an underlying test weakness, fix the test in the same commit rather than perpetuating the weakness. Cycle 51 fold 2 confirms this is the right call — 3-line fix, all 5 tests now run order-independent.
