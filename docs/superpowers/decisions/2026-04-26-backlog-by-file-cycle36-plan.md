# Cycle 36 — Implementation Plan (Primary Session per cycle-14 L1)

**Date:** 2026-04-26
**Branch:** `feat/backlog-by-file-cycle36`
**Inputs:** Step-1 requirements (with AC3 amendment), Step-2 threat model, Step-3 brainstorm, Step-4 R1+R2 evals, Step-5 design decision (binding).
**Sequencing:** 3 commits per Q16/Q21 — probe → fix → strict-gate.
**Heuristic:** Per cycle-13 L2 sizing (most tasks <30 LOC + <100 LOC tests + stdlib APIs), all tasks execute in primary session. Codex dispatch reserved for Step 8 plan-gate verification.

---

## TASK 1 — Skip cycle-23 multiprocessing test on CI (AC1 + AC2)

**Files:** `tests/test_cycle23_file_lock_multiprocessing.py`
**Change:** Add `import os` + `@pytest.mark.skipif(os.environ.get("CI") == "true", reason="Windows multiprocessing spawn hangs on GHA — tracked C36-investigation.md, cycle-37 candidate")` to the single test function.
**Test:** Local pytest passes the test; CI skips it (verified later in commit-1 CI run).
**Criteria:** AC1 (identification — already done in Step 2 baseline), AC2 (skipif marker).
**Threat:** T1 (skipif gap acceptable — local coverage preserved).
**Commit:** Commit 1 (probe).

## TASK 2 — Add pytest-timeout dep + global config (AC3, amended Q2/Q10)

**Files:** `pyproject.toml`, `requirements.txt`
**Change:**
- Add `pytest-timeout>=2.3` to `[project.optional-dependencies] dev` list
- Add `[tool.pytest.ini_options] timeout = 120` (under existing `[tool.pytest.ini_options]` block, with comment `# Cycle 36 AC3 — 120 s catches genuine hangs without false-positives`)
- Add `pytest-timeout>=2.3` to `requirements.txt` (alphabetical position near `pytest`)
**Test:** `pip list | grep pytest-timeout` shows installed; `pytest --collect-only -q` doesn't error; manual probe with a 5-second sleep test confirms 120s gate fires only on true hang.
**Criteria:** AC3.
**Threat:** T2 (default chosen with 70-80x headroom over slowest current test).
**Commit:** Commit 1 (probe).

## TASK 3 — Wiki-content monkeypatch mirror-rebind (AC5 amended Q3/Q18)

**Files:** `tests/test_cycle10_quality.py`
**Change:** For both affected tests:
- Add `monkeypatch.setattr("kb.config.WIKI_DIR", tmp_wiki)` to the existing monkeypatch chain
- Trace the `refine_page` / `kb_affected_pages` call chain via Read of `src/kb/review/refiner.py:32-100`, `src/kb/mcp/quality.py`, `src/kb/utils/pages.py:11`. Already verified at Step 5: `kb.review.refiner.WIKI_DIR` is the read site (test ALREADY patches); `kb.config.WIKI_DIR` is the source of the snapshot. Add `kb.utils.pages.WIKI_DIR` only if `_find_affected_pages` reaches `kb.utils.pages` for path resolution (verify by reading `mcp/quality.py::kb_affected_pages` body).
- Add a 1-line comment per test: `# Cycle 36 AC5 — mirror kb.config.WIKI_DIR snapshot per cycle-19 L1`
**Test:** Tests pass under `pytest tests/test_cycle10_quality.py -v` locally (already pass per probe); will pass on ubuntu-latest probe (Commit 1 CI).
**Criteria:** AC5.
**Threat:** T1 mitigation (production call chain reaches the patched binding).
**Commit:** Commit 1 (probe).

## TASK 4 — `requires_real_api_key()` helper + tests/_helpers/ (AC6 amended Q4/Q12/Q19)

