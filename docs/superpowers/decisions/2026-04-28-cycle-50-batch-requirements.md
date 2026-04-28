# Cycle 50 — Backlog hygiene + freeze-and-fold continuation + dep-CVE re-confirm

**Date:** 2026-04-28
**Branch:** `cycle-50-batch` (worktree at `D:\Projects\llm-wiki-flywheel-c50` per cycle-42 L4)
**Cycle pattern:** Continuation of cycles 38-49 (small fold-batches under the BACKLOG.md Phase 4.5 HIGH item 4 freeze-and-fold rule) + routine dep-CVE re-confirmation.

## Problem

The `tests/` directory still has ~190+ versioned `test_v0NNN_*` / `test_cycleNN_*` files that pre-date the canonical-module-file convention. The HIGH item in BACKLOG.md `Phase 4.5` line 89-91 documents the "freeze-and-fold" rule: once a version ships, fold its tests INTO the canonical module file (`test_v0917_dedup.py` → `test_query.py::class TestDedup`). Cycles 38-49 have made steady progress (cycle 47 folded 3, cycle 48 folded 2, cycle 49 folded 4 — file count 244 → 237). The 4 fold candidates in this cycle are the smallest remaining versioned files with clear collision-free canonical homes:

1. `test_cycle9_lint_checks.py` (1506 B, 1 test) — `test_check_source_coverage_parses_yaml_once_per_page` belongs next to existing `test_check_source_coverage` / `test_check_source_coverage_empty` in `test_lint.py`.
2. `test_cycle45_lint_runner_order_invariant.py` (1358 B, 1 test) — `test_lint_runner_enumeration_order_unchanged` belongs next to existing `test_run_all_checks` / `test_run_all_checks_empty` / `test_format_report` in `test_lint.py`.
3. `test_cycle8_llm_telemetry.py` (2300 B, 2 tests) — telemetry tests for `_make_api_call` belong next to other `call_llm` tests in `test_llm.py`. Brings 2 helpers (`_FakeMessages`, `_install_client`) — neither name collides with `test_llm.py`.
4. `test_cycle9_mcp_path_validation.py` (2226 B, 9 tests) — wiki_dir validation across `kb_compile_scan` / `kb_lint` / `kb_evolve` belongs in `test_mcp_core.py` as a `TestMcpWikiDirValidation` class (3 sub-namespaces). `test_mcp_core.py` already hosts `kb_compile_scan` tests + `TestKbCaptureWrapper` cross-module pattern → precedent exists.

CVE state on `main` is unchanged from cycle 49 (4 unpatched advisories, 4 Dependabot alerts) — needs routine re-confirmation per the "1-week refresh" pattern + timestamp updates in `BACKLOG.md` to reflect the new cycle.

## Non-goals

