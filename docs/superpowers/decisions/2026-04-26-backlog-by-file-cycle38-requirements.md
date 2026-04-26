# Cycle 38 — Requirements + Acceptance Criteria

**Date:** 2026-04-26
**Branch:** `feat/backlog-by-file-cycle38`
**Scope:** Re-enable POSIX-skipped tests from cycle-36 ubuntu probe (Categories A + B); refresh Dependabot drift entries.
**Out of scope:** windows-latest CI matrix re-enable (cycle-36 L1: one CI dimension per cycle); GHA-Windows multiprocessing spawn investigation (needs self-hosted Windows runner); config.py god-module split; IndexWriter consolidation refactor.

---

## 1. Problem

Cycle 36's ubuntu-probe surfaced 23 cross-OS test failures categorised into 6 buckets. Cycle 36 commit-2 applied skipif markers data-driven from probe results; commit-3 pivoted to ubuntu-only strict gate (windows matrix deferred). Two of the six categories were marked as cycle-37+ candidates for the SDK injection refactor / POSIX investigation that the marker pass deferred:

- **Category A (10 tests)** — `mock_scan_llm` POSIX reload-leak. Mock fixture patches `kb.capture.call_llm_json`, but POSIX full-suite ordering bypasses the mock and the real Anthropic SDK call goes through, failing on the dummy CI key with 401 auth error. Affected: `tests/test_capture.py::TestCaptureItems::*` (5), `TestPipelineFrontmatterStrip::test_frontmatter_stripped_for_capture_source` (1), `TestRoundTripIntegration::test_capture_then_ingest_renders_wiki_summary` (1), `tests/test_mcp_core.py::TestKbCaptureWrapper::*` (3). Currently gated behind `_REQUIRES_REAL_API_KEY` skipif (cycle-36 AC6).

- **Category B (4 tests)** — POSIX-incompatible Windows-helper class. `_exclusive_atomic_write` monkeypatch on `kb.capture.atomic_text_write` doesn't reach the production POSIX path (per cycle-36 commit-2 narrative); `_write_item_files` slug-collision counter is off-by-one on POSIX (`decision-foo-2` becomes `decision-foo-3`). Affected: `tests/test_capture.py::TestExclusiveAtomicWrite::test_cleans_up_reservation_on_inner_write_failure`, `test_cleans_up_on_keyboard_interrupt`, `TestWriteItemFiles::test_creates_dir_if_missing`, `test_pre_existing_file_collision`. Currently gated behind `_WINDOWS_ONLY` skipif (cycle-36 AC11).