**Files (NEW):** `tests/_helpers/__init__.py`, `tests/_helpers/api_key.py`
**Files modified:** `tests/test_cycle21_cli_backend.py`, `tests/test_v5_lint_augment_orchestrator.py`, `tests/test_env_example.py`, `tests/test_backlog_by_file_cycle1.py` (per Step-9 trace results — only annotate tests confirmed to reach a real Anthropic SDK call)
**Change:**
1. `tests/_helpers/__init__.py` — empty file
2. `tests/_helpers/api_key.py`:
```python
"""Cycle 36 AC6 — predicate for tests that risk a real Anthropic API call."""
import os

_DUMMY_KEY_PREFIX = "sk-ant-dummy-key-"


def requires_real_api_key() -> bool:
    """Return True iff ANTHROPIC_API_KEY appears to be a real (non-dummy, non-empty) key.

    Tests that ENTER code paths ultimately calling anthropic.Anthropic(...).messages.create(...)
    should mark themselves with @pytest.mark.skipif(not requires_real_api_key(), reason=...).

    The CI runner sets ANTHROPIC_API_KEY=sk-ant-dummy-key-for-ci-tests-only (see ci.yml:38),
    so the dummy-prefix check identifies CI environments without coupling to a specific
    CI provider env var (CI=true would also catch local act runs).
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return bool(key) and not key.startswith(_DUMMY_KEY_PREFIX)
```
3. Per-file trace recorded in `docs/superpowers/decisions/2026-04-26-backlog-by-file-cycle36-investigation.md` per C4. Annotate ONLY tests confirmed to reach a real API call.
**Test:** Behaviour tests in `tests/test_cycle36_ci_hardening.py` per C4/C9 — see TASK 7.
**Criteria:** AC6.
**Threat:** T7 (helper false-negative caught by behaviour tests).
**Commit:** Commit 1 (probe).

## TASK 5 — Wall-clock timing tolerance (AC7 amended Q11)

**Files:** `tests/test_capture.py:165`
**Change:** Modify `assert retry_after <= 3600` to `assert retry_after <= 3601` with comment `# Cycle 36 AC7 — 1s tolerance for CI clock variance (cycle-34 timing fragility class)`. LEAVE `tests/test_capture.py:175` (`assert retry_after == 3600` in the static-clock variant) UNCHANGED — frozen clock = exact equality sound per Q11/R1-NEW-4.
**Test:** Local + CI probe confirms test passes with 1s tolerance.
**Criteria:** AC7.
**Threat:** T2 (timing precision narrowed).
**Commit:** Commit 1 (probe).

## TASK 6 — Probe ubuntu-latest CI run (AC11 / AC13 / Commit 1 sequencing)

