# Cycle 56 — Implementation Plan

**Date:** 2026-05-02
**Branch:** worktree-cycle-56
**Source design:** `2026-05-02-cycle56-folds-design.md`

Per cycle-14 L1 + cycle-37 L5: plan drafted in primary session — 11 ACs, primary holds full context from Steps 1–5, all targets grep-verified at Step 4. Plan-gate runs in primary per cycle-21 L1 (no code-exploration gaps).

---

## Picks claimed (parallel-cycle collision avoidance — AC8)

5 versioned source files, 6 receiver files. None overlap with cycle-53 receivers (`test_compile.py`, `test_config.py`, `test_query.py`) or cycle-54 receivers (`test_mcp_browse_health.py`, `test_models.py`, `test_lint.py`).

| # | Source file | Receiver(s) | Tests | Class / section name |
|---|-------------|-------------|-------|---------------------|
| AC1 | `tests/test_v01012_mcp_validation.py` | `tests/test_mcp_core.py` | 7 | `TestMcpInputValidation` (cross-module precedent: TestKbCaptureWrapper) |
| AC2 | `tests/test_v0916_task09.py` | `tests/test_v070.py` | 3 | 3 classes preserved: TestCompileExitCode, TestCliSourceTypeList, TestVersionBump |
| AC3a | `tests/test_v01013_cli_error_truncation.py` (5 CLI tests) | `tests/test_cli.py` | 5 | `TestCliErrorTruncation` |
| AC3b | `tests/test_v01013_cli_error_truncation.py` (2 truncate tests) | `tests/test_utils_text.py` | 2 | bare functions |
| AC4 | `tests/test_v01001_utils_fixes.py` | `tests/test_utils.py` | 5 | `TestUtilsFixes` (helper rename `_write_page` → `_write_concept_page`) |
| AC5 | `tests/test_phase4_audit_concurrency.py` | `tests/test_utils_io.py` | 4 | `TestFileLockConcurrency` |

Total tests folded: **26** (7+3+5+2+5+4). Test count preserved at **3026**. File count: **219 → 214** (-5).

Commit graph (in order):

1. `docs(cycle 56): design + plan for 5-fold batch (parallel-safe with 53/54)` — design.md + plan.md (this doc)
2. `test(cycle 56): fold test_v01012_mcp_validation into test_mcp_core.py (1/5)`
3. `test(cycle 56): fold test_v0916_task09 into test_v070.py (2/5)`
4. `test(cycle 56): fold test_v01013_cli_error_truncation into test_cli.py (3a/5)` — CLI half
5. `test(cycle 56): fold test_v01013_cli_error_truncation truncate tests into test_utils_text.py (3b/5)` — utils half + delete source
6. `test(cycle 56): fold test_v01001_utils_fixes into test_utils.py (4/5)`
7. `test(cycle 56): fold test_phase4_audit_concurrency into test_utils_io.py (5/5)`
8. `docs(cycle 56): doc-sync for 5-fold batch + Step 15 deferred-patch finding`
9. (Step 20 R1/R2 fix-commits as needed)
10. `docs(cycle 56): self-review scorecard + skill-patch lessons` (Step 24)

---

## TASK 1 — AC1: fold test_v01012_mcp_validation.py into test_mcp_core.py

**Files:**
- READ: `tests/test_v01012_mcp_validation.py` (verbatim source)
- READ: `tests/test_mcp_core.py` (find tail; existing class shape)
- EDIT: `tests/test_mcp_core.py` (append class `TestMcpInputValidation`)
- DELETE: `tests/test_v01012_mcp_validation.py`

**Change:**
1. Append a new section comment header `# ── Input validation across MCP tools (cycle 56 fold) ─` near the tail.
2. Append class `TestMcpInputValidation` containing the 7 functions converted to methods (rename `def test_X(...)` → `def test_X(self, ...)`; add monkeypatch parameter where used). Imports stay function-local (already function-local in source).
3. Delete source.

**Test:** `python -m pytest tests/test_mcp_core.py -x --tb=short` green; revert-verify: insert `assert False` at top of `test_kb_query_rejects_overlong_question`, run pytest -x, FAIL; restore.

**Criteria:** AC1, AC6 (count delta), AC7 (commit format).

