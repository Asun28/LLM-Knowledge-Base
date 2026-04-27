# Cycle 46 — Phase 4.6 LOW closeout + dep-CVE re-verify + BACKLOG hygiene

**Date:** 2026-04-28
**Branch:** `cycle-46-batch` in worktree `D:/Projects/llm-wiki-flywheel-c46`
**Cycle pattern:** primary-session per C37-L5 (≤15 ACs / ≤5 src files / primary-holds-context)
**Parallel cycles:** OK — running in dedicated worktree per C42-L4 user reminder

## Problem

Two stale BACKLOG entries documenting work already shipped or staged for deletion, plus accumulated dep-CVE drift since cycle-41 last re-verified.

1. **Phase 4.6 LOW** — `lint/_augment_manifest.py` (27 LOC) and `lint/_augment_rate.py` (25 LOC) compat shims were filed in cycle-44 close as "tagged for cycle-45 deletion (avoids 25-site test patch migration in cycle 44)". Cycle 45 focused on M3 mcp/core.py split and did not get to the shim deletion. The shims still exist; the entry now reads as 1-cycle-stale.

2. **Phase 4.6 MEDIUM** — `mcp/core.py` (1149 LOC → 447 LOC after cycle-45 split into `mcp/ingest.py` + `mcp/compile.py`). The BACKLOG entry's "Cycle 44 design Q13 DEFERRED to cycle 45" text is now historical — cycle 45 PR #65 shipped the split. Entry is stale documentation only.

3. **Phase 4.5 MEDIUM dep-CVEs** — last re-verified cycle 41 (2026-04-27 morning). State has not been re-checked across:
   - 4 advisories with no upstream patch (diskcache 5.6.3, ragas 0.4.3, litellm 1.83.0, pip 26.0.1)
   - 3 resolver conflicts (arxiv/requests, crawl4ai/lxml, instructor/rich)
   - 2 Dependabot pip-audit drift entries (litellm GHSA-r75f-5x8p-qvmc + GHSA-v4p8-mg3p-g94g)

   Cycles 39/40/41 each re-verified; this is the established hygiene-cycle pattern.

## Non-goals

- **No new MCP tools / no new validators / no new code paths.** Pure mechanical migration + delete + re-tag.
- **No Phase 5 community-followup items.** Per user instruction "before Phase 5 items".
- **No new CI dimensions.** `windows-latest` matrix re-enable, GHA-Windows multiprocessing, POSIX TestWriteItemFiles all remain DEFERRED to cycle-47+ per cycle-36 L1 (one new CI dimension per cycle; deferred items need self-hosted Windows runner / POSIX shell access this session lacks).
- **No fold of `tests/test_cycle11_task6_mcp_ingest_type.py`** (last cycle-10/11 era file). Defer to cycle-47+ — the file references mcp/core.py + mcp/ingest.py symbols and a fold would interleave with cycle-45's split surface; safer to wait one cycle.
- **No `test_lint_augment_split.py` deletion.** Per cycle-15 L2 DROP-with-test-anchor retention: keep the file as cycle-44 package-structure anchor, drop only the shim-specific test function and invert the `_augment_*.py is_file()` assertion to `not is_file()`.

## Acceptance Criteria

### Group A — Lint shim deletion (Phase 4.6 LOW closeout, cycle-44 → 45 → 46 carry-over)

