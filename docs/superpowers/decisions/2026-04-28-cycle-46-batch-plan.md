# Cycle 46 — Step 7 Implementation Plan

**Date:** 2026-04-28
**Inputs:** requirements.md (12 ACs), threat-model.md (T1-T5), design.md (PROCEED-WITH-CONDITIONS, 7 binding CONDITIONS, 7 amendments)

## Step 8 plan-gate verdict — APPROVE (primary-session per C37-L5 + cycle-21 L1)

| Coverage | Status |
|---|---|
| All 12 ACs → 6 implementation tasks | AC1→T1 / AC2→T3 / AC3→T1 / AC4→T2 / AC5→T2 / AC6→T3 / AC7→T3 / AC8→T4 / AC9→T4 / AC10→T5 / AC11→T6 / AC12→T6 |
| All 5 threat-model items → step gates | T1→Step 11; T2→T1+T2 deletion-only; T3→T1 ordering + T3 forward-protection; T4→T4 deletion + T5 tag refresh; T5→T6 multi-site grep |
| All 7 design CONDITIONS → tasks | C1→T1 / C2→T3 / C3→T3 / C4→T2 / C5→T5 + Step 11.5 / C6→T6 / C7→T4 |
| Test expectations explicit per task | T1 targeted pytest + grep; T2 targeted + grep; T3 full suite (cycle-22 L3); T4-T6 grep-only doc edits |
| PLAN-AMENDS-DESIGN: needed? | No — plan honours design Q2 commit cadence (with bundling); honours design Q6 Edit replace_all=True with mandatory grep verification |
| Plan-gate dispatch | Primary session per C37-L5 (12 ACs ≤ 15 threshold + ≤5 src files + primary holds full context from Steps 1-5) |


## Plan summary

6 implementation tasks → 6 logical commits + 1 self-review commit (Step 16) = 7 total. Squash-merge collapses to 1 commit on `main` per cycle-36 L1 / cycle-44 / cycle-45 precedent.

Each task lists: files modified (grep-confirmed paths), what to change, failing test that must pass, AC ref, threat-model ref, design CONDITION ref.

## TASK 1 — Test patch migration (AC1) + orchestrator import flip (AC3)

**Goal:** keep tests green throughout the cycle by migrating ALL test patch sites + production caller to the package paths in ONE commit. The shims still exist and still re-export, so this commit is semantically equivalent (no test should fail).

**Files (9 total):**

Test files (8) — `Edit replace_all=True` per file with 2 Edit calls (one for `_augment_manifest`, one for `_augment_rate`) per Q6 / cycle-24 L1 single-line literal pattern:

| File | Sites | Patterns to migrate |
|---|---|---|
| `tests/test_backlog_by_file_cycle1.py` | 2 | `from kb.lint._augment_manifest import Manifest` (line 157), `from kb.lint._augment_rate import RateLimiter` (line 166) |
| `tests/test_cycle13_frontmatter_migration.py` | 2 | `monkeypatch.setattr("kb.lint._augment_manifest.MANIFEST_DIR", ...)` (line 459), `"kb.lint._augment_rate.RATE_PATH"` (line 461) |
| `tests/test_cycle17_resume.py` | 1 | `from kb.lint._augment_manifest import Manifest` (line 19) |
| `tests/test_cycle9_lint_augment.py` | 2 | `monkeypatch.setattr("kb.lint._augment_manifest.MANIFEST_DIR", ...)` (line 12), `"kb.lint._augment_rate.RATE_PATH"` (line 14) |
| `tests/test_v5_kb_lint_signature.py` | 1 | `monkeypatch.setattr("kb.lint._augment_manifest.MANIFEST_DIR", ...)` (line 52) |
| `tests/test_v5_lint_augment_manifest.py` | 6 | 3× `monkeypatch.setattr("kb.lint._augment_manifest.MANIFEST_DIR", ...)` + 3× `from kb.lint._augment_manifest import Manifest` |
| `tests/test_v5_lint_augment_orchestrator.py` | 16 | 7× paired `monkeypatch.setattr("kb.lint._augment_manifest.MANIFEST_DIR", ...)` + `"kb.lint._augment_rate.RATE_PATH"` (lines 397/399, 460/462, 515/517, 566/568, 678/680, 982/984, 1039/1041) + 2× lone `monkeypatch.setattr("kb.lint._augment_rate.RateLimiter", ...)` (lines 996, 1051) |
| `tests/test_v5_lint_augment_rate.py` | 6 | 3× `monkeypatch.setattr("kb.lint._augment_rate.RATE_PATH", ...)` + 3× `from kb.lint._augment_rate import RateLimiter` |