**Threat:** T1 (revert-verify), T2 (no helper rename in this fold).

## TASK 2 — AC2: fold test_v0916_task09.py into test_v070.py

**Files:**
- READ: `tests/test_v0916_task09.py` (3 classes: TestCompileExitCode + TestCliSourceTypeList + TestVersionBump)
- READ: `tests/test_v070.py` (numbered-section style)
- EDIT: `tests/test_v070.py` (append 3 classes preserving class boundaries per C40-L5)
- DELETE: `tests/test_v0916_task09.py`

**Change:**
1. Append a new numbered section header `# ── 11. Phase 3.97 task 09 — CLI fixes + version bump (cycle 56 fold) ─` near the tail.
2. Append 3 classes verbatim. `from kb.cli import cli` already module-top in test_v070.py? grep first; if not, function-local imports (already function-local in source).
3. Delete source.

**Test:** `python -m pytest tests/test_v070.py -x --tb=short` green; revert-verify on `test_compile_errors_exit_code_1` (assert False); FAIL; restore.

**Criteria:** AC2, AC6, AC7. **CONDITION 5 (host-shape preservation): 3 classes remain distinct, NOT merged.**

## TASK 3a — AC3a: fold 5 CLI tests from test_v01013_cli_error_truncation.py into test_cli.py

**Files:**
- READ: `tests/test_v01013_cli_error_truncation.py` (5 CLI tests via runner.invoke; 2 truncate tests will go to AC3b)
- READ: `tests/test_cli.py` (find tail)
- EDIT: `tests/test_cli.py` (append class `TestCliErrorTruncation` with 5 methods)
- (do NOT delete source yet — AC3b deletes after both halves land)

**Change:**
1. Append section comment `# ── Long-error truncation across CLI commands (cycle 56 fold) ─`.
2. Append class `TestCliErrorTruncation` containing 5 methods converted from the 5 CLI-truncation tests. Each test has its own monkeypatch import (function-local). Convert `def test_X(monkeypatch)` → `def test_X(self, monkeypatch)`. The `runner_cli = CliRunner()` shadow in `test_lint_error_truncates_long_message` MUST be preserved as-is (the source uses local name `runner` for the imported pipeline.runner module then `runner_cli` for the CliRunner — preserve verbatim).
3. **Do NOT delete source** in this commit; deletion happens in TASK 3b after the truncate-helper tests are also moved.

**Test:** `python -m pytest tests/test_cli.py -x --tb=short` green; revert-verify on `test_ingest_error_truncates_long_message` method; FAIL; restore.

**Criteria:** AC3, AC6 partial (count delta on AC3b), AC7.

**Threat:** T1, T3 (split-receiver — second half is AC3b).

## TASK 3b — AC3b: fold 2 truncate tests + delete source

**Files:**
- READ: `tests/test_v01013_cli_error_truncation.py` (2 truncate tests, lines 88–107)
- READ: `tests/test_utils_text.py` (find tail)
- EDIT: `tests/test_utils_text.py` (append 2 bare functions)
- DELETE: `tests/test_v01013_cli_error_truncation.py`

**Change:**
1. Append section comment `# ── truncate (cycle 56 fold from test_v01013_cli_error_truncation) ─`.
2. Append `test_truncate_preserves_short_messages` and `test_truncate_cuts_long_messages` as bare functions verbatim (function-local `from kb.utils.text import truncate` preserved).
3. Delete source `tests/test_v01013_cli_error_truncation.py`.

**Test:** `python -m pytest tests/test_utils_text.py -x --tb=short` green; revert-verify on `test_truncate_cuts_long_messages`; FAIL; restore.

**Criteria:** AC3b, AC6 (cumulative count delta now -3 source files), AC7.

## TASK 4 — AC4: fold test_v01001_utils_fixes.py into test_utils.py

**Files:**
- READ: `tests/test_v01001_utils_fixes.py` (5 tests + helper `_write_page`)
- READ: `tests/test_utils.py` (find tail; check if `_write_concept_page` already exists per cycle-52)
- EDIT: `tests/test_utils.py` (append class `TestUtilsFixes` with renamed helper)
- DELETE: `tests/test_v01001_utils_fixes.py`