- **AC1** Test patch migration across 9 test files: replace `kb.lint._augment_manifest` → `kb.lint.augment.manifest` and `kb.lint._augment_rate` → `kb.lint.augment.rate`.
  - 38 patch sites total (per `rg "kb\.lint\._augment_(manifest|rate)" tests/`):
    - `tests/test_backlog_by_file_cycle1.py` (2 sites — function-local imports lines 157, 166)
    - `tests/test_cycle13_frontmatter_migration.py` (2 sites — `monkeypatch.setattr` lines 459, 461)
    - `tests/test_cycle17_resume.py` (1 site — module-top import line 19)
    - `tests/test_cycle9_lint_augment.py` (2 sites — `monkeypatch.setattr` lines 12, 14)
    - `tests/test_v5_kb_lint_signature.py` (1 site — `monkeypatch.setattr` line 52)
    - `tests/test_v5_lint_augment_manifest.py` (6 sites — paired `monkeypatch.setattr` + `from import` × 3)
    - `tests/test_v5_lint_augment_orchestrator.py` (14 sites — `monkeypatch.setattr` × 7 paired pairs)
    - `tests/test_v5_lint_augment_rate.py` (6 sites — paired `monkeypatch.setattr` + `from import` × 3)
  - Verify: full test suite passes; `rg "kb\.lint\._augment_(manifest|rate)" tests/` returns zero hits.

- **AC2** `tests/test_lint_augment_split.py` cycle-44 anchor refresh:
  - Delete `test_augment_compat_shims_resolve_to_new_package` (purpose vanishes when shim deleted).
  - In `test_augment_package_structure_cycle44`: invert `_augment_manifest.py is_file()` and `_augment_rate.py is_file()` assertions → `not is_file()`. This pins the cycle-46 deletion as a structural regression.
  - Keep other tests as-is.

- **AC3** `src/kb/lint/augment/orchestrator.py` lines 79-80: replace function-local imports
  ```python
  from kb.lint._augment_manifest import RESUME_COMPLETE_STATES, Manifest
  from kb.lint._augment_rate import RateLimiter
  ```
  with
  ```python
  from kb.lint.augment.manifest import RESUME_COMPLETE_STATES, Manifest
  from kb.lint.augment.rate import RateLimiter
  ```

- **AC4** `src/kb/lint/augment/manifest.py` lines 166-180: delete `_sync_legacy_shim()` function and module-level `_sync_legacy_shim()` call. Drop the now-orphan `import sys` if no other site uses it.

- **AC5** `src/kb/lint/augment/rate.py` lines 81-88: delete `_sync_legacy_shim()` function and module-level `_sync_legacy_shim()` call. Drop the now-orphan `import sys` if no other site uses it.

- **AC6** Delete `src/kb/lint/_augment_manifest.py`.

- **AC7** Delete `src/kb/lint/_augment_rate.py`.

### Group B — BACKLOG hygiene

- **AC8** Delete Phase 4.6 LOW BACKLOG entry (lines 228-229 of `BACKLOG.md`, plus the cycle-44 "REMAIN as compat shims" comment block that referenced the cycle-45 deletion plan). Resolved by AC3-AC7.

- **AC9** Delete Phase 4.6 MEDIUM `mcp/core.py` BACKLOG entry (lines 211-212). Resolved by cycle-45 PR #65 M3 split (`mcp/core.py` 1149 LOC → 447 LOC, with `mcp/ingest.py` 612 LOC + `mcp/compile.py` 148 LOC). Entry is now stale documentation only.

### Group C — Dep-CVE re-verification (cycle-39/40/41 hygiene pattern)

- **AC10** Re-verify dependency-vulnerability state vs cycle-41 baseline:
  - Run `pip-audit --format=json` against the live `.venv`.
  - Run `gh api repos/Asun28/llm-wiki-flywheel/dependabot/alerts` for current alert set.
  - Re-check `pip index versions {diskcache,ragas,litellm,pip}` for new releases.
  - Re-check `pip download --no-deps litellm==<latest>` METADATA for `Requires-Dist: click==X.Y.Z` (verifying upstream has not relaxed).
  - For each of 4 advisories + 3 resolver conflicts + 2 Dependabot-drift entries: either re-confirm (update cycle tag from cycle-41/cycle-42+ → cycle-47+ in BACKLOG.md) OR document state changes in CHANGELOG (e.g., new release, new advisory, resolver conflict cleared).