**Files:** `.github/workflows/ci.yml`
**Change for Commit 1 (probe):**
- Change `runs-on: windows-latest` → `runs-on: ubuntu-latest`
- KEEP `continue-on-error: true` on pytest step (probe doesn't strict-gate)
- KEEP all other workflow steps unchanged
**Test:** Push commit 1; observe ubuntu CI run; capture ALL failing test IDs into `docs/superpowers/decisions/2026-04-26-backlog-by-file-cycle36-investigation.md`. Expected failures from R2 enumeration: `test_cycle11_utils_pages.py::test_page_id_normalizes_backslashes_to_posix_id`, `test_v0915_task09.py::TestValidatePageIdAbsoluteCheck::test_absolute_path_rejected`. May also surface: `test_backlog_by_file_cycle1.py:622`, `test_backlog_by_file_cycle2.py:149`, `test_capture.py:682` symlink-related tests.
**Criteria:** AC13 (probe-driven enumeration).
**Threat:** T6 (cross-OS surface revealed).
**Commit:** Commit 1 (probe).

## TASK 7 — `tests/test_cycle36_ci_hardening.py` regression tests (C4/C9/C10/C11)

**Files (NEW):** `tests/test_cycle36_ci_hardening.py`
**Change:** Test classes covering:
- **C9**: `requires_real_api_key()` 4 cases (unset / exact-dummy / dummy-prefix / real-prefix split-string-constructed per `feedback_no_secrets_in_code.md`)
- **C10**: parsing test — read `SECURITY.md` advisory IDs + `.github/workflows/ci.yml` `--ignore-vuln=` flags; assert set equality
- **C5/C11**: skipif marker collect-only sanity — `pytest --collect-only` includes the cycle-23 multiprocessing test name (regression: marker doesn't prevent collection, only execution)
**Test:** All new tests in this file pass locally + on ubuntu-latest probe.
**Criteria:** AC6 (helper coverage), AC20 (SECURITY.md ↔ workflow parity).
**Threat:** T1 (markers don't lose coverage), T5 (advisory drift detection), T7 (helper correctness).
**Commit:** Commit 1 (probe).

## TASK 8 — Apply AC11 markers from probe results (Commit 2 fix)

**Files:** Per probe enumeration in TASK 6 — at minimum:
- `tests/test_cycle11_utils_pages.py` — add `import sys` + `@pytest.mark.skipif(sys.platform != "win32", reason="Windows backslash-to-POSIX-slash normalisation; POSIX treats \\ as literal")`
- `tests/test_v0915_task09.py` — `@pytest.mark.skipif(sys.platform != "win32", reason="Windows-style absolute path detection (drive letter); POSIX uses different absolute-path semantics")`
**Change:** Apply skipif markers to confirmed-failing tests from probe. Document each addition in the cycle-36 investigation doc with a one-liner: "`<test_id>` — `skipif(<predicate>)` because `<reason>`."
**Test:** Re-run pytest locally + on ubuntu probe (re-pushed commit 2 CI run); affected tests now skip on POSIX without losing Windows coverage.
**Criteria:** AC11 (data-driven enumeration).
**Threat:** T6 (POSIX surface coverage).
**Commit:** Commit 2 (fix).

## TASK 9 — pip-audit reconciliation + SECURITY.md update (AC9, AC18, AC20 — Commit 2)

**Files:** `.github/workflows/ci.yml`, `SECURITY.md`, `BACKLOG.md`
**Change:**
1. Run `pip install -e '.[dev,formats,augment,hybrid,eval]'` in a fresh venv equivalent to CI; run `pip-audit --format json` (no `--ignore-vuln` flags); inspect emitted advisory IDs.
2. Compare against current workflow `--ignore-vuln` set: CVE-2025-69872 (diskcache), GHSA-xqmj-j6mv-4862 (litellm), CVE-2026-3219 (pip), CVE-2026-6587 (ragas).
3. CI's actual emission per cycle-35 hotfix CI: "No known vulnerabilities found, 4 ignored". So pip-audit emits exactly these 4 IDs. The 4 Dependabot alerts listed in `.data/cycle-36/alerts-baseline.json` (3 litellm + 1 ragas) include 2 GHSAs (`GHSA-r75f-5x8p-qvmc`, `GHSA-v4p8-mg3p-g94g`) NOT in pip-audit's report — these get cycle-37 BACKLOG entries.
4. SECURITY.md: add row for `GHSA-v4p8-mg3p-g94g` (litellm authenticated MCP-stdio command execution, fix=1.83.7 BLOCKED by click<8.2 transitive). Existing litellm row already mentions `GHSA-r75f-5x8p-qvmc`; add `GHSA-v4p8-mg3p-g94g` to the same row.
5. Workflow `--ignore-vuln`: NO change (current 4-ID list matches pip-audit emission).
6. BACKLOG: add Phase 4.6 entries per Q17 BACKLOG-shape for any drift between Dependabot and pip-audit.
**Test:** Local `pip-audit --ignore-vuln=...` exits 0 with "No known vulnerabilities found, N ignored". `tests/test_cycle36_ci_hardening.py` parsing test passes (SECURITY.md ↔ workflow set-equality).
**Criteria:** AC9, AC18, AC20.
**Threat:** T5 (SECURITY.md drift mitigation).
**Commit:** Commit 2 (fix).

## TASK 10 — Strict CI gate flip (AC8, AC10, AC12 — Commit 3)

**Files:** `.github/workflows/ci.yml`
**Change for Commit 3 (strict-gate):**
- DROP `continue-on-error: true` from the `Pytest full suite` step
- Update step name from `Pytest full suite (soft-fail per cycle 34 R1 fallback)` to `Pytest full suite (strict — cycle 36 closure)`
- Update the comment block above the step to describe cycle-36 fixes (skipif markers landed; pytest-timeout in place; mirror-rebind on quality tests; helper for API-key tests)
- Add `strategy.matrix.os: [ubuntu-latest, windows-latest]` and `strategy.fail-fast: false` to the test job
- Change `runs-on: ubuntu-latest` (set by commit 1) → `runs-on: ${{ matrix.os }}`
- KEEP `continue-on-error: true` on `pip check` step (per AC10 / non-goal #7)
- KEEP `pip-audit` `--ignore-vuln` flags unchanged (verified TASK 9)
**Test:** Push commit 3; CI runs both ubuntu-latest AND windows-latest; both pass strict pytest gate; the matrix produces 2 successful checks.
**Criteria:** AC8, AC10, AC12.
**Threat:** T3 (matrix expansion preserves read-all permissions), T9 (chicken-and-egg neutralised by 3-commit ordering).
**Commit:** Commit 3 (strict-gate).

## TASK 11 — Documentation updates (AC21-AC25)

**Files:** `CHANGELOG.md`, `CHANGELOG-history.md`, `BACKLOG.md`, `CLAUDE.md`, `docs/reference/testing.md`
**Change:**
- `CHANGELOG.md` `[Unreleased]` Quick Reference: cycle-36 compact entry (Items / Tests / Scope / Detail) with `+TBD commits` per cycle-30 L1
- `CHANGELOG-history.md`: full per-cycle bullet detail
- `BACKLOG.md`:
  - DELETE the "tests/ strict full-pytest CI gate (cycle-36 follow-up)" entry (AC23)
  - DELETE the "tests/ cross-OS portability (cycle-36 follow-up)" entry (AC23)
  - REPLACE "requirements.txt split into per-extra files (cycle-36 follow-up)" with "Phase 4.5 — Requirements split (deferred from cycle 36)" per Q6 BACKLOG-shape
  - DELETE the cycle-32 deferred-CVE-recheck entry (AC18 confirms state)
  - ADD cycle-37 entries: GHSA-r75f-5x8p-qvmc + GHSA-v4p8-mg3p-g94g pip-audit drift entries (per Q17)
  - ADD cycle-37 entry: GHA-Windows multiprocessing spawn investigation (per Q1 / AC2)
- `CLAUDE.md` Quick Reference: re-collect test count per Q22 / C14 (`pytest --collect-only -q | tail -3` after all marker fixes land)
- `docs/reference/testing.md`:
  - Refresh test count from current stale `2941 / 254` to actual collected per pytest output
  - Document new conventions: cross-OS skipif marker pattern (anti-Windows + anti-POSIX), `requires_real_api_key()` helper location and usage, pytest-timeout 120s default + override mechanism, CI vs local skip strategy, dummy-key prefix `sk-ant-dummy-key-for-ci-tests-only` (per T7 verification step #4)
**Test:** Manual review; `git diff` shows the doc updates match the implementation.
**Criteria:** AC21-AC25.
**Threat:** T1 / T6 / T7 documentation completeness.
**Commit:** Commit 3 (strict-gate) — single doc-update commit per cycle-26 L2 routing.

## TASK 12 — Cycle-36 investigation document (NEW)

**Files (NEW):** `docs/superpowers/decisions/2026-04-26-backlog-by-file-cycle36-investigation.md`
**Change:** Single living document accumulating evidence per CONDITIONS C3, C4, C5, C8, C11, C16:
- **C3 / AC5**: per-test call-chain trace for `kb_refine_page` and `kb_affected_pages`
- **C4 / AC6**: per-file SDK call-chain trace for the 4 enumerated test files (annotated / out-of-scope decision per file)
- **C5 / AC11**: two-list enumeration (anti-Windows-skipif + anti-POSIX-skipif) data-driven from probe
- **C8 / AC9 / AC20**: pip-audit live-env JSON snippet showing actual advisory IDs
- **C11**: collect-only diff per commit (`pytest --collect-only -q | tail -3` snippets)
- **C16 / Q14**: pytest-timeout × mp.Event acknowledgement (1.03s local; CI-skipped per AC2)
**Test:** Doc exists; Step-11 verifier greps for the conditions and finds matches.
**Criteria:** Spans AC1-AC11 (cross-cutting evidence trail per C7 PR review trail).
**Threat:** Audit-trail completeness for R3 review (Q15).
**Commit:** Updated across all 3 commits as evidence accumulates.

---

## Verification of cited symbols (cycle-15 L1)

Before Step 8 plan-gate dispatch, confirmed via prior Read / Grep:

| Symbol | File:line | Status |
|---|---|---|
| `test_cross_process_file_lock_timeout_then_recovery` | tests/test_cycle23_file_lock_multiprocessing.py:56 | EXISTS |
| `[tool.pytest.ini_options]` | pyproject.toml:63 | EXISTS — `addopts` defined; `timeout` field NEW |
| `[project.optional-dependencies] dev` | pyproject.toml:47 | EXISTS — `pytest-timeout` to be added |
| `tests/_helpers/` | none | NEW directory |
| `tests/_helpers/api_key.py` | none | NEW file |
| `requires_real_api_key()` | — | NEW function |
| `tests/test_cycle36_ci_hardening.py` | none | NEW file |
| `test_kb_refine_page_surfaces_backlinks_error_on_failure` | tests/test_cycle10_quality.py:7 | EXISTS — needs `kb.config.WIKI_DIR` mirror |
| `test_kb_affected_pages_surfaces_shared_sources_error_on_failure` | tests/test_cycle10_quality.py:28 | EXISTS — same |
| `test_over_cap_rejected_with_retry_after` | tests/test_capture.py:158-165 | EXISTS — wall-clock test |
| `test_over_cap_retry_after_static_clock_is_one_hour` | tests/test_capture.py:167-175 | EXISTS — frozen clock; LEAVE UNCHANGED |
| `test_page_id_normalizes_backslashes_to_posix_id` | tests/test_cycle11_utils_pages.py:32 | EXISTS — needs Windows-only skipif |
| `TestValidatePageIdAbsoluteCheck::test_absolute_path_rejected` | tests/test_v0915_task09.py:396 | EXISTS — needs Windows-only skipif |
| `Pytest full suite` step name | .github/workflows/ci.yml:71 | EXISTS — name + step content updates per TASK 10 |
| `runs-on: windows-latest` | .github/workflows/ci.yml:36 | EXISTS — toggles in 3 commits |
| `--ignore-vuln=` set | .github/workflows/ci.yml:111-114 | EXISTS — 4 IDs unchanged |
| `langchain-openai>=1.1.14` | pyproject.toml:45 | EXISTS — cycle-35 floor pin preserved |
| `GHSA-v4p8-mg3p-g94g` | none in repo | MISSING — added to SECURITY.md per TASK 9 |
| `kb.review.refiner.WIKI_DIR` import | src/kb/review/refiner.py:36 | EXISTS — module-top snapshot |
| `kb.config.WIKI_DIR` source | src/kb/config.py | EXISTS — origin of all snapshots |
| `kb.utils.pages.WIKI_DIR` import | src/kb/utils/pages.py:11 | EXISTS — module-top snapshot |
| `_index_cache_lock` and similar — N/A this cycle | — | OUT OF SCOPE — no `src/kb/` changes |

Zero phantom-symbol REJECTs. All NEW files explicitly named.

---

## File grouping (per `feedback_batch_by_file`)

Multi-file tasks marked as CLUSTER with rationale:

- **TASK 4 (CLUSTER)**: `tests/_helpers/__init__.py` + `tests/_helpers/api_key.py` + 4 test-file annotations. Rationale: helper + caller updates ship together for atomicity (cycle-7 L1).
- **TASK 9 (CLUSTER)**: `.github/workflows/ci.yml` + `SECURITY.md` + `BACKLOG.md`. Rationale: workflow `--ignore-vuln` set, SECURITY.md table, and BACKLOG drift entries must stay 1:1 (cycle-32 T5).
- **TASK 10 (CLUSTER)**: `.github/workflows/ci.yml` strict-gate flip + matrix introduction (single file; logical cluster of changes that must land atomically).
- **TASK 11 (CLUSTER)**: `CHANGELOG.md` + `CHANGELOG-history.md` + `BACKLOG.md` + `CLAUDE.md` + `docs/reference/testing.md`. Rationale: doc-update routing (cycle-26 L2 — single doc-update commit captures all cross-references).

Other tasks are single-file or single-test-file; no clustering.

---

## Sequencing summary (per Q16/Q21)

**Commit 1 (probe):** TASK 1 + TASK 2 + TASK 3 + TASK 4 + TASK 5 + TASK 6 + TASK 7 — markers + pytest-timeout + mirror-rebind + helper + tests + ubuntu-latest probe runs-on flip. NO matrix, NO strict-gate, `continue-on-error: true` STILL ON. CI runs full suite on ubuntu-latest, surfacing failures.

**Commit 2 (fix):** TASK 8 + TASK 9 — apply AC11 markers from probe results; pip-audit reconciliation. Re-push: ubuntu-latest CI re-runs with markers applied. CI green expected.

**Commit 3 (strict-gate):** TASK 10 + TASK 11 + TASK 12 final updates — strict-gate flip + matrix + doc updates. Both ubuntu-latest AND windows-latest CI runs strict-gate.

**Self-check at each commit:**
- Local `pytest -q` passes (cycle-22 L3 full-suite gate)
- `ruff check src/ tests/` passes
- `ruff format --check src/ tests/` passes
- `pip check` MAY have known-conflict noise (cycle-22 L1 — accepted)
- After commit 1: `gh run watch` per cycle-35 L8 to completion
- After commit 2: same; verify probe-revealed failures now skip cleanly
- After commit 3: same; verify strict-gate green on BOTH ubuntu and windows

---

## Edge-case alignment with Red Flags table

- **C-edge-1 (cycle-13 L2 sizing)**: All tasks are <30 LOC code or <100 LOC tests + stdlib APIs. Primary-session execution chosen.
- **C-edge-2 (cycle-22 L3 full-suite Step-10)**: Step 10 runs FULL local suite, not just changed-tests.
- **C-edge-3 (cycle-26 L2 test-count routing)**: TASK 11 re-collects via `pytest --collect-only -q | tail -3` AFTER all markers land; updates CLAUDE.md AND `docs/reference/testing.md`.
- **C-edge-4 (cycle-35 L7 ruff format CRLF)**: If `ruff format --check` flags non-cycle CRLF/LF carryover, fix as separate `chore(ruff, cycle 36)` commit per cycle-35 L7.
- **C-edge-5 (cycle-22 L4 cross-cycle CVE)**: Step 11 will re-run pip-audit on branch HEAD; advisories that landed during cycle 36 must be addressed (Class B blocks).
- **C-edge-6 (cycle-30 L1 commit count)**: TASK 11 uses `+TBD` for commit count in CHANGELOG; backfill post-merge on `main`.
- **C-edge-7 (cycle-22 L5 design conditions)**: All 16 CONDITIONS from Step 5 are mapped to specific tasks above.
- **C-edge-8 (cycle-13 L3 / Step 9.5)**: This cycle's `src/` diff is ZERO LoC (test+CI infrastructure only). Step 9.5 `/simplify` is SKIPPED per skip-when row "no `src/` changes".
- **C-edge-9 (Q15 / R3 trigger)**: 22 design-gate questions resolved → R3 review fires per cycle-19 L4 criterion (d).

---

End of plan document.