**Change:**
1. Append section comment `# ── Phase 4 utils fixes (cycle 56 fold) ─`.
2. Append class `TestUtilsFixes` containing:
   - `@staticmethod _write_concept_page(dirpath, name, body)` — renamed per C52-L4 helper-name uniqueness. **Pre-grep `_write_concept_page` in receiver to confirm uniqueness BEFORE commit.** If cycle-52 already added a `_write_concept_page` helper at section `# ── load_all_pages ─`, rename further to `_write_phase4_concept_page` to avoid collision.
   - 5 methods: test_load_all_pages_extracts_date_from_datetime, test_slugify_preserves_version_numbers, test_atomic_json_write_cleanup_no_ebadf, test_extract_wikilinks_strips_embedded_newlines, test_append_wiki_log_strips_tabs. Convert to `(self, ...)`.
3. Delete source.

**Test:** `python -m pytest tests/test_utils.py -x --tb=short` green; revert-verify on `test_slugify_preserves_version_numbers`; FAIL; restore.

**Criteria:** AC4, AC6, AC7. **CONDITION 4 (helper-name uniqueness verified).**

**Threat:** T2 (helper rename).

## TASK 5 — AC5: fold test_phase4_audit_concurrency.py into test_utils_io.py

**Files:**
- READ: `tests/test_phase4_audit_concurrency.py` (4 tests)
- READ: `tests/test_utils_io.py` (find tail)
- EDIT: `tests/test_utils_io.py` (append class `TestFileLockConcurrency`)
- DELETE: `tests/test_phase4_audit_concurrency.py`

**Change:**
1. Append section comment `# ── file_lock concurrency + verdicts threading.Lock removal (cycle 56 fold) ─`.
2. Append class `TestFileLockConcurrency` containing 4 methods verbatim (test_file_lock_basic_mutual_exclusion, test_file_lock_writes_pid_to_lock_file, test_feedback_lock_uses_file_lock, test_verdicts_add_verdict_does_not_use_threading_lock). Function-local imports preserved.
3. Delete source.

**Test:** `python -m pytest tests/test_utils_io.py -x --tb=short` green; revert-verify on `test_file_lock_writes_pid_to_lock_file`; FAIL; restore.

**Criteria:** AC5, AC6, AC7.

## TASK 6 — Doc-sync after all 5 folds land

**Files updated:**
- `CLAUDE.md` — Quick Reference: tests `3026` preserved; files `221 → 214`. Drop the cycle-55 file-count caveat note (since cycle 55 is now merged, the count is no longer "subject to Step 21 rebase").
- `CHANGELOG.md` `[Unreleased]` — add cycle-56 compact entry: Items / Tests / Scope / Detail.
- `CHANGELOG-history.md` — add cycle-56 detail block at top with all 5 fold targets, receiver, test count, source-file count, AC8 picks-marker rationale, dep-CVE re-confirmation, and trial-relevance note (5 picks vs 4 cadence per user direction).
- `BACKLOG.md` HIGH cycle-44-progress note — append cycle-56 progress: `Cycle 56 continued cadence with 5 small folds (one extra over c53/c54/c55 cadence per user direction): test_v01012_mcp_validation.py (2701 B / 7 tests) → test_mcp_core.py as TestMcpInputValidation; test_v0916_task09.py (2011 B / 3 tests) → test_v070.py preserving 3 classes; test_v01013_cli_error_truncation.py (3444 B / 7 tests) split → test_cli.py as TestCliErrorTruncation (5) + test_utils_text.py (2 bare functions); test_v01001_utils_fixes.py (2754 B / 5 tests) → test_utils.py as TestUtilsFixes with helper renamed _write_page → _write_concept_page per C52-L4 (re-verify uniqueness against cycle-52 fold first); test_phase4_audit_concurrency.py (3099 B / 4 tests) → test_utils_io.py as TestFileLockConcurrency. file count 221 → 214 (-5 sources, +0 receivers); test count preserved at 3026; each fold revert-verified per C40-L3, per-fold isolation pytest passed per C51-L1.`
- `docs/reference/testing.md` — same test/file count update if it cites these numbers.
- `docs/reference/implementation-status.md` — same.
- Re-confirm 4 dep-CVEs in CHANGELOG-history.md cycle-56 entry: diskcache (no upstream fix), ragas (no upstream fix), litellm (1.83.7 still blocked by click==8.1.8 transitive), pip 26.0.1 (advisory `first_patched_version` still null). Document the same Dependabot pip-audit drift on litellm GHSA-r75f-5x8p-qvmc + GHSA-v4p8-mg3p-g94g per cycle-22 L4 cross-cycle advisory cadence.