**TOTAL: 36 sites across 8 files** (corrected from 38/9 in requirements per CONDITION 1).

Production file (1):

| `src/kb/lint/augment/orchestrator.py` | 2 sites | function-local imports at lines 79-80: `from kb.lint._augment_manifest import RESUME_COMPLETE_STATES, Manifest` → `from kb.lint.augment.manifest import RESUME_COMPLETE_STATES, Manifest`; `from kb.lint._augment_rate import RateLimiter` → `from kb.lint.augment.rate import RateLimiter` |

**Per-file verification gate** (cycle-24 L1):
After each file's Edit pair, run `rg -c "kb\.lint\._augment_(manifest|rate)" <file>` — expected output: 0. If non-zero, halt and inspect missed sites.

**Whole-task verification:**
- `rg "kb\.lint\._augment_(manifest|rate)" tests/` → ONLY hits in `tests/test_lint_augment_split.py` (4 sites — those belong to AC2)
- `rg "kb\.lint\._augment_(manifest|rate)" src/kb/lint/augment/orchestrator.py` → 0 hits

**Failing test (TDD pattern):** none — semantically equivalent migration. Run targeted `pytest tests/test_v5_lint_augment_orchestrator.py tests/test_v5_lint_augment_manifest.py tests/test_v5_lint_augment_rate.py -x -q` to confirm green post-Edit.

**Criteria refs:** AC1, AC3
**Threat refs:** T3 (test contract preservation under shim path migration)
**Design CONDITIONS:** 1 (corrected scope), 6 (Edit replace_all=True)

**Commit message:** `cycle 46 TASK 1: migrate 36 test patches + orchestrator caller from kb.lint._augment_* to kb.lint.augment.*`

## TASK 2 — Drop `_sync_legacy_shim()` from manifest.py + rate.py (AC4 + AC5)

**Goal:** remove the now-dead `_sync_legacy_shim()` machinery from the two cycle-44 package modules.

**Files:**

`src/kb/lint/augment/manifest.py`:
- Delete `import sys` (line 7) per CONDITION 4 — only used by `_sync_legacy_shim`.
- Delete `_sync_legacy_shim()` function definition (lines 166-177 — 12 lines).
- Delete module-level `_sync_legacy_shim()` call (line 180).

`src/kb/lint/augment/rate.py`:
- Delete `import sys` (line 6) per CONDITION 4 — only used by `_sync_legacy_shim`.
- Delete `_sync_legacy_shim()` function definition (lines 81-85 — 5 lines).
- Delete module-level `_sync_legacy_shim()` call (line 88).

**Verification:**
- `rg "_sync_legacy_shim" src/kb/lint/augment/` → 0 hits
- `rg "^import sys" src/kb/lint/augment/manifest.py` → 0 hits
- `rg "^import sys" src/kb/lint/augment/rate.py` → 0 hits
- `rg "^import sys" src/kb/lint/augment/orchestrator.py` → 1 hit (PRESERVED per CONDITION 4)
- Targeted pytest: `pytest tests/test_v5_lint_augment_manifest.py tests/test_v5_lint_augment_rate.py tests/test_lint_augment_split.py -x -q` → green (shim files still exist; their re-exports + cycle-44 `__init__` still resolve symbols)

**Failing test (TDD):** none — pure dead-code removal; the shims' own `from kb.lint.augment.manifest import (...)` statements continue to resolve symbols.

**Criteria refs:** AC4, AC5
**Threat refs:** T2 (no new attack surface — pure deletion)
**Design CONDITIONS:** 4 (`import sys` removal)