### Group D — Doc sync

- **AC11** Multi-site test-count narrative sync per C26-L2 + C39-L3:
  - Run `python -m pytest --collect-only | tail -1` for the authoritative test count.
  - Update count in: `CLAUDE.md`, `docs/reference/testing.md`, `docs/reference/implementation-status.md`, `README.md`.
  - Test-file count: enumerate via `git ls-files tests/test_*.py | wc -l`.
  - File count delta = -2 (delete 2 src compat shim files) + 0 test file deltas (test_lint_augment_split.py edited not deleted, no fold this cycle).

- **AC12** Phase 4.5 HIGH #4 (`tests/` coverage-visibility freeze-and-fold) progress note: append cycle-46 marker noting "no new folds this cycle (cycle-46 prioritised Phase 4.6 LOW shim deletion); ~190+ versioned files still to fold across future cycles."

## Blast radius

| Module | Change | Risk |
|---|---|---|
| `src/kb/lint/_augment_manifest.py` | DELETED | None — shim only; symbols moved to `kb.lint.augment.manifest` since cycle 44 |
| `src/kb/lint/_augment_rate.py` | DELETED | None — same as above |
| `src/kb/lint/augment/orchestrator.py` | 2-line import edit | None — semantically equivalent, just drops the indirection |
| `src/kb/lint/augment/manifest.py` | Drop 15 LOC `_sync_legacy_shim()` | None — once shim is gone, function is dead code |
| `src/kb/lint/augment/rate.py` | Drop 8 LOC `_sync_legacy_shim()` | None — same |
| 9 test files | Path-string replacement only | None mechanically, but `test_v5_lint_augment_orchestrator.py` is a 1000+ LOC file; risk = `Edit replace_all` partial replacement (cycle-24 L1) — mitigate via per-line Edit or post-edit grep verification |
| `BACKLOG.md` | 2 entries deleted, dep-CVE tags refreshed | None — documentation only |
| Doc files (CLAUDE.md, docs/reference/*, README.md) | test-count drift fix | None — narrative only |

**No new attack surface, no new I/O paths, no new public APIs, no new third-party dependencies.**

## Revert path

Single force-push revert if any test fails post-merge. The shim deletion is mechanically reversible by:
1. Recreating `_augment_manifest.py` + `_augment_rate.py` with the cycle-44 content
2. Restoring the `_sync_legacy_shim()` function + call in `manifest.py` + `rate.py`
3. Restoring legacy import paths in `orchestrator.py:79-80`

Test-patch migrations are reversible via `sed s/kb\.lint\.augment\.manifest/kb.lint._augment_manifest/g` (and same for rate).

## Open questions for Step 5 design gate

Q1. Should `test_lint_augment_split.py` be deleted entirely or kept as a structure-anchor with the shim-test removed and `is_file()` inverted?
   - Lean: **kept** per cycle-15 L2 DROP-with-test-anchor retention. The package structure (9 modules) is still cycle-44 contract; the shim ABSENCE is now the cycle-46 contract.

Q2. Should `_sync_legacy_shim()` removal happen as one commit per file (3 commits: orchestrator.py, manifest.py, rate.py) or one batched commit per `feedback_batch_by_file`?
   - Lean: **one commit each per file** since `feedback_batch_by_file` says group HIGH+MED+LOW per file (severities), not flatten different files into one commit.

Q3. AC10 dep-CVE re-verify: if pip 26.1 advisory metadata has been updated since cycle-41 to confirm the patch, do we bump pip pin in this cycle or defer?
   - Lean: **bump if confirmed**, document in CHANGELOG as Class A opportunistic patch (Step 11.5). Else defer per cycle-22 L4 conservative posture.

Q4. AC10 dep-CVE re-verify: if a new advisory drops between cycle-41 and now (e.g., ragas 0.5.0 published with a fix), is this in scope?
   - Lean: **yes** — Step 11.5 Class A opportunistic patch is part of the standard pipeline. New CVE arrival → bump if patched, document in CHANGELOG.

Q5. Should the `lint/augment/manifest.py` and `lint/augment/rate.py` `import sys` lines be removed once `_sync_legacy_shim` is dropped?
   - Lean: **check via grep** — drop if no other reference to `sys` in the file; keep otherwise.

Q6. Should AC1 use `Edit replace_all=True` per file, or per-line `Edit replace_all=False` to dodge cycle-24 L1 multi-line silent-skip?
   - Lean: **replace_all=True with post-edit grep verification** since the substring `kb.lint._augment_manifest` is a single-line literal that Edit can match across all occurrences. Per cycle-24 L1, this is safer than multi-line patterns. Verify with `rg "kb\.lint\._augment_(manifest|rate)" tests/ src/` returning zero hits after each AC.

Q7. Should the cycle-44 "REMAIN as compat shims" comment block in BACKLOG.md (line ~206-209) be deleted, or replaced with a "Cycle 46 closed" entry?
   - Lean: **delete the historical comment** since CHANGELOG-history captures the full chain (cycle-44 deferred → cycle-45 deferred → cycle-46 deleted). BACKLOG.md is open work only per its own format guide.

Q8. Step 4 design eval — skip or run?
   - Lean: **SKIP** per skill text "trivial one-liner" — this is a mechanical migration + delete + re-tag cycle with no novel design decisions. Cycle-39/40/41/42 precedent.

Q9. Step 6 Context7 — skip or run?
   - Lean: **SKIP** per skill text "pure stdlib/internal code" — no third-party libraries are touched; only internal `kb.lint.augment.*` paths.

Q10. Step 9.5 simplify — skip or run?
   - Lean: **SKIP** per skill text "trivial diff (<50 LoC)" + "signature-preserving refactor" — total `src/` diff after AC3-AC7 is roughly +0 / -75 LOC (net deletion), behavior-preserving.

## Test plan

- All 12 ACs verified by full pytest pass (3027 → 3026 expected: AC2 deletes 1 test from `test_lint_augment_split.py`).
- `pytest --collect-only | tail -1` final count cross-checked against doc updates.
- `rg "kb\.lint\._augment_(manifest|rate)" tests/ src/` returns zero hits.
- `ls src/kb/lint/_augment_*.py` returns no files.
- Full suite under Windows local: target `3025 passed + 11 skipped` (3027 baseline − 2 deleted: 1 shim test + 1 unique reference; actual depends on AC2 count).

## Step routing decisions

| Step | Decision | Reason |
|---|---|---|
| 1 | **Run** primary | required |
| 2 | **Run** primary | dep-CVE baseline mandatory; trust-boundary minimal |
| 3 | **Skip** | Hygiene cycle; no novel design |
| 4 | **Skip** | Trivial mechanical migration |
| 5 | **Run** Opus subagent | Mandatory per skill |
| 6 | **Skip** | No third-party libs |
| 7 | **Run** primary | C37-L5 (≤15 ACs / ≤5 src files / primary holds context) |
| 8 | **Run** primary | C37-L5; gate verifies primary's plan |
| 9 | **Run** primary, TDD | Mechanical migration; primary fastest |
| 9.5 | **Skip** | <50 LoC src diff, signature-preserving |
| 10 | **Run** | Mandatory |
| 11 | **Run** primary | Mandatory; minimal threat surface |
| 11.5 | **Run** primary | Class A opportunistic dep-bump if any |
| 12 | **Run** primary | Mandatory |
| 13 | **Run** primary | Mandatory |
| 14 | **Run** R1 DeepSeek (direct CLI) + R1 Codex (agent) parallel; R2 Codex verify | Mandatory; default per cycle-39 L1 amendment |
| 15 | **Run** | Mandatory |
| 16 | **Run** Opus main | Mandatory |