- **No fold of `test_cycle12_conftest.py`** — no clear canonical home (it tests the `tmp_kb_env` conftest fixture itself; closest match is a hypothetical `test_conftest.py` which doesn't exist). Defer.
- **No new CI dimension** (e.g., windows-latest matrix re-enable, NPM-audit migration). Per C36-L1 CI-cost discipline: one new gate per cycle, this cycle has fold + CVE re-confirm.
- **No GHA-Windows multiprocessing investigation** — needs self-hosted runner (per BACKLOG.md cycle-50+ tag, prerequisite missing).
- **No POSIX off-by-one investigation in `test_capture.py::TestWriteItemFiles`** — needs POSIX shell (per BACKLOG.md cycle-50+ tag, prerequisite missing).
- **No CVE patch attempts** — all 4 advisories have empty `fix_versions` (diskcache, pip, ragas) OR a fix-version (litellm 1.83.7) that ResolutionImpossibly conflicts with our `click==8.3.2` pin. Re-check next cycle.
- **No simplify pass on src/** — pure test-only diff, src/ is unchanged.
- **No new test additions** — fold cycle, test count must be preserved.

## Acceptance Criteria

| # | Criterion | Test |
|---|-----------|------|
| AC1 | `tests/test_cycle9_lint_checks.py` is deleted | `! test -f tests/test_cycle9_lint_checks.py` |
| AC2 | `tests/test_lint.py` contains `test_check_source_coverage_parses_yaml_once_per_page` | `grep -q "def test_check_source_coverage_parses_yaml_once_per_page" tests/test_lint.py` |
| AC3 | AC1 fold revert-verify: writing `assert False` into the moved test under `test_lint.py` causes `pytest -x` to FAIL (per C40-L3 — fold must move a behavioral test, not a vacuous one) | manual `assert False` insertion + `pytest tests/test_lint.py -k parses_yaml_once -x` shows 1 failure; restored. |
| AC4 | `tests/test_cycle45_lint_runner_order_invariant.py` is deleted | `! test -f tests/test_cycle45_lint_runner_order_invariant.py` |
| AC5 | `tests/test_lint.py` contains `test_lint_runner_enumeration_order_unchanged` AND module-level `EXPECTED_CHECK_ORDER` constant (or function-local equivalent) | `grep -q "def test_lint_runner_enumeration_order_unchanged" tests/test_lint.py && grep -q "EXPECTED_CHECK_ORDER" tests/test_lint.py` |
| AC6 | AC4 fold revert-verify per C40-L3 | manual `assert False` → `pytest -x` FAIL → restored |
| AC7 | `tests/test_cycle8_llm_telemetry.py` is deleted | `! test -f tests/test_cycle8_llm_telemetry.py` |
| AC8 | `tests/test_llm.py` contains both `test_make_api_call_success_logs_info_record_without_prompt_leak` and `test_make_api_call_missing_usage_logs_zero_tokens` AND helper code (`_FakeMessages` / `_install_client` / equivalent) is preserved | `grep -q "def test_make_api_call_success_logs_info_record_without_prompt_leak" tests/test_llm.py && grep -q "def test_make_api_call_missing_usage_logs_zero_tokens" tests/test_llm.py` |
| AC9 | AC7 fold revert-verify per C40-L3 | manual `assert False` → `pytest -x` FAIL → restored |
| AC10 | `tests/test_cycle9_mcp_path_validation.py` is deleted | `! test -f tests/test_cycle9_mcp_path_validation.py` |
| AC11 | `tests/test_mcp_core.py` contains a class `TestMcpWikiDirValidation` (or equivalent host shape, decided at Step 5) hosting all 9 wiki_dir validation tests | `grep -q "class TestMcpWikiDirValidation" tests/test_mcp_core.py && grep -c "def test_kb_.*_rejects_" tests/test_mcp_core.py` ≥ 9 |
| AC12 | AC10 fold revert-verify per C40-L3 — pick the highest-coverage of the 9 (e.g. `test_kb_compile_scan_rejects_nonexistent_wiki_dir`) | manual `assert False` → `pytest -x` FAIL → restored |
| AC13 | Total test count is preserved at 3025 (4 folds × {1, 1, 2, 9} = 13 tests moved, no add/remove) | `pytest --collect-only -q | tail -1` shows `3025 tests collected` |
| AC14 | Total root test file count is 237 − 4 = 233 | `find tests -maxdepth 1 -name '*.py' -type f \| wc -l` returns 233 |
| AC15 | Full pytest suite passes locally on Windows (3014 passed + 11 skipped) | `python -m pytest 2>&1 \| tail -2` shows `3014 passed, 11 skipped` |
| AC16 | `ruff check src/ tests/` passes; `ruff format --check src/ tests/` passes | both commands exit 0 |
| AC17 | `BACKLOG.md` HIGH item 4 (lines 89-91) progress note is updated from "Cycle 49 continued cadence with 4 small folds" to "Cycle 50 continued cadence with 4 small folds" + new file count math `237 → 233 (-4)` + new fold list | manual diff inspection |
| AC18 | `BACKLOG.md` CVE entries (diskcache / ragas / litellm / pip) timestamps updated from `2026-04-28 (cycle-49)` to `2026-04-28 (cycle-50)` (same date — back-to-back same-day cycles) AND re-confirmed against `.data/cycle-50/cve-baseline.json` (4 vulns identical) AND re-confirmed against `.data/cycle-50/alerts-baseline.json` (4 alerts identical) | manual diff inspection |
| AC19 | `BACKLOG.md` cycle-50+ deferred tags (windows matrix re-enable, GHA-Windows multiprocessing, POSIX off-by-one) bumped to `cycle-51+` | `! grep -E "cycle-50\+" BACKLOG.md` |
| AC20 | `CHANGELOG.md` `[Unreleased]` Quick Reference adds compact cycle-50 entry (newest first) | manual diff inspection |
| AC21 | `CHANGELOG-history.md` adds full per-cycle bullet detail (newest first) | manual diff inspection |
| AC22 | `CLAUDE.md` Quick Reference state line updated: `237 files` → `233 files`; `cycle 36..49 carry-over` → `cycle 36..50 carry-over` | manual diff inspection |
| AC23 | `docs/reference/implementation-status.md` and `docs/reference/testing.md` test-count narrative sites match (per C26-L2 extended) | grep + manual diff |
| AC24 | `README.md` test-count narrative sites updated if present (per C39-L3 extending C26-L2) | grep + manual diff |
| AC25 | All `Step 11.5` Dependabot drift entries in `BACKLOG.md` (cycle-49+ tagged for `GHSA-r75f-5x8p-qvmc` and `GHSA-v4p8-mg3p-g94g`) re-confirmed at cycle 50 with current timestamps | manual diff inspection |

## Blast radius

- `tests/` only — 4 deletions + 3 receivers (`test_lint.py`, `test_llm.py`, `test_mcp_core.py`) edited. No `src/` changes.
- `BACKLOG.md` — HIGH item 4 progress note + CVE timestamps + cycle-50+ tag bumps.
- `CHANGELOG.md`, `CHANGELOG-history.md` — newest-first entries.
- `CLAUDE.md` Quick Reference + `docs/reference/{implementation-status,testing}.md` + `README.md` — count fields only.

No production code (`src/kb/`) is touched. No imports rebound. No fixture / runtime constant / config drift.

## Threat model classification

Per `dev_ds` skill Step 2 skip-when: "pure internal refactor, no I/O or trust boundary changes" → threat model is SKIPPED for fold tasks proper. Dep-CVE baseline IS captured (already done at `.data/cycle-50/`), Step 11 PR-CVE diff still runs, Step 11.5 still considers patches (no-op this cycle).

## Cycle-pattern history

| Cycle | Folds | File count | Test count |
|---|---|---|---|
| 47 | 3 (`cycle16_config_constants`, `cycle11_task6_mcp_ingest_type`, `cycle14_save_frontmatter`) | 244 → 241 (−3 fold + new test_config.py) | 3025 |
| 48 | 2 (`cycle9_evolve`, `cycle9_compiler`) + 2 test-quality upgrades | 241 (alignment, was doc-drift 243) | 3025 |
| 49 | 4 (`cycle12_mcp_console_script`, `cycle9_capture_runtime_guard`, `cycle9_package_exports`, `cycle9_mcp_app`) | 241 → 237 | 3025 |
| **50** | **4 (`cycle9_lint_checks`, `cycle45_lint_runner_order_invariant`, `cycle8_llm_telemetry`, `cycle9_mcp_path_validation`)** | **237 → 233** | **3025 (preserved)** |

Cumulative versioned-file remaining count after cycle 50: ~186 (was ~190 at cycle 49 end).