**Commit message:** `cycle 46 TASK 2: drop _sync_legacy_shim() + import sys from manifest.py + rate.py`

## TASK 3 — Anchor refresh + delete shim files (AC2 + AC6 + AC7)

**Goal:** Land AC2 anchor refresh + shim file deletions in ONE commit so the branch never has a failing-test state. Per Step 10 CI hard gate "All pass or stop. No exceptions."

**Files (3 modified, 2 deleted):**

`tests/test_lint_augment_split.py` (AC2):
- Delete `test_augment_compat_shims_resolve_to_new_package` function (lines 54-61).
- In `test_augment_package_structure_cycle44`:
  - Invert assertion at line 25: `assert (ROOT / "src" / "kb" / "lint" / "_augment_manifest.py").is_file()` → `assert not (ROOT / "src" / "kb" / "lint" / "_augment_manifest.py").is_file()`
  - Invert assertion at line 26: same for `_augment_rate.py`.
  - **Add behavioral importability assertions per CONDITION 2:**
    ```python
    import pytest
    with pytest.raises(ModuleNotFoundError):
        import kb.lint._augment_manifest  # noqa: F401
    with pytest.raises(ModuleNotFoundError):
        import kb.lint._augment_rate  # noqa: F401
    ```
- Add new test `test_run_augment_docstring_survives_cycle46_import_flip` per CONDITION 3:
  ```python
  def test_run_augment_docstring_survives_cycle46_import_flip() -> None:
      from kb.lint.augment.orchestrator import run_augment
      assert run_augment.__doc__ is not None
      assert "Three-gate" in run_augment.__doc__
  ```
- Keep `test_augment_package_reexports_match_former_flat_symbols_cycle44` and `test_augment_package_imports_with_nonexistent_wiki_dir_cycle44` unchanged.

Add module-level `import pytest` at top of file (currently has `from __future__ import annotations`, `import importlib`, `from pathlib import Path`).

`src/kb/lint/_augment_manifest.py` — DELETE (AC6).
`src/kb/lint/_augment_rate.py` — DELETE (AC7).

**Verification:**
- `ls src/kb/lint/_augment_*.py` → "No such file or directory" or empty
- `rg "kb\.lint\._augment_(manifest|rate)" src/ tests/` → 0 hits except inside `test_lint_augment_split.py`'s `pytest.raises(...): import kb.lint._augment_manifest` blocks (that's the test asserting absence)
- `pytest tests/test_lint_augment_split.py -x -q` → green; 3 tests + 1 new doc test = 4 tests in file (was 4 + the deleted shim test = 5 → now 4 net change after AC2 deletion)

Wait — let me recount: original was 4 tests; AC2 deletes 1 (`test_augment_compat_shims_resolve_to_new_package`) and adds 1 new (`test_run_augment_docstring_survives_cycle46_import_flip`). Net: 4 - 1 + 1 = 4 tests in the file. Total suite delta: +0 from this file (test count stays same as far as this file goes); but cycle wide delta is -1 because `test_augment_compat_shims_resolve_to_new_package` was the only deletion (no other test additions in this cycle).

Actually let me reconsider — the new `test_run_augment_docstring_survives_cycle46_import_flip` is a NET-NEW test. So:
- AC2 deletion: -1 test (`test_augment_compat_shims_resolve_to_new_package`)
- AC2 addition: +1 test (`test_run_augment_docstring_survives_cycle46_import_flip`)
- Net cycle-wide delta: 0

Wait no — design CONDITION 2 says behavioral assertions go INSIDE `test_augment_package_structure_cycle44` (not as new test functions). So that's +0 tests there. Only the new `test_run_augment_docstring_survives_cycle46_import_flip` is +1.

Net delta: -1 + 1 = 0. Test count stays at 3025.