**CONDITION 3 (count cross-check):** grep `3026` and `214` across CLAUDE.md AND docs/reference/*.md AND CHANGELOG.md AND CHANGELOG-history.md AND BACKLOG.md. Zero mismatch. Re-run `pytest --collect-only \| Select-Object -Last 1` AFTER any R1/R2 fix commit per C26-L2 + cycle-15 L4.

---

## Plan Gate (Step 8) — primary-session resolution per cycle-21 L1

| Gap candidate | Resolution |
|---------------|------------|
| AC1 — class-conversion strategy: do all tests in source need monkeypatch param? | YES — test_kb_detect_drift_none_changed_sources uses `monkeypatch.setattr(_h, "detect_source_drift", ...)`. Other 6 do not. Class methods take `self, monkeypatch` only where source had `monkeypatch`; otherwise `(self)`. |
| AC2 — does test_v070.py already import `from kb.cli import cli`? | grep at TASK execution time. If yes, deduplicate to one module-top import; if no, keep function-local imports per source. |
| AC4 — does test_utils.py already define `_write_concept_page`? | **REQUIRED grep at TASK 4 execution time** — cycle-52 fold MIGHT have added it. CONDITION 4 enforces. |
| AC5 — does test_utils_io.py already have a `TestFileLockConcurrency` or `_feedback_lock` test? | grep at TASK 5 execution time; if so, rename new class to `TestFileLockConcurrencyAudit` to avoid collision. |
| AC6 — file count math: 219 - 5 = 214 ✓ | Confirmed. |
| AC9 — `gh api dependabot/alerts` — needs auth | Skip if `gh auth status` fails; rely on pip-audit baseline only. Document in Step-15 deferred-patch finding. |

**APPROVE** — proceed to Step 9.

---

## Step-by-step execution checklist

- [x] Step 1 — Requirements + ACs (in design.md)
- [x] Step 2 — Threat model + dep-CVE baseline (in design.md + .data/cycle-56/cve-baseline.json)
- [x] Step 3 — Brainstorm (in design.md — 2 approaches → Approach 2 picked)
- [x] Step 4 — Design eval R1 (Opus primary; R2 trivially-skipped)
- [x] Step 5 — Design decision gate (8 questions resolved inline)
- [N/A] Step 6 — Context7 (pure-stdlib fold work)
- [x] Step 7 — Implementation plan (this doc)
- [x] Step 8 — Plan gate (primary-session inline resolution)
- [ ] Commit + push picks marker on `cycle-56-batch` to origin (AC8 pre-Step-9)
- [ ] Step 9 — TASK 1..5 with revert-verify per task
- [N/A] Step 10 — /simplify (no src/ diff)
- [N/A] Step 11 — SAST (no code diff)
- [ ] Step 12 — CI hard gate (full pytest + ruff + pip-audit)
- [N/A] Step 13 — Coverage delta (test-fold exemption)
- [ ] Step 14 — Security verify + PR-CVE diff (Class B — empty expected)
- [ ] Step 15 — Existing-CVE re-confirm
- [N/A] Step 16 — IaC/container/SBOM (no deployable artifacts)
- [ ] Step 17 — Doc-sync (CLAUDE.md + CHANGELOG.md + CHANGELOG-history.md + BACKLOG.md + docs/reference/*.md)
- [ ] Step 18 — Branch finalise + PR
- [N/A] Step 19 — Signing (no signed-commit policy)
- [ ] Step 20 — PR review (R1: DeepSeek+Sonnet parallel; R2: Codex+Sonnet parallel)
- [ ] Step 21 — Merge + late-arrival CVE warn
- [N/A] Step 22+23 — Deploy + smoke (no deployable)
- [ ] Step 24 — Self-review scorecard + skill patches (MiMo trial outcomes for 2026-05-31 writeup)