Cycle 38 closes both classes so ubuntu-latest CI exercises the full intended capture-flow surface area without the `_REQUIRES_REAL_API_KEY` / `_WINDOWS_ONLY` escape hatches. The two classes share a root pattern (`monkeypatch.setattr("kb.capture.X", …)` doesn't survive on POSIX in some condition) so they are batched per the user's `feedback_batch_by_file` preference — both touch `tests/test_capture.py` and `tests/conftest.py`.

Additionally, cycle 36 left 2 Dependabot drift entries open (litellm GHSA-r75f and GHSA-v4p8) where the live CI install env's `pip-audit` doesn't surface the IDs that Dependabot reports. This cycle re-confirms the drift status — non-gating, monitoring only. If pip-audit still does not emit the IDs, refresh the BACKLOG re-check date; if pip-audit catches up, add the IDs to the workflow's `--ignore-vuln` list with documented narrow-role rationale.

## 2. Non-goals

- Do NOT add windows-latest to the CI matrix in this cycle (cycle-36 L1).
- Do NOT investigate the GHA-Windows multiprocessing spawn hang (needs self-hosted Windows runner; investigation-heavy).
- Do NOT refactor `kb.capture` to use a single SDK injection point — if widening the monkeypatch defeats the reload-leak, narrower fix wins (lower blast radius).
- Do NOT touch the litellm pin (no upstream fix path because click<8.2 transitive blocks 1.83.7).
- Do NOT split `config.py` god-module or refactor `IndexWriter` here — separate cycles.

## 3. Acceptance criteria

Each AC is testable as pass/fail on ubuntu-latest CI strict-gate.

### Area A — mock_scan_llm POSIX reload-leak (Category A, 10 tests)

**AC1 — widen mock_scan_llm to defeat reload-leak.** The `mock_scan_llm` fixture in `tests/conftest.py` patches BOTH `kb.capture.call_llm_json` AND `kb.utils.llm.call_llm_json` (canonical source) so that even if a sibling test's `importlib.reload(kb.config)` cascade re-binds module-top imports inside `kb.capture`, the mock still captures the call. Test: install `mock_scan_llm`, simulate a reload-cascade scenario via a regression test (AC5), verify the mock fires.

**AC2 — widen inline `kb.capture.call_llm_json` patches in test bodies.** Two test sites in `tests/test_capture.py` apply `monkeypatch.setattr("kb.capture.call_llm_json", ...)` directly (lines 419, 1126). Each gets a paired `monkeypatch.setattr("kb.utils.llm.call_llm_json", ...)` to defeat the same reload-leak class. Test: existing tests still pass under POSIX full-suite ordering.

**AC3 — remove `_REQUIRES_REAL_API_KEY` from 7 test_capture.py tests.** Drop the `@_REQUIRES_REAL_API_KEY` decorator from: `TestCaptureItems::test_happy_path_writes_files`, `test_rate_limit_class_a_reject`, `test_zero_items_returned_class_c_success`, `test_body_verbatim_drops_count_in_filtered`, `test_partial_write_class_d`; `TestPipelineFrontmatterStrip::test_frontmatter_stripped_for_capture_source`; `TestRoundTripIntegration::test_capture_then_ingest_renders_wiki_summary`. Test: ubuntu-latest CI runs all 7 without 401 auth-error failures.

**AC4 — remove `_REQUIRES_REAL_API_KEY` from 3 test_mcp_core.py tests.** Drop the decorator from `TestKbCaptureWrapper::test_happy_path_format`, `test_zero_items_format`, `test_partial_write_format`. Test: ubuntu-latest CI runs all 3 without 401 auth-error failures.

**AC5 — regression test pinning the reload-leak fix.** Add `tests/test_cycle38_mock_scan_llm_reload_safe.py` with at least two cases: (a) baseline — install `mock_scan_llm`, call `kb.capture.capture_items`, assert the mock fired; (b) post-reload — `importlib.reload(kb.utils.llm)` BEFORE installing `mock_scan_llm`, then call, assert the mock STILL fires. Pre-cycle-38 fixture (single-site patch only) MUST fail case (b); post-cycle-38 fixture (dual-site patch) MUST pass both. Test: revert AC1's widening locally and verify case (b) fails — proves the test is not vacuous (per `feedback_test_behavior_over_signature`).

### Area B — POSIX-incompatible Windows-helper class (Category B, 4 tests)

**AC6 — widen `kb.capture.atomic_text_write` patches in `test_cleans_up_*` tests.** Both `test_cleans_up_reservation_on_inner_write_failure` and `test_cleans_up_on_keyboard_interrupt` apply `monkeypatch.setattr("kb.capture.atomic_text_write", boom/interrupted)`. Each gets a paired `monkeypatch.setattr("kb.utils.io.atomic_text_write", boom/interrupted)`. Drop the `@_WINDOWS_ONLY` decorator from both tests. Test: ubuntu-latest CI exercises both tests successfully — `pytest.raises(OSError, match="disk full")` AND `pytest.raises(KeyboardInterrupt)` BOTH fire on POSIX, AND `path.exists()` returns False after cleanup.

**AC7 — investigate + fix `test_pre_existing_file_collision` POSIX off-by-one.** The test asserts `written[0].slug == "decision-foo-2"`, but cycle-36 ubuntu probe surfaced `decision-foo-3`. Root cause to be confirmed during implementation by adding diagnostic prints to `_scan_existing_slugs` / `_build_slug` / `_reserve_hidden_temp` and shipping a probe commit. Once root cause is identified, fix the production code OR loosen the test assertion to match documented behaviour. Drop the `@_WINDOWS_ONLY` decorator. Test: ubuntu-latest CI passes the test with the correct expected slug.

**AC8 — investigate + fix `test_creates_dir_if_missing` POSIX behaviour.** Test does `shutil.rmtree(tmp_captures_dir)` then expects `_write_item_files` to recreate. Production line 641: `_captures_dir.mkdir(parents=True, exist_ok=True)`. Hypothesis: `tmp_captures_dir` Path object captures a stale resolved path on POSIX where `tmp_path` differs from `kb.capture.CAPTURES_DIR` post-monkeypatch. Confirm via probe commit; fix by adjusting fixture or assertion. Drop the `@_WINDOWS_ONLY` decorator. Test: ubuntu-latest CI passes — `tmp_captures_dir.exists()` is True after rmtree+write.

### Area C — Dependabot litellm drift refresh

**AC9 — refresh Dependabot drift status.** Run `gh api repos/Asun28/llm-wiki-flywheel/dependabot/alerts` and `pip-audit -r requirements.txt --format=json`; for each litellm advisory ID (GHSA-r75f, GHSA-v4p8), verify whether pip-audit now surfaces it. Update the two BACKLOG entries with the cycle-38 re-check date and current status. If pip-audit caught up, add the ID to the CI workflow's `--ignore-vuln` arg with the existing narrow-role rationale (litellm dev-eval-only; zero `src/kb/` imports; click<8.2 transitive blocks 1.83.7 fix). Test: BACKLOG.md shows the refreshed status; CI workflow either unchanged (drift persists) or updated with new --ignore-vuln IDs.

### Area D — BACKLOG cleanup

**AC10 — delete resolved cycle-38 candidates from BACKLOG.** After AC1-AC8 ship, delete the two cycle-38+ entries `mock_scan_llm POSIX reload-leak investigation` and `TestExclusiveAtomicWrite + TestWriteItemFiles POSIX cleanup behaviour` from `BACKLOG.md`. Preserve cycle-39+ candidates: windows-latest CI matrix re-enable, GHA-Windows multiprocessing spawn investigation, the two Dependabot drift entries (re-pin to cycle-39 if still drifting). Test: `BACKLOG.md` no longer mentions the resolved entries.

## 4. Blast radius

| File | Change |
|------|--------|
| `tests/conftest.py` | AC1: widen `mock_scan_llm` to dual-site patch |
| `tests/test_capture.py` | AC2 (2 sites), AC3 (7 decorators), AC6 (2 tests + 2 patches), AC7-AC8 (2 tests; +probe diagnostics) |
| `tests/test_mcp_core.py` | AC4 (3 decorators) |
| `tests/test_cycle38_mock_scan_llm_reload_safe.py` (NEW) | AC5: regression test |
| `BACKLOG.md` | AC9 + AC10: drift refresh + resolved cleanup |
| `CHANGELOG.md` + `CHANGELOG-history.md` + `CLAUDE.md` + `docs/reference/testing.md` + `docs/reference/implementation-status.md` | Step 12 doc update |
| `.github/workflows/ci.yml` | AC9: ONLY if pip-audit caught up on litellm IDs (likely no change) |

**Source file changes**: 0-1 (`.github/workflows/ci.yml` if AC9 fires). Per cycle-37 L5 (`primary-session is cycle-level DEFAULT for ≤15 ACs / ≤5 src files`), this cycle qualifies for primary-session execution.

## 5. Verification path

- **Step 9 TDD per AC**: failing test → fix → green.
- **Step 10 CI hard gate**: full pytest + ruff + format + pip-audit + build, mirroring `.github/workflows/ci.yml` (cycle-34 L6).
- **Step 11 PR-introduced CVE diff**: zero new advisories vs Step-2 baseline.
- **Step 14 R1+R2 PR review**: 10-AC cycle below R3 trigger thresholds (cycle-17 L4: ≥25 ACs OR ≥10 design-gate questions OR new write surface OR new security enforcement point — none fire here).

## 6. Risk register

- **R1**: AC7/AC8 root cause may require deeper POSIX investigation than a single probe commit reveals. Mitigation: if probe-1 doesn't pinpoint, narrow scope — keep `_WINDOWS_ONLY` skipif on the offending test, document as cycle-39+ candidate, ship the rest.
- **R2**: Widening `mock_scan_llm` to ALSO patch `kb.utils.llm.call_llm_json` may break `test_extractors.py` etc. that already patch `kb.ingest.extractors.call_llm_json`. Mitigation: AC1 widens conditionally — only patch `kb.utils.llm` if `kb.utils.llm.call_llm_json` ≠ the original; assert via spy that the canonical-source patch is exercised only by capture-flow tests.
- **R3**: Reload-leak might not be the actual root cause of Category A (cycle-36 BACKLOG said "suspected reload-leak class"). Mitigation: AC5 regression test forces verification — if a probe commit shows the suspected scenario doesn't reproduce, pivot to a different hypothesis (e.g., `kb.capture` import-order issue, autouse fixture bypass).

## 7. Open questions for design eval (Step 4)

- Q1: Should `mock_scan_llm` patch also handle the `kb.ingest.extractors.call_llm_json` site? Currently several tests patch that site directly; widening the fixture may collide.
- Q2: For AC7 (POSIX off-by-one slug), is the right fix to ADJUST the test assertion (accept either `-2` or `-3` as legitimate POSIX behaviour) OR to FIX the production code (some `_scan_existing_slugs` / `_build_slug` divergence)?
- Q3: Should AC6 widen `atomic_text_write` patches in OTHER tests in the codebase (cycle-16 L1 same-class peer scan), or scope strictly to the two failing tests?
- Q4: For AC9, if pip-audit catches up on the litellm drift, is adding the IDs to `--ignore-vuln` an in-cycle decision or does it need a separate Step-5 design-gate pass?
- Q5: Should AC5's regression test live in `tests/test_cycle38_*` (cycle-tagged) OR `tests/test_capture.py::TestMockScanLlmReloadSafety` (folded into the canonical capture test file per cycle-4 L4 freeze-and-fold)?