Actually wait — let me re-read CONDITION 2: "test_augment_package_structure_cycle44 MUST add `with pytest.raises(...)`...". So the additions go INSIDE the existing test. CONDITION 3 says the docstring assertion is a sibling test. So:
- `test_augment_package_structure_cycle44`: KEEP, EDIT to add 2 raises blocks
- `test_augment_package_reexports_match_former_flat_symbols_cycle44`: KEEP unchanged
- `test_augment_package_imports_with_nonexistent_wiki_dir_cycle44`: KEEP unchanged
- `test_augment_compat_shims_resolve_to_new_package`: DELETE
- `test_run_augment_docstring_survives_cycle46_import_flip`: ADD as new test

Net delta: 4 → 4 (3 unchanged + 1 deleted + 1 added = 4). Net cycle-wide delta = 0 unless somewhere else changes.

So Test count goes 3025 → 3025 (no net delta).

Hmm but the design summary said "post-cycle expected is 3024" (subtract 1 from AC2 deletion). That assumed AC2 only deletes — didn't account for the docstring forward-protection ADD per CONDITION 3.

CORRECTION: Test count delta = 0. Post-cycle expected: 3025 / 243 (unchanged).

**Failing test (TDD pattern):** AC2's inverted `not is_file()` and `pytest.raises(ModuleNotFoundError)` assertions FAIL while shims still exist. They PASS once AC6+AC7 delete the files. Same commit handles both.

**Criteria refs:** AC2, AC6, AC7
**Threat refs:** T3, T4 (deferred-promise sync)
**Design CONDITIONS:** 2 (forward-protection), 3 (docstring assertion)

**Commit message:** `cycle 46 TASK 3: refresh test_lint_augment_split.py anchor + delete _augment_manifest.py + _augment_rate.py shims`

## TASK 4 — BACKLOG.md cleanup (AC8 + AC9)

**Goal:** delete the 2 stale BACKLOG entries.

**File:** `BACKLOG.md`

