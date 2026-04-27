# Cycle 43 — Step 16 Self-Review

**Date:** 2026-04-27
**Cycle scope:** Phase 4.5 HIGH #4 test-fold continuation (11 folds + 4 BACKLOG entries)
**Merged commit:** `5bd8fcb` (PR #61 → main)
**Wall-clock:** ~5.5 hours from `/dev_ds 43 ...` to merge

## Scorecard

| Step | Executed? | First-try? | Surprised? |
|------|-----------|------------|------------|
| 1 — Requirements + ACs | yes | yes | — |
| 2 — Threat model + dep-CVE baseline | partial (skip-path; baseline only) | yes | — |
| 3 — Brainstorming | yes (primary) | yes | — |
| 4 — Design eval (R1+R2 parallel) | yes (DeepSeek direct CLI + Codex agent) | yes | — |
| 5 — Design decision gate | yes (primary, Opus rationale) | yes | — |
| 6 — Context7 verify | skip (no third-party libs) | n/a | — |
| 7 — Implementation plan | yes (primary) | yes | — |
| 8 — Plan gate | yes (self-attested per cycle-21 L1) | yes | — |
| 9 — Implementation (11 folds + BACKLOG) | yes | **no** (AC5 dedup discovery + parallel-session interference) | yes (3 surprises) |
| 9.5 — Simplify | skip (test-only) | n/a | — |
| 10 — CI hard gate | yes | **no** (7 E501 + 1 format diff) | yes (1 surprise) |
| 11 — Security verify + PR-CVE diff | yes | yes | — |
| 11.5 — Existing-CVE patch | skip (no actionable bumps) | n/a | — |
| 12 — Doc update | yes | yes | — |
| 13 — Branch finalise + PR | yes | **no** (PR #61 CONFLICTING vs main; cycle-42 had merged) | yes (1 surprise) |
| 14 — PR review (R1+R2) | yes | **no** (R1 Codex BLOCKER + 1 NIT; R2 verified resolution) | yes (1 surprise) |
| 15 — Merge + cleanup + late-CVE warn | yes | yes (zero new alerts) | — |

**Net:** 6 surprises across Steps 9 (×3), 10, 13, 14. All resolved in-cycle.

## Surprises and skill-patch candidates

### Surprise 1 — Parallel cycle-42 session shared the working tree (Step 9-13)

**What happened:** The user said "cycle 42 is running in parallel". I interpreted "parallel" as a separate session/agent on a different branch — but they shared the SAME working directory `D:\Projects\llm-wiki-flywheel`. Cycle-42 session was actively switching branches (`cycle-42-phase46-dedup` ↔ `cycle-43-test-folds`) and committing during my cycle-43 work. Concrete failures:

1. **My Step 1+2 docs commit landed on cycle-42's branch** (commit `64b94b5`) because cycle-42 session checked out their branch in the brief moment between my `git status` and `git commit`. Recovered via cherry-pick to cycle-43-test-folds (commit `5ca6ca7`).
2. **My Step 5+7 docs commit also landed on cycle-42's branch** (commit `a681b4c`). Cherry-picked again (commit `db10032`).
3. **My stash@{0} of cycle-42's WIP got popped by them mid-cycle** when they recovered their work, leaving my cycle-43 with mysterious new src/ modifications.

**Recovery:** `git worktree add D:/Projects/llm-wiki-flywheel-c43 cycle-43-test-folds` — created a true worktree isolation. All subsequent cycle-43 work happened in that worktree using the main worktree's `.venv` for pytest invocation. Zero further interference after that.

**Skill-patch candidate (C43-L1) — Parallel-cycle worktree-from-the-start rule.**

> When the user says "cycle X is running in parallel" or otherwise indicates concurrent cycles in the same project, the FIRST step (before any commit) MUST be `git worktree add <sibling-path> cycle-N-<scope>` to create a true filesystem isolation. Do NOT attempt to coordinate via `git stash` + `git checkout` in a shared working tree — branch switches by the parallel session will cause your commits to land on their branch.
>
> **Why:** Cycle-43 burned 3+ hours and 4 mistaken commits (`64b94b5`, `a681b4c` and 2 cherry-pick recoveries) before adopting the worktree pattern. After worktree creation, zero further interference. The cost of `git worktree add` is one shell command; the cost of NOT using it scales with the number of branch switches by the parallel session.
>
> **How to apply:** In dev_ds Step 0 (pre-Step 1 setup) for cycles where the user has indicated parallel-cycle context, run `git worktree add D:/Projects/<repo>-cN cycle-N-<scope>` instead of `git checkout -b cycle-N-<scope>`. Use absolute paths in all subsequent tool calls (Read/Edit/Write/Bash) so the cycle's tree binding is explicit. For pytest, invoke the main-worktree's `.venv/Scripts/python.exe -m pytest` from the new worktree's cwd to inherit the editable install but use the worktree's tests/ directory.

**Refines:** cycle-22 L2 (block-no-verify hook hazard); cycle-39 L1 (wrapper-vs-direct dispatch). Different failure mode (working-tree contention vs Codex companion blocking) but same theme: shared infrastructure between concurrent agents requires explicit isolation.

---

### Surprise 2 — AC5 7-test redundancy discovered mid-Step-9 (Step 9)

**What happened:** TASK 5 (`test_cycle11_ingest_coerce.py` → `test_ingest.py`) source had 11 tests. While reading the source for the fold, I noticed 7 of the 11 were bare-function copies of cases already covered by AC2's just-folded parametrized test (`test_coerce_str_field_accepts_string_missing_none_and_rejects_non_strings` with 10 rows including int/float/dict/list/bytes/bool). Folding the 7 redundant tests would have added pure churn — same assertions twice with different fixture-name decoration.

**Decision routed via cycle-17 L3:** Rather than silently narrow scope OR fold-then-delete-later, I documented the AC5 design-amendment in the commit message (`52eaa0b`) AND in the consolidated BACKLOG commit (`ebd880a`). Net cycle-43 test count: 3014 → 3007 (−7). NOT a regression — explicit dedup with grep-cross-checked coverage.

**Skill-patch candidate (C43-L2) — Test-fold cycles surface dedup opportunities; route via cycle-17 L3.**

> When a fold cycle migrates multiple test files into a shared canonical home, expect to discover redundant tests that overlap with peer folds. The right disposition is NOT "fold all to preserve count" (cycle-15 L2 DROP-with-test-anchor explicitly preserves test ANCHORS, not REDUNDANCY). The right disposition is also NOT "silently drop redundant tests during Step 9" (cycle-17 L3 forbids silent scope narrowing). The right path:
>
> 1. **Detect** at fold-time via grep: when reading source, grep canonical home for the same production symbol (`_coerce_str_field`, `frontmatter.load`, etc.). If both target the same parametrize-equivalent input space, flag.
> 2. **Document** the dedup as a DESIGN-AMEND in the AC's commit message naming (a) what was dropped, (b) what coverage was retained, (c) why dropping is safe (reverse-revert sanity: would the parametrized test still fail if production were reverted?). Cycle-43 commit `52eaa0b` is the template.
> 3. **Update** plan / design doc inline with `DESIGN-AMEND (added <date> mid-Step-9 per cycle-17 L3): ...` so future cycle-43 R1/R2 reviewers and Step 16 self-review see the rationale.
> 4. **Update** count-sensitive doc fields at Step 12 (CHANGELOG / BACKLOG / CLAUDE.md / README / testing.md / implementation-status.md) to reflect actual numbers, NOT the pre-amendment plan.
>
> **Why:** Silent narrowing produces "WTF the test count dropped" reviewer questions and breaks the cycle-26 L2 / C39-L3 multi-site count-sync rule. Explicit DESIGN-AMEND lands the discovery in the audit trail where future maintainers can find it.
>
> **How to apply:** When folding test file F into canonical home H, add an explicit grep step before writing the new test bodies: `grep -E "def test_<base_name>" H tests/test_cycleNN_*` to enumerate same-symbol tests already in H. If overlap exists, route through Step 5 design-amendment (one Opus subagent dispatch ~2 min) OR document inline in the commit message + plan doc per the C43-L2 template.

**Refines:** cycle-17 L3 (scope-narrowing routes BACK to design); cycle-15 L2 (DROP-with-test-anchor); `feedback_test_behavior_over_signature` (redundant assertions don't add coverage).

---

### Surprise 3 — AC7 reload-isolation BLOCKER (Step 9 + Step 14 R1 Codex)

**What happened:** I designed AC7 to wrap 5 reload-using config tests in `TestProjectRootResolution` class with an autouse `_restore_config_after_test` fixture that took `monkeypatch` as a dependency. Intent: clean up env var + reload config back to canonical state after each test. Step 14 R1 Codex caught a real ordering bug:

- Pytest LIFO finalization: a fixture that DEPENDS on monkeypatch finalizes BEFORE monkeypatch teardown.
- My fixture took `monkeypatch` as a param, so my reload ran while the test's `monkeypatch.chdir(tmp_path)` and `monkeypatch.setattr(Path, "exists", ...)` were still active.
- The reload re-detected PROJECT_ROOT from the temp-dir's chdir, then monkeypatch undid the chdir, leaving PROJECT_ROOT pointing at a now-deleted temp dir.

**Why the full suite passed anyway:** Test discovery order ran `test_make_source_ref_*` BEFORE `TestProjectRootResolution` in test_paths.py, so the leak didn't surface in any sibling assertion. Codex's catch was correct + load-bearing for future test additions.

**Fix (commit `86577a4`):** Drop `monkeypatch` from fixture signature. With no explicit dependency, pytest finalizes my fixture LAST (after monkeypatch has restored env/cwd/setattr). Reload then sees the canonical state. Verified by R2 Codex.

**Skill-patch candidate (C43-L3) — Pytest fixture finalization order with monkeypatch dependencies.**

> When writing an autouse fixture whose teardown body NEEDS to see the post-monkeypatch-teardown state (e.g. reload a module after env vars / cwd / setattr have been restored), DO NOT take `monkeypatch` as a fixture parameter. Pytest finalizes fixtures in LIFO of setup order; explicit dependencies force your finalize to run BEFORE the dependency's finalize. By being autouse-only with no explicit dependencies, your finalize runs LAST.
>
> **Concrete pattern (cycle-43 AC7 template):**
> ```python
> @pytest.fixture(autouse=True)
> def _restore_after_test(self):  # NO monkeypatch param
>     """Restore module state to canonical snapshot after every test in this class."""
>     yield
>     # Runs AFTER monkeypatch has restored env/cwd/setattrs, so reload
>     # sees the canonical state.
>     import kb.config as config
>     importlib.reload(config)
> ```
>
> **Reverse pattern (when finalize needs DURING-monkeypatch state):** explicitly take `monkeypatch` as a dep. Then your finalize runs INSIDE the active monkeypatch context — useful for restoring something that must be observable to other monkeypatch teardown steps.
>
> **Self-check for fold cycles:** any AC that adds an autouse fixture wrapping `importlib.reload`, env-var clear, or cwd-restore in a class with multiple chdir/setattr-using tests MUST run pre-merge under R1 review with the question: "Will this finalize run BEFORE or AFTER monkeypatch teardown?" If the answer is "before" and the finalize observes module-level state derived from cwd/env/setattr, it's a BLOCKER.

**Refines:** cycle-19 L2 (snapshot-binding hazard with `from X import Y`); cycle-20 L1 (pytest.raises misfires across reload-boundary modules); cycle-22 L3 (full-suite test in CI catches reload-leak).

---

### Surprise 4 — 7 ruff E501 errors on long section comments (Step 10)

**What happened:** Ruff format ran without complaint mid-cycle, but the post-Step-9 `ruff check` flagged 7 E501 line-too-long errors on the `# ── Cycle N ... (folded from test_cycleNN_*.py) ─` section comments I added per cycle-41 fold-comment style. The longest was 243 chars (the AC5 dedup-explanation comment).

**Fix:** Mechanical shortening. 1 commit (`35d469d`) with 8 string changes. Per cycle-35 L7 ruff-format-vs-Edit ordering rule.

**Lesson (no new skill patch — cycle-35 L7 covers this):** Per cycle-35 L7, ruff-format runs AFTER all Edits. But ruff-CHECK on long comments is a separate concern from ruff-format reflow. For section comments specifically:
- Comments with prose (multi-clause, parenthetical detail) trip E501.
- Compact `# ── <Symbol>: <one-line-summary> (cycle N fold) ─` keeps under 100 cols.
- Cycle-41 set the style; cycle-43 inherited it but added more parenthetical detail than fit.

**Implicit rule reinforcement:** When writing fold section comments, target ≤80 chars (leaves room for trailing dashes per the box-drawing convention). Long parenthetical detail goes in commit messages, not comment lines.

---

### Surprise 5 — Cycle-42 PR landed on main during cycle-43, causing PR #61 conflict (Step 13/14)

**What happened:** Cycle-42 PR #60 merged at commit `01f0e6a` while my cycle-43 work was in flight. After my Step 13 `gh pr create`, GitHub reported PR #61 mergeStateStatus: DIRTY. Conflicts on:
- `CLAUDE.md` (state-line counts both branches updated independently)
- `CHANGELOG.md` (both branches added a cycle entry)
- `CHANGELOG-history.md` (both added a per-cycle archive entry)
- `tests/test_mcp_browse_health.py` (cycle-42 changed `_sanitize_error_str` import; cycle-43 added a test in a different section — auto-merged cleanly)

**Fix (commit `285f96c`):** `git merge origin/main` on cycle-43-test-folds. Resolved 3 textual conflicts newest-first (cycle 43 → cycle 42 → cycle 41 in history docs). Verified post-merge: 3007 tests collected, ruff clean.

**Skill-patch candidate (C43-L4) — PR-time merge with concurrent-cycle landings.**

> When a parallel cycle's PR lands on main DURING your cycle's Step 13 PR creation window, expect mergeStateStatus DIRTY on your PR. The conflict surface is predictable:
>
> - **Doc files** (CLAUDE.md / CHANGELOG.md / CHANGELOG-history.md / README.md / docs/reference/*.md) — both branches almost always edit shared count-narrative or per-cycle entries. Resolution: keep BOTH cycles' edits, ordered newest-first per the file convention.
> - **Test files in canonical homes** (test_mcp_*, test_query.py, test_lint.py) — usually auto-merge if the two cycles edit different sections.
> - **src/kb files** — rarer if both cycles deliberately scope to non-overlapping modules (cycle-42 was Phase 4.6 dedup in src/kb/{cli,mcp,query,lint}/...; cycle-43 was tests-only — zero overlap).
>
> **Workflow:** Don't try to rebase. `git merge origin/main` + manual conflict resolution + push. The merge commit is the audit trail of the cross-cycle synchronization.
>
> **Pre-conflict-prevention:** When the user mentions a parallel cycle, scope your cycle to MINIMIZE shared-file overlap. Cycle-43 chose tests/ only because Phase 4.5 HIGH #4 was tests-scoped; this minimised the cycle-42 collision surface to doc-narrative + 1 test-file (test_mcp_browse_health.py) where the new test was in a different section than cycle-42's edited import line.

**Refines:** cycle-22 L4 (cross-cycle CVE arrival between Step 2 and Step 11); cycle-36 L3 (no PR-branch push after squash-merge trigger). New territory because cycle-43 is the first cycle to land in true-parallel with another cycle (cycles 39-42 were sequential).

---

### Surprise 6 — pip-audit baseline location across worktrees (Step 11)

**What happened:** Step 2 captured the dep-CVE baseline to `D:/Projects/llm-wiki-flywheel/.data/cycle-43/cve-baseline.json` in the MAIN worktree (before I created the cycle-43 worktree). At Step 11 in the cycle-43 worktree, the baseline file did not exist at `D:/Projects/llm-wiki-flywheel-c43/.data/cycle-43/cve-baseline.json`. Had to `cp -r` the baseline into the cycle-43 worktree.

**Skill-patch candidate (C43-L5 — minor) — Worktree-aware baseline file location.**

> When using a git worktree (per C43-L1), Step 2 dep-CVE baseline + Step 11 PR-CVE diff MUST use paths within the worktree's `.data/cycle-N/` directory, not the original worktree's. Mitigations:
>
> - Capture baseline in the worktree where Step 11 will run (preferred).
> - If baseline was captured in the main worktree before worktree creation, `cp -r D:/Projects/<repo>/.data/cycle-N D:/Projects/<repo>-cN/.data/` before Step 11.
>
> Self-check at Step 11: `wc -c .data/cycle-N/cve-baseline.json` from the cycle's worktree must return non-zero before running the diff.

**Refines:** cycle-22 L1 (Windows bash `/tmp/` vs Python.exe path mismatch); cycle-40 L4 (project-relative `.data/cycle-N/` for cross-platform paths). Same theme: baseline / artifact paths must match the working tree where they're consumed.

## Skill-patch landing notes

Per cycle-39 L5, skill patches that fix infrastructure ship in user-global `~/.claude/skills/dev_ds/` not the project repo. The 5 candidates above (C43-L1 through C43-L5) are documented here as the project-repo audit trail; user-global SKILL.md `Accumulated rules index` updates + `references/cycle-lessons.md` blocks are the operator's follow-up step.

**Specifically for the next maintainer:**

1. **Append to `~/.claude/skills/dev_ds/references/cycle-lessons.md`** under a new `## Cycle 43 skill patches (2026-04-27)` heading: 5 blocks (C43-L1 through C43-L5) with the rule + Why + How to apply + Refines lines copied verbatim from this file's surprise sections.

2. **Append to `~/.claude/skills/dev_ds/SKILL.md` Accumulated rules index** under appropriate concern areas:
   - Subagent dispatch and fallback: `- C43-L1 — parallel-cycle worktree-from-the-start: use git worktree before any commit when user mentions concurrent cycles (refines cycle-22 L2 + cycle-39 L1)`
   - Test authoring: `- C43-L2 — fold-cycle redundancy detection: route 7-test-overlap discoveries via DESIGN-AMEND inline + commit message (refines cycle-17 L3 + cycle-15 L2)`
   - Implementation gotchas: `- C43-L3 — pytest autouse fixture finalize-without-monkeypatch-dep when teardown observes post-monkeypatch state (refines cycle-19 L2 + cycle-20 L1 + cycle-22 L3)`
   - Subagent dispatch and fallback: `- C43-L4 — concurrent-cycle PR merge: keep both cycles' doc edits newest-first; src non-overlap minimises conflict (refines cycle-22 L4 + cycle-36 L3)`
   - Library and API awareness: `- C43-L5 — worktree-aware baseline file location: capture in the worktree where Step 11 will run, OR cp -r before diff (refines cycle-22 L1 + cycle-40 L4)`

## Cycle 43 final stats

- **Items shipped:** 11 folds + 4 BACKLOG entries + 1 R1 BLOCKER fix + 1 R1 NIT fix
- **Commits on cycle-43-test-folds branch:** 17 (16 cycle-43-only + 1 merge with main)
- **Test count:** 3014 → 3007 (−7 from AC5 dedup)
- **Test file count:** 251 → 242 (−9 net; cycle-42 also folded but on different files)
- **Wall-clock:** ~5.5 hours from `/dev_ds 43 ...` to merge
- **Reviewer findings:** 1 BLOCKER (resolved) + 1 NIT (resolved) + 0 MAJOR
- **Operational lessons:** 5 skill-patch candidates (C43-L1 through C43-L5)
- **Merge target:** PR #61 → main commit `5bd8fcb` at 2026-04-27T08:54:52Z
- **Late-arrival CVE check (post-merge):** clean — same 4 carry-over advisories as cycle 41/42 baseline.

**Cycle status:** COMPLETE.
