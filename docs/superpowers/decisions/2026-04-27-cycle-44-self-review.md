# Cycle 44 Self-Review

**Date:** 2026-04-27
**PR:** #63 (merged as commit `ac8beb8` on main)
**Branch:** cycle-44-batch (squash-merged + deleted on origin)
**Worktree:** D:/Projects/llm-wiki-flywheel-c44 (post-cycle artifact; eligible for cleanup)
**Cycle theme:** Phase 4.6 close — M1 + M2 + M4 splits + AC10 fold + 3 vacuous-test upgrades (M3 deferred to cycle 45)

---

## Step scorecard

| Step | Executed? | First-try? | Surprises |
|------|-----------|------------|-----------|
| 1 — Requirements + ACs (Codex) | yes | yes | Codex auto-encoded literal strings as `chr()` concat (visible in AC14/AC25 of saved doc) — over-applied secret-scanner avoidance per `feedback_no_secrets_in_code`. Cosmetic; doc still readable. |
| 2 — Threat model + CVE baseline | yes | yes | Skipped formal DeepSeek dispatch per skip-when (pure internal refactor). Captured 4 pip-audit + 4 Dependabot baselines + 6 correctness invariants T1-T6 directly. |
| 3 — Brainstorming | yes | yes | Inline brainstorm in primary session (refactor-class alternatives are well-bounded). 10 open questions surfaced for Step 5 to resolve. |
| 4 — Design eval R1 + R2 | yes | yes | R1 (DeepSeek direct CLI) flagged AC25 signature reversal + AC12 save_page_frontmatter mismatch. R2 (Codex agent) found 13 amendments needed including 24 atomic_text_write callers (vs my "20" estimate), 17+ call_llm_json patch sites in test_v5_lint_augment_orchestrator.py alone, AC11 compat-shim need, AC29 production-behavior-change risk, AC30 wrong target API. Both returned in ~5-6 min as predicted by cycle-24 L5. |
| 5 — Design decision gate (Opus) | yes | yes | All 14 questions resolved with HIGH confidence; M3 deferred to cycle 45 (Q13). 7 binding CONDITIONS produced. No ESCALATE. |
| 6 — Context7 verify | skip | n/a | Skipped per skip-when (pure stdlib/internal refactor; no third-party API). |
| 7 — Implementation plan | yes | yes | Drafted in primary session per cycle-14 L1 (≥15 ACs + primary holds context). 15 TASKs, ~30 deliverables. |
| 8 — Plan gate (Codex) | yes | partial | REJECT with 7 specific test-assertion gaps. Per cycle-21 L1, resolved INLINE (gaps were doc/test-assertion clarifications, not code-exploration). Plan AMENDMENTS section appended. |
| 9 — Implementation | yes | mostly | TASKs 1-7 + 12-14 in primary; M1 + M2 splits via parallel Codex subagent dispatches. Surprise: Codex M2 initial apply_patch wrote to MAIN worktree; agent self-detected via git status + reverted via git restore + switched to PowerShell mode. See C44-L5 below. |
| 9.5 — Simplify pass | skip | n/a | Skipped per skill skip-when row (signature-preserving structural refactor only — atomic_text_write keeps `(content, path)` order; package splits preserve function bodies; no over-engineering surface to simplify). |
| 10 — CI hard gate | yes | yes (after ruff cleanup) | 3008 passed + 11 skipped local Windows; ruff `--fix` applied 4 I001 import-sort fixes + 15 cosmetic format reformats. CONDITION 14 hygiene: 3 scratch files (findings.md / progress.md / task_plan.md) left by Codex subagents — deleted to satisfy cycle-34 hygiene test. |
| 11 — Security verify + PR-CVE diff | yes | yes | Class B (PR-introduced) = empty. Class A unchanged: 4 baseline advisories all pre-existing per BACKLOG cycles 32-43 narrative. |
| 11.5 — Existing-CVE patch | skip | n/a | Skipped — all 4 baseline advisories have no upstream patch (diskcache / ragas / pip) or are blocked by transitive (litellm 1.83.7 needs click==8.1.8 vs our pinned 8.3.2). No-op confirmed by post-implementation re-check. |
| 12 — Doc update | yes | yes | CHANGELOG / CHANGELOG-history / BACKLOG / CLAUDE.md / docs/reference/* / README.md updated. Test count narratives 3007 → 3019, file count 240 → 241 per C26-L2 + C39-L3. |
| 13 — Branch finalise + PR | yes | yes | Pushed cycle-44-batch + opened PR #63 with full review trail in body. |
| 14 — PR review (R1 + R2 + R3) | yes | partial | R1 DeepSeek APPROVE with one non-blocking note (resolved by manual verify: capture.py has zero atomic_text_write usage post-deletion). R2 Codex sub-task `b0ngrd3wr` exceeded 10-min completion threshold — fell back to manual verify per cycle-20 L4. R3 audit-doc drift sweep in primary session per `feedback_minimize_subagent_pauses` (cycle-17 L4 trigger fired at 14 resolved Step-5 questions). |
| 15 — Merge + cleanup + late-arrival CVE warn | yes | yes | Squash-merged via `gh pr merge --squash --delete-branch`; main fast-forwarded to `ac8beb8`. Late-arrival CVE check: 4 open Dependabot alerts unchanged. |

---

## Six operational surprises (cycle-44 specific)

### 1. AC29 design proposed a production behavior change disguised as a test upgrade

R2 Codex found that AC29's "behavioral mtime-collision test" implicitly required adding `st_size` or content fingerprint to `load_page_frontmatter`'s cache key — a PRODUCTION CHANGE forbidden by non-goal #1 ("NO functional or behavior changes"). Cycle 43's vacuous-test upgrade plan blindly proposed swapping a docstring assertion for a behavioral test that asserted the OPPOSITE behavior. Q11 inverted the AC: pin the DOCUMENTED stale-read contract instead, satisfying both cycle-16 L2 (behavioral coverage) and non-goal #1 (no behavior change).

### 2. AC30 monkeypatch target didn't exist in production

AC30 specified `monkeypatch.setattr` of `psutil.pid_exists`, but `kb.utils.io.file_lock` actually uses `os.kill(pid, 0)` to detect dead processes. Patching `psutil.pid_exists` would never fire. R2 Codex caught it via grep at design eval. Q12 corrected the target to `kb.utils.io.os.kill` raising `ProcessLookupError`.

### 3. C42-L3 patch invalidation extends to PRODUCTION callers, not just tests

The cycle-44 design Q4 amended AC15 to migrate test patches from `kb.lint.augment.run_augment` → `kb.lint.augment.orchestrator.run_augment`. AC15 was implemented and 2 patches updated. Then `tests/test_cycle17_resume.py` STILL FAILED. Investigation: `cli.py:344` and `mcp/health.py:114` import via `from kb.lint.augment import run_augment` (the PACKAGE re-export creates a SEPARATE binding); tests patching `orchestrator.run_augment` never reach those production callers because they read the package's binding (snapshot-bound at import time). Fixed by also updating production callers to `from kb.lint.augment.orchestrator import run_augment` directly — TWO separate code-locations per migration when production callers exist.

### 4. AC's premise can fail at implementation time

AC26/AC27 design assumed `capture.py` had production atomic_text_write call sites needing the io_utils import pattern. Implementation discovered `_exclusive_atomic_write` had ZERO production callers — only the 4 `TestExclusiveAtomicWrite` tests in `test_capture.py` used it, making it effectively a test fixture. The io_utils import pattern was unnecessary; tests patch `kb.utils.io._atomic_text_write_replace` (the inner) directly for cleanup-on-failure regression. Documented the AMENDMENT in CHANGELOG-history.md rather than silently dropping the design instruction.

### 5. Codex subagent apply_patch initially wrote to MAIN worktree, not c44

M2 Codex dispatch was instructed "Do NOT touch D:/Projects/llm-wiki-flywheel — that is the main worktree". The agent's first apply_patch calls nonetheless created `src/kb/lint/augment/` files in the main worktree (the apply_patch tool resolves paths relative to the dispatcher session's cwd, not the task-specified working directory). Codex agent self-detected via `git status` showing unexpected modifications in main, used `git restore` to revert, then switched to PowerShell + absolute-path here-strings for the second pass — which succeeded in c44. No data loss; main worktree clean post-recovery.

### 6. DeepSeek direct CLI failed on 482KB prompt with bidi-char encoding

The first R1 PR-review dispatch built a 482KB prompt by piping `git diff origin/main..HEAD` directly. The diff contained the cycle-12 sanitize-context test's `HOSTILE_PAYLOAD` (NUL + BIDI override + fullwidth chars) — at column 468809 of the JSON-encoded request body, the unicode produced "lone leading surrogate in hex escape". DeepSeek returned a 400 error after 1.1s. Retry with a SLIMMER 52KB prompt (diff-stat + targeted src/ excerpts only, no test files with bidi fixtures) succeeded in ~5 min.

---

## Skill-patch candidates (5 lessons → cycle-lessons.md)

### C44-L1 — Vacuous-test upgrades require non-goal cross-check

**Rule.** When upgrading a docstring-introspection test to a behavioral test (per C40-L3 / C41-L1), the proposed behavioral assertion MUST be checked against the cycle's non-goals. If the behavioral test's expected outcome contradicts a documented contract OR requires a production change (cache-key change, validator addition, contract relaxation), the AC has crossed from "test upgrade" into "behavior change" — re-route through Step 5 design gate or invert the assertion to pin the EXISTING documented behavior instead.

**Why:** cycle 43 flagged 3 vacuous-test upgrade candidates with concrete behavioral replacement plans. Cycle 44 R2 Codex caught that AC29's proposed `test_load_page_frontmatter_mtime_collision` would assert FRESH content returned after mtime collision — directly contradicting `src/kb/utils/pages.py:78-83` which documents stale reads as ACCEPTABLE. The cycle's non-goal #1 forbade behavior changes. Fix: invert the test to pin the DOCUMENTED contract.

**How to apply:** at Step 4 design eval, for every AC matching pattern "replace docstring-grep test X with behavioral test Y": (a) read the production code's existing docstring + contract; (b) verify Y's expected outcome is consistent with the documented behavior; (c) if Y contradicts the docstring, the AC requires a Step-5 design amendment OR a Q-style decision to invert. Refines C40-L3 + C41-L1.

### C44-L2 — Behavioral test self-checks require monkeypatch-target verification

**Rule.** When a vacuous-test upgrade or new behavioral test specifies a monkeypatch target (`monkeypatch.setattr("module.symbol", ...)`), Step 4/5/Step-9 self-check MUST grep the production module for an actual call site that uses the patched symbol. If the symbol is not actually called by the production code path under test, the patch is vacuous and the cycle-16 L2 mutation self-check would still PASS (a false guarantee).

**Why:** Cycle 44 AC30 originally specified `monkeypatch.setattr(psutil.pid_exists, ...)` but `kb.utils.io.file_lock` uses `os.kill(pid, 0)` to detect dead processes — `psutil.pid_exists` is never called. Patching it would have no effect; the test would pass either way; the cycle-16 L2 self-check (mutate `lock_path.unlink` to no-op) would still observe the patched-then-uncalled-then-no-op chain because the original lock-reaping path doesn't fire. R2 Codex caught it via direct grep before implementation.

**How to apply:** at Step 4 design eval, for every AC mentioning `monkeypatch.setattr(X.Y, ...)` or `patch("X.Y", ...)`: grep `src/kb/` for `X.Y(` (call site) AND `from X import Y` (snapshot binding). Both must exist on the code path the test exercises. If only the import exists (or neither), the patch is vacuous. Refines C26-L3 (grep-spec call-shape) + cycle-16 L2.

### C44-L3 — C42-L3 patch-invalidation extends to PRODUCTION callers, not just tests

**Rule.** When a function moves from module A to canonical owner module B (with `from B import X` re-exported in A's `__init__.py` for backward compat), and tests are migrated to patch `B.X` per C42-L3, ANY production caller doing `from A import X` or `import A; A.X` ALSO needs to migrate to `from B import X` directly. The package re-export creates a SEPARATE binding in A's namespace; patches on `B.X` don't reach A's binding (cycle-18 L1 snapshot-bind hazard applies symmetrically to package re-exports).

**Why:** Cycle 44 AC15 migrated 2 test patches from `kb.lint.augment.run_augment` → `kb.lint.augment.orchestrator.run_augment`. Tests still failed because `cli.py:344` (lazy import) and `mcp/health.py:114` (lazy import) read `kb.lint.augment.run_augment` from the package's __init__ binding — that binding was set at import time pointing at the original `run_augment`. Tests patching `orchestrator.run_augment` updated the orchestrator's namespace but not the package's snapshot. Fix: production callers updated to `from kb.lint.augment.orchestrator import run_augment` directly. Mid-cycle discovery cost ~30 minutes of debug.

**How to apply:** at Step 7 plan grep gate AND Step 11 security verify, when listing patch-target migrations per C42-L3, ALSO grep `src/kb/` for `from <package> import <symbol>` and `<package>.<symbol>` patterns. Every production caller using the package re-export ALSO needs migration to the canonical owner. Add to plan TASK as "production caller migration" sub-step. Self-check at Step 9: after migrating tests, run the affected test file in isolation; if it still fails, inspect production callers. Refines C42-L3 (was test-scope-only).

### C44-L4 — AC's design premise can fail at implementation time — document AMENDMENT, don't silently skip

**Rule.** When an AC's design specifies a pattern (e.g. "rewrite X to use io_utils import + single-site patch") that ASSUMES existing call sites or a current code structure, Step-9 implementation MUST verify the assumption holds before applying the pattern. If the assumption fails (zero call sites, different structure, prior cycle already migrated), document the AMENDMENT explicitly in (a) commit message, (b) CHANGELOG-history.md cycle entry, and (c) Step-16 self-review — DO NOT silently skip the design pattern. Future readers tracing the cycle's "why" depend on the AMENDMENT trail.

**Why:** Cycle 44 AC26/AC27 design (Q10 amendment) said `capture.py` should `import kb.utils.io as io_utils` so the single-site `monkeypatch.setattr("kb.utils.io.atomic_text_write", ...)` intercepts. Implementation discovered `capture._exclusive_atomic_write` was the ONLY consumer of `atomic_text_write` in capture.py, AND it was being deleted entirely (no production callers — was a test fixture). The io_utils pattern became unnecessary. Without explicit AMENDMENT documentation, R1 PR review flagged "verify capture.py uses io_utils" as a non-blocking note because the pattern from the design was missing. CHANGELOG-history.md amendment text resolved the gap.

**How to apply:** at Step 9, when an AC specifies a pattern based on existing call sites, re-grep at implementation time. If the assumption fails: (a) commit with `# AMENDMENT (cycle-N AC#X — design assumption failed):` comment header; (b) add a CHANGELOG-history.md "Operational lessons" bullet describing what assumption failed and the resolution; (c) flag for Step-16 self-review skill-patch candidate. Refines cycle-15 L1 (was about R1 grep-verify; this extends to mid-implementation discovery).

### C44-L5 — Subagent worktree dispatch needs explicit cwd anchoring + post-completion verification

**Rule.** When dispatching a subagent (Codex or DeepSeek) with instructions to write to a non-default working directory (e.g. cycle-N worktree at `D:/Projects/proj-cN/`), the dispatch prompt MUST explicitly anchor cwd via repeated absolute paths (NOT just "working directory: ..." once at top), AND the primary session MUST verify post-completion that target files landed in the correct worktree (not the main worktree where the subagent's tools may default to).

**Why:** Cycle 44 M2 Codex dispatch said "Do NOT touch D:/Projects/llm-wiki-flywheel" but the agent's apply_patch tool defaults to the dispatcher session's cwd (which IS the main worktree) — initial writes landed there before the agent self-detected via `git status`. Recovery required `git restore` + tool switch to PowerShell here-strings. The agent caught it; the primary session would have caught it via post-completion `git -C <main> status` check anyway. The earlier the verification, the smaller the recovery cost.

**How to apply:** for any subagent dispatch involving a worktree:
1. **In the prompt:** repeat the absolute target path on every instruction line (not just once); explicitly say "verify with `git -C <main> status` AFTER each write to confirm zero modifications in the main worktree"; provide a fallback PowerShell here-string pattern for the agent to switch to if apply_patch misroutes.
2. **In the primary session:** after subagent completion, run `git -C <main_worktree> status --short` AND `find <c-N_worktree> -newer <baseline_file> -name "*.py"` to confirm the changes landed in the cycle worktree only.
3. **If misrouting detected:** revert main worktree changes via `git -C <main> restore .` BEFORE re-dispatching, otherwise the second dispatch may amplify the contamination.

Refines cycle-22 L2 (apply_patch tool footguns) + cycle-43 L1 (worktree from start).

---

## Sub-skill-patch candidates (minor; index in SKILL.md only — no full cycle-lessons.md entry)

- **AC fold-1 spelling normalization:** when folding tests into a canonical home with `pytest -k <keyword>` count requirements, normalize British/American spelling at fold time so the keyword filter matches all expected cases. Cycle 44 had to rename "sanitised"/"sanitiser" → "sanitized"/"sanitizer" mid-implementation. Minor but cosmetic-test-only.

- **DeepSeek prompt size + bidi-char encoding:** when piping `git diff` to DeepSeek direct CLI, large diffs (>100KB) containing bidi/control-char test fixtures can produce JSON encoding errors. Mitigation: filter to diff-stat + targeted file excerpts only; avoid raw `git diff` pipes for prompts >100KB.

- **R2 codex-companion sub-task forwarding:** when codex:codex-rescue agent forwards a long-running review to a sub-task (e.g. `b0ngrd3wr`) and exits without producing the .md output, the primary session's notification is misleading (says "completed" but actual review still running). Per cycle-20 L4 + C35-L2: 10-min 0-byte = fall back to manual verify; don't poll the sub-task.

---

## Operator follow-up (skill-infrastructure migration)

Per cycle-39 L5: skill patches that affect the user-global dev_ds skill MUST be folded into `~/.claude/skills/dev_ds/` infrastructure (NOT this project repo). The 5 C44-L1..L5 candidates above are project-repo audit trail only; operator should:

1. Add C44-L1 to `~/.claude/skills/dev_ds/references/cycle-lessons.md` under "Test authoring" concern area.
2. Add C44-L2 to same file under "Test authoring" (sibling of C44-L1).
3. Add C44-L3 to same file under "Implementation gotchas" — refines C42-L3 (which is currently test-scope-only).
4. Add C44-L4 to same file under "Implementation gotchas" (mid-implementation discovery class).
5. Add C44-L5 to same file under "Subagent dispatch and fallback" — refines cycle-22 L2.
6. Add 5 one-liner index entries to `~/.claude/skills/dev_ds/SKILL.md` under "Accumulated rules index".
7. Cycle-44 commit reference for evidence: `ac8beb8` (cycle-44 squash-merge); R1 + R2 design eval docs at `docs/superpowers/decisions/2026-04-27-cycle-44-design-eval-r2-codex.md` and `.data/cycle-44/r1-deepseek-design.txt`.

---

## Cycle 44 metrics

- **Items:** 23 ACs + 7 CONDITIONS = 30 deliverables
- **Commits:** 5 (4 implementation + 1 doc-update; cycle-44-batch squash-merged as `ac8beb8`)
- **Files:** +27 source files in 2 new packages, −2 flat src files; +2 new test files, −1 deleted test file (folded)
- **Tests:** 3007 → 3019 (+12); Windows local 3008 passed + 11 skipped
- **CVE:** Class B (PR-introduced) = empty; Class A (pre-existing) unchanged at 4 alerts
- **CI:** test job passed in 2m46s on PR #63
- **Wall-clock:** ~3 hours from Step 1 to Step 16 (including ~90 min subagent dispatch wait time across Steps 4/5/8/9/14)
- **Subagent dispatches:** Codex (Step 1, Step 8, Step 9 M1+M2, Step 14 R2) + DeepSeek (Step 4 R1, Step 14 R1) + Opus (Step 5)
- **Phase 4.6 progress:** M1 + M2 + M4 + L1 closed; M3 deferred to cycle 45 with explicit cycle-45 staged scope (M3 6 ACs + M2 compat-shim removal ~25 patches + Q6 29-tool registration test + Q8 lazy-lookup regressions ≈ 35 ACs)

---

## Sign-off

Cycle 44 complete. PR #63 merged as `ac8beb8` on main. Self-review committed to project repo + 5 skill-patch candidates flagged for operator follow-up to `~/.claude/skills/dev_ds/`.