Edits:
- Delete lines 211-212 (Phase 4.6 MEDIUM `mcp/core.py` entry — resolved by cycle-45 PR #65).
- Delete lines 222-226 (cycle-44 historical comment block — `Cycle 44 closed (2026-04-27): L1 lint/_augment_manifest.py + lint/_augment_rate.py absorbed...`).
- Delete lines 228-229 (Phase 4.6 LOW shim entry — resolved by AC6+AC7).
- KEEP lines 216-221 (cycle-42 closed comment block — covers separate L1/L2/L4/L5 items).

**Verification:**
- `grep -n "mcp/core.py" BACKLOG.md` → no Phase 4.6 MEDIUM hits
- `grep -n "_augment_manifest\.py\|_augment_rate\.py" BACKLOG.md` → no Phase 4.6 LOW or cycle-44 historical hits
- `grep -nE "## Phase 4.6" BACKLOG.md` → still shows Phase 4.6 header
- `grep -nE "### MEDIUM" BACKLOG.md` (line ~197) — Phase 4.6 MEDIUM section now contains only the "Cycle 42 closed" comment block (no open items) → consider whether to collapse Phase 4.6 MEDIUM section to "_All items resolved — see CHANGELOG cycle 42 + cycle 44 + cycle 45 + cycle 46._" per BACKLOG.md format guide collapse-when-empty rule.
- Same check for Phase 4.6 LOW section (line ~214) — after AC8 deletion, the section contains only the cycle-42 closed comment + cycle-44 closed comment (now both historical empty pointers); collapse to "_All items resolved — see CHANGELOG cycle 42 + cycle 44 + cycle 46._"

**Failing test (TDD):** none — documentation-only edit. Confirmation via greps above.

**Criteria refs:** AC8, AC9
**Threat refs:** T4 (deferred-promise BACKLOG sync)
**Design CONDITIONS:** 7 (BACKLOG cleanup completeness)

**Commit message:** `cycle 46 TASK 4: delete 2 stale Phase 4.6 BACKLOG entries (LOW shims + MEDIUM mcp/core.py)`

## TASK 5 — Dep-CVE re-verification + BACKLOG tag refresh (AC10)

**Goal:** bump cycle tags from `cycle-41+` → `cycle-47+` on all 9 dep-CVE items per CONDITION 5 / Q11 / cycle-23 L3 / cycle-39/40/41 precedent.

**Files:** `BACKLOG.md` (Phase 4.5 MEDIUM section)

Items to re-tag:

1. `requirements.txt` `diskcache==5.6.3` (line ~126) — append "(cycle-46 re-confirmed 2026-04-28: pip-audit fix_versions=[]; pip index versions → 5.6.3 = LATEST)"
2. `requirements.txt` `ragas==0.4.3` (line ~129) — append cycle-46 re-confirm
3. `requirements.txt` `litellm==1.83.0` (line ~132) — append cycle-46 re-confirm + 1.83.14 click==8.1.8 METADATA verification
4. `requirements.txt` `pip==26.0.1` (line ~135) — append cycle-46 re-confirm + GHSA-58qw-9mgm-455v `firstPatchedVersion: null` verification
5. `requirements.txt` resolver conflicts (line ~158) — append cycle-46 re-confirm of all 3 verbatim
6. `tests/` windows-latest CI matrix re-enable (line ~164) — re-tag `cycle-40+` → `cycle-47+`
7. `tests/` GHA-Windows multiprocessing spawn investigation (line ~166) — re-tag `cycle-40+` → `cycle-47+`
8. `tests/test_capture.py::TestWriteItemFiles` POSIX off-by-one (line ~168) — re-tag `cycle-40+` → `cycle-47+`
9. `Dependabot pip-audit drift on litellm GHSA-r75f-5x8p-qvmc` (line ~170) — re-tag `cycle-41+` → `cycle-47+` + cycle-46 re-confirm
10. `Dependabot pip-audit drift on litellm GHSA-v4p8-mg3p-g94g` (line ~172) — re-tag `cycle-41+` → `cycle-47+` + cycle-46 re-confirm

(Items 6-8 are the deferred CI-related items that need self-hosted Windows runner / POSIX shell access — same as cycle-39/40/41 deferral pattern.)

**Verification:**
- `grep -c "cycle-46 re-confirmed 2026-04-28" BACKLOG.md` → expected count = 7 (4 dep-CVEs + 3 resolver conflicts collapsed into 1 entry + 2 Dependabot drift = 7 distinct re-confirms; or count individually if the resolver-conflicts entry is split)
- `grep -nE "cycle-(41|42|43|44|45)\+" BACKLOG.md` → for any items being bumped, expected = 0 hits after edit (all bumped to `cycle-47+`)
- `grep -nE "cycle-47\+" BACKLOG.md` → expected = 9 hits

**Failing test (TDD):** none — documentation-only edit.

**Criteria refs:** AC10
**Threat refs:** T1 (Class B PR-introduced CVE diff verification at Step 11)
**Design CONDITIONS:** 5 (Step 11.5 dep-CVE re-confirm)

**Commit message:** `cycle 46 TASK 5: re-confirm 9 dep-CVE BACKLOG entries; bump cycle tags cycle-41+ → cycle-47+`

## TASK 6 — Doc-sync (AC11 + AC12) + CHANGELOG/CHANGELOG-history

**Goal:** propagate test count + version + cycle-46 narrative to all doc-sync sites.

**Files:**

`CLAUDE.md` (Quick Reference line 6):
- Update `3027 tests / 244 files (3016 passed + 11 skipped on Windows local; ...)` → `3025 tests / 243 files (3014 passed + 11 skipped on Windows local; ...)`. (3025 / 243 / 3014 numbers per CONDITION 6; the 3014 is 3025 - 11 skipped from cycle-45's "11 skipped" pattern.)

Wait — actual local pass/skip counts must come from `pytest -q | tail -3` post-cycle. Let me revise to "actual numbers TBD post-Step-10".

`docs/reference/testing.md` — grep for `3027`, `244`, replace with post-cycle numbers.
`docs/reference/implementation-status.md` — same.
`README.md` — grep for `3027`, `244`, replace.

`CHANGELOG.md`:
- Add cycle 46 entry to `[Unreleased]` Quick Reference at the top, newest first:
  ```
  #### 2026-04-28 — cycle 46 (Phase 4.6 LOW closeout — lint/_augment_*.py shim deletion + dep-CVE re-verify + BACKLOG hygiene)

  - Items: 12 AC (AC1-AC12) / 3 src files modified + 2 deleted (orchestrator.py imports + manifest.py drop _sync_legacy_shim + rate.py drop _sync_legacy_shim + _augment_manifest.py DELETED + _augment_rate.py DELETED) / 1 test file modified (test_lint_augment_split.py anchor refresh + 1 new docstring forward-protection test) + 8 test files migrated (36 path strings replaced) + BACKLOG.md (2 stale Phase 4.6 entries deleted + 9 dep-CVE entries re-tagged cycle-41+ → cycle-47+) + CLAUDE.md / docs/reference/testing.md / docs/reference/implementation-status.md / README.md test-count drift narrative + 4 cycle-46 decision docs / +TBD commits (Step-7 plan expects 6 implementation + 1 self-review = 7 total)
  - Tests: 3025 → 3025 (-1 from AC2 deletion of `test_augment_compat_shims_resolve_to_new_package`; +1 from AC2 addition of `test_run_augment_docstring_survives_cycle46_import_flip` per CONDITION 3 forward-protection; net 0)
  - Scope:
    Phase 4.6 LOW closeout — `lint/_augment_*.py` shim deletion deferred from cycle-44 → cycle-45 → cycle-46. Closes 2 of 2 Phase 4.6 BACKLOG entries (LOW lint shim files + MEDIUM mcp/core.py — the latter was stale documentation only since cycle-45 PR #65 already shipped the M3 split). Migrated 36 test patch sites across 8 test files from `kb.lint._augment_manifest` / `kb.lint._augment_rate` paths to `kb.lint.augment.manifest` / `kb.lint.augment.rate` per Q6 / cycle-24 L1 single-line literal `Edit replace_all=True` with mandatory post-edit grep verification. Switched 2 production caller imports in `src/kb/lint/augment/orchestrator.py:79-80` (function-local lazy imports inside `run_augment`) per cycle-23 L1 SAFE-confirmed-by-grep. Dropped `_sync_legacy_shim()` + `import sys` from `manifest.py` + `rate.py` per CONDITION 4 ruff F401 forced removal. Deleted `_augment_manifest.py` (27 LOC) + `_augment_rate.py` (25 LOC). Refreshed `test_lint_augment_split.py` cycle-44 anchor: dropped `test_augment_compat_shims_resolve_to_new_package`, inverted 2× `is_file()` to `not is_file()`, added `pytest.raises(ModuleNotFoundError)` behavioral assertions per CONDITION 2 / `feedback_test_behavior_over_signature` / C40-L3, added `test_run_augment_docstring_survives_cycle46_import_flip` per CONDITION 3 / cycle-23 L1 forward-protection. Re-confirmed 9 dep-CVE BACKLOG entries unchanged (4 advisories: diskcache 5.6.3 / ragas 0.4.3 / litellm 1.83.0 / pip 26.0.1 all `fix_versions=[]` per pip-audit; pip 26.1 advisory metadata still `firstPatchedVersion: null` per `gh api graphql` — DO NOT bump pin per cycle-22 L4; 3 resolver conflicts persist; 2 Dependabot drift entries litellm GHSA-r75f-5x8p-qvmc + GHSA-v4p8-mg3p-g94g still not emitted by pip-audit). Bumped cycle tags `cycle-41+` → `cycle-47+` on all 9 items per cycle-23 L3 + cycle-39/40/41 precedent. Steps 1-2 + 5 + 7-15 ran primary-session per C37-L5 (≤15 ACs / ≤5 src files / primary holds context); Step 4 + 6 + 9.5 SKIPPED per skip-eligibility (hygiene cycle, no third-party libs, signature-preserving deletion). Cycle-46 worktree at `D:/Projects/llm-wiki-flywheel-c46` per C42-L4 from-the-start isolation. Zero PR-introduced CVEs (Step 11 baseline-vs-postcheck diff = empty set; cycle 46 changes 0 dependencies).
  - Detail: [history archive](CHANGELOG-history.md#2026-04-28--cycle-46)
  ```

`CHANGELOG-history.md`:
- Add full per-cycle bullet-level detail under `## 2026-04-28 — cycle 46`. Mirror the cycle-45 / cycle-44 / cycle-43 archive entry shape (~200 lines of bullet detail).

**Verification:**
- `grep -n "3025\|3027" CLAUDE.md docs/reference/testing.md docs/reference/implementation-status.md README.md` — all hits should be the corrected `3025` (or post-cycle-10 number if that turns out different).
- `grep -nE "244|243" CLAUDE.md docs/reference/testing.md docs/reference/implementation-status.md README.md` — 243 should be the file count.

**Phase 4.5 HIGH #4 progress note (AC12):**
- Edit `BACKLOG.md` lines ~91 (the Phase 4.5 HIGH #4 progress note that already contains "cycle-44 progress: 20 files folded total..."): append `Cycle 46: no new folds (cycle-46 prioritised Phase 4.6 LOW shim deletion); ~190+ versioned files still to fold across future cycles.`

**Failing test (TDD):** none — doc-only edits.

**Criteria refs:** AC11, AC12
**Threat refs:** T5 (doc-text drift on test count)
**Design CONDITIONS:** 6 (count drift fix to 3025 baseline)

**Commit message:** `cycle 46 TASK 6: doc-sync test count 3027/244 → 3025/243 per CLAUDE.md drift; CHANGELOG/CHANGELOG-history cycle 46 entries`

## Step ordering note — Step 11.5 DEFERRED

Per the design Q3 + Q4 resolution, Step 11.5 will run as a no-op patch step this cycle:
- 4 advisories: no upstream fix → no patch
- pip 26.1: advisory not refreshed → no patch per cycle-22 L4
- 3 resolver conflicts: no upstream relaxation → no patch
- 2 Dependabot drifts: no pip-audit emission → no `--ignore-vuln` change

The verification commands STILL RUN (CONDITION 5) — they just produce no diff, only re-confirmations folded into TASK 5's BACKLOG tag refresh.

## Step 14 — PR review routing

Per cycle-39 L1 amendment:
- R1 architecture role: `Agent(subagent_type="deepseek-rescue", ...)` — but per C39-L1, prefer DIRECT CLI via Bash for fabrication-risk avoidance: `/c/Users/Admin/.claude/bin/deepseek --model deepseek-v4-pro --think --effort high`.
- R1 edge-case role: `Agent(subagent_type="codex:codex-rescue", ...)` — direct agent dispatch per C39-L1 amendment.
- R2 verify role: same Codex agent.
- R3 audit-doc drift: dispatch only if AC ≥ 25 OR design Qs ≥ 10 (cycle 46 has 12 ACs + 13 resolved Qs — TRIGGERS R3 per cycle-17 L4 (b)+(d) thresholds).

So cycle 46 will run **R1 parallel + R2 + R3 audit-doc drift** — same shape as cycles 17-22.

## TaskList sequencing

| Step | Task | Status |
|---|---|---|
| 9 | TASK 1 — AC1 + AC3 | TODO |
| 9 | TASK 2 — AC4 + AC5 | TODO |
| 9 | TASK 3 — AC2 + AC6 + AC7 | TODO |
| 9 | TASK 4 — AC8 + AC9 (BACKLOG cleanup) | TODO |
| 9 | TASK 5 — AC10 (dep-CVE BACKLOG tag refresh) | TODO |
| 9 | TASK 6 — AC11 + AC12 (doc-sync) | TODO |
| 10 | CI hard gate — full pytest + ruff | TODO |
| 11 | Security verify | TODO |
| 11.5 | Class A opportunistic — confirmed no-op | TODO |
| 12 | (TASK 6 above is the doc-update; nothing more here) | TODO |
| 13 | Branch finalise + PR | TODO |
| 14 | R1 + R2 + R3 (per AC ≥ 12 trigger) | TODO |
| 15 | Merge + cleanup + late-arrival CVE warn | TODO |
| 16 | Self-review + skill patch | TODO |
