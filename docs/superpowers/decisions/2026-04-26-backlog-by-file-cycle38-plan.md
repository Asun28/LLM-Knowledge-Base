# Cycle 38 — Implementation Plan

**Date:** 2026-04-26
**Branch:** `feat/backlog-by-file-cycle38`
**Author:** Step-7 primary session per cycle-37 L5 (≤15 ACs, ≤5 src files, primary holds context)
**Inputs:** [requirements](2026-04-26-backlog-by-file-cycle38-requirements.md), [threat-model](2026-04-26-backlog-by-file-cycle38-threat-model.md), [design](2026-04-26-backlog-by-file-cycle38-design.md)

---

## Pre-flight grep verification (cycle-15 L1)

All cited symbols verified in Step-4 R1 Opus eval. Re-confirmed:

- `kb.capture.call_llm_json` at `src/kb/capture.py:37` — `from kb.utils.llm import call_llm_json`
- `kb.utils.llm.call_llm_json` at `src/kb/utils/llm.py:320` — `def call_llm_json(...)`
- `kb.capture.atomic_text_write` at `src/kb/capture.py:36` — `from kb.utils.io import atomic_text_write`
- `kb.utils.io.atomic_text_write` at `src/kb/utils/io.py:144` — `def atomic_text_write(...)`
- Module-import-time security guard at `src/kb/capture.py:832-844` — RuntimeError on CAPTURES_DIR outside PROJECT_ROOT
- `tests/test_capture.py:700-714` — `TestSymlinkGuard::test_symlink_outside_project_root_refuses_import` (the contamination source)
- `tests/conftest.py:362-391` — `mock_scan_llm` fixture (single-site patch today)
- `tests/test_capture.py:47-61` — `_REQUIRES_REAL_API_KEY` + `_WINDOWS_ONLY` markers
- `tests/test_capture.py:734,747,901,971` — Four `@_WINDOWS_ONLY` test sites
- `tests/test_capture.py:1062,1106,1130,1140,1170,1262,1420` — Seven `@_REQUIRES_REAL_API_KEY` sites
- `tests/test_mcp_core.py:339,372,395` — Three `@_REQUIRES_REAL_API_KEY` sites
- `pyproject.toml:62` — `select = ["E", "F", "I", "W", "UP"]` (T20 not present)

---

## Task ordering rationale

Per design D2: **AC0 → AC1 → AC2 → AC5 → AC3 → AC4 → AC6 → AC7 → AC8 → AC9 → AC10 + ruff T20**.

AC0 (subprocess refactor) MUST land first because AC5 case (b)/(c) depends on a clean `sys.modules["kb.capture"]` baseline — if the symlink test still does del+reimport in-process, AC5's regression test framework is unstable.

AC1+AC2 widen patches; AC5 codifies the regression. AC3+AC4 only flip skipif decorators (mechanical).

AC6 follows after Cat-A is green. AC7+AC8 are probe-style commits (with revert) for the POSIX off-by-one investigations.

AC9+AC10 are doc-only and run during Step 12.

---

## TASK 1 — AC0 Subprocess refactor of TestSymlinkGuard

**Files**: `tests/test_capture.py` (replace lines 694-714 of `TestSymlinkGuard` class)
**Change**: Move the security-guard verification into a subprocess so it never mutates the test runner's `sys.modules["kb.capture"]`.

**Implementation shape:**

```python
class TestSymlinkGuard:
    """Spec §3 — refuse to import if CAPTURES_DIR resolves outside PROJECT_ROOT.

    Cycle 38 AC0: runs the import-time check in a subprocess so the test
    does NOT mutate the test runner's sys.modules. Pre-cycle-38 used
    `del sys.modules["kb.capture"]` + reimport in-process, which left
    test_capture.py's pre-collection bindings (line 20+) holding OLD
    module function objects whose __globals__ was the OLD module __dict__.
    Subsequent mock_scan_llm patches on sys.modules["kb.capture"] (= NEW
    module) didn't reach the OLD __dict__ that test functions actually used,
    causing the cycle-36 ubuntu-probe Category-A failures. Subprocess
    isolation eliminates this contamination class entirely.
    """

    def test_symlink_outside_project_root_refuses_import(self, tmp_path):
        external_dir = tmp_path / "external"
        external_dir.mkdir()
        symlink_dir = tmp_path / "captures_symlink"
        try:
            symlink_dir.symlink_to(external_dir, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"symlink creation requires privileges on this OS: {exc}")
        project_root = tmp_path / "project_root"
        project_root.mkdir()

        # Probe: import kb.capture with patched CAPTURES_DIR pointing OUTSIDE
        # PROJECT_ROOT. The module-import-time guard at src/kb/capture.py:832-844
        # must raise RuntimeError("SECURITY: CAPTURES_DIR ...").
        probe = textwrap.dedent(
            """
            import os, sys
            # Set KB_PROJECT_ROOT BEFORE any kb import so kb.config picks it up.
            os.environ["KB_PROJECT_ROOT"] = sys.argv[2]
            import kb.config
            from pathlib import Path
            kb.config.CAPTURES_DIR = Path(sys.argv[1])
            kb.config.PROJECT_ROOT = Path(sys.argv[2])
            try:
                import kb.capture
            except RuntimeError as exc:
                if "SECURITY: CAPTURES_DIR" in str(exc):
                    sys.exit(42)
                sys.stderr.write(f"unexpected RuntimeError: {exc}\\n")
                sys.exit(1)
            sys.stderr.write("module imported without raising\\n")
            sys.exit(2)
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", probe, str(symlink_dir), str(project_root)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 42, (
            f"expected SECURITY: CAPTURES_DIR exit 42, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
```

**Test expectations:**
- Refactored test passes on POSIX (subprocess can create symlink as user).
- Refactored test passes on Windows (with developer mode) OR skips cleanly via the OSError except.
- After this task, `grep -n "del sys.modules" tests/test_capture.py` returns zero hits.

**Verification:**
- `grep -n "del sys.modules" tests/test_capture.py` = 0 hits.
- `grep -nE "subprocess\.run.*kb\.capture" tests/test_capture.py` ≥ 1 hit.
- Run full pytest locally to confirm no regression on existing tests.

**Criteria**: AC0 (D-NEW); CONDITIONS §1.

**Threat**: T2 (test-pollution residual) closed.

---

## TASK 2 — AC1 widen mock_scan_llm to dual-site patch

**File**: `tests/conftest.py` (lines 363-391)
**Change**: Patch `kb.utils.llm.call_llm_json` BEFORE `kb.capture.call_llm_json` for defense-in-depth against future similar contamination.

**Implementation shape:**

```python
@pytest.fixture
def mock_scan_llm(monkeypatch):
    """Install a canned JSON response for call_llm_json inside kb.capture.

    Cycle 38 AC1: dual-site patch (kb.utils.llm.call_llm_json BEFORE
    kb.capture.call_llm_json) defends against future contamination of
    sys.modules["kb.capture"] (cycle-19 L2 / cycle-20 L1 reload-leak class).
    Apply utils.llm first so any subsequent re-import of kb.capture picks
    up the mocked function via `from kb.utils.llm import call_llm_json`.

    Mock signature mirrors the REAL call_llm_json signature
    (src/kb/utils/llm.py): tier and schema are keyword-only, schema is required.
    The sentinel + assertions catch the bug where capture.py forgets to pass
    schema=_CAPTURE_SCHEMA.
    """

    def _install(
        response: dict,
        expected_schema_keys: tuple[str, ...] = ("items", "filtered_out_count"),
    ):
        def fake_call(prompt, *, tier="write", schema=_REQUIRED, system="", **_kw):
            assert tier == "scan", f"kb_capture must use scan tier, got {tier!r}"
            msg = "kb_capture must pass schema= to call_llm_json"
            assert schema is not _REQUIRED, msg
            assert isinstance(schema, dict), f"schema must be dict, got {type(schema)}"
            for key in expected_schema_keys:
                prop = schema.get("properties", {})
                assert key in prop, f"schema missing property {key!r}"
            required = set(schema.get("required", []))
            missing = required - set(response)
            assert not missing, f"mock response missing required schema keys: {missing}"
            return response

        # Cycle 38 AC1 — patch utils.llm FIRST (canonical source) then kb.capture
        # so any test that triggers a re-import of kb.capture picks up the mock
        # via `from kb.utils.llm import call_llm_json` at re-import time.
        monkeypatch.setattr("kb.utils.llm.call_llm_json", fake_call)
        monkeypatch.setattr("kb.capture.call_llm_json", fake_call)

    return _install
```

**Test expectations:** existing mock_scan_llm callers still pass; AC5 regression test (TASK 4) verifies dual-site shape.

**Verification:**
- `grep -n "kb.utils.llm.call_llm_json" tests/conftest.py` ≥ 1 hit (precedes the kb.capture line).
- Fixture docstring contains "patch utils.llm FIRST".

**Criteria**: AC1; CONDITIONS §2.

**Threat**: T1 (mock-bypass via reload-leak) primary mitigation.

---

## TASK 3 — AC2 widen inline kb.capture.call_llm_json patches

**File**: `tests/test_capture.py` lines 419, 1126
**Change**: Pair each `monkeypatch.setattr("kb.capture.call_llm_json", X)` with a preceding `monkeypatch.setattr("kb.utils.llm.call_llm_json", X)`.

**Specific edits:**

1. Around line 419 (TestExtractAndVerify::test_extract_calls_scan_tier or similar): paired patch.
2. Around line 1126 (TestCaptureItems::test_llm_error_propagates_class_b): paired patch with `raise_llm`.

**Test expectations:** existing tests still pass; defends against post-AC0 reload-leak class.

**Verification:**
- `grep -nE "kb\.utils\.llm\.call_llm_json" tests/test_capture.py` ≥ 2 hits (lines just before 419 and 1126 equivalents).

**Criteria**: AC2.

**Threat**: T1 secondary mitigation.

---

## TASK 4 — AC5 regression test for mock_scan_llm reload-safety

**File**: NEW `tests/test_cycle38_mock_scan_llm_reload_safe.py`
**Change**: Three test cases per CONDITIONS §3.

**Implementation shape:**

```python
"""Cycle 38 AC5 — pin the mock_scan_llm dual-site patch contract.

Three cases prove the dual-site fix (cycle-38 AC1) is non-vacuous:

(a) baseline — install dual-site mock_scan_llm, call capture_items, mock fires.
(b) single-site contaminated — manually install single-site patch ONLY (mimic
    pre-AC1 state), simulate sys.modules["kb.capture"] deletion + reimport,
    call capture_items via FRESH `from kb.capture import` (not the test-module
    snapshot), mock did NOT fire (proves single-site is broken post-reimport).
(c) dual-site survives contamination — install dual-site mock_scan_llm, repeat
    case (b)'s reimport sequence, mock DID fire (proves dual-site fix works).

Manual revert check: locally revert AC1's dual-site widening; case (c) MUST
FAIL (mock would not fire). Documented in module docstring per
feedback_test_behavior_over_signature.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable

import pytest


def _make_canned_response() -> dict:
    return {
        "items": [
            {
                "title": "test",
                "kind": "decision",
                "body": "we decided X",
                "one_line_summary": "s",
                "confidence": "stated",
            }
        ],
        "filtered_out_count": 0,
    }


def _make_fake_call(received: list[dict]) -> Callable:
    def _fake(prompt, *, tier="write", schema, system="", **_kw):
        received.append({"tier": tier, "schema": schema})
        return _make_canned_response()

    return _fake


class TestMockScanLlmReloadSafety:
    """Cycle 38 AC5 — dual-site patch survives sys.modules re-import contamination."""

    def test_baseline_dual_site_install_mock_fires(
        self, tmp_captures_dir, mock_scan_llm, reset_rate_limit, monkeypatch
    ):
        """Case (a): install dual-site mock, call capture_items, mock fires."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        from kb.capture import capture_items

        mock_scan_llm(_make_canned_response())
        result = capture_items("we decided X" * 5, provenance="cycle38-baseline")
        assert result.rejected_reason is None
        assert len(result.items) == 1

    def test_single_site_install_breaks_post_reimport(
        self, tmp_captures_dir, reset_rate_limit, monkeypatch
    ):
        """Case (b): single-site patch ONLY; sys.modules deletion + reimport
        breaks the patch (mock did NOT fire — should attempt real SDK).

        This MUST fail (mock not fired / SDK reached) under pre-AC1 single-site
        fixture. Verifies the contamination class is real and the AC5 test
        is non-vacuous.
        """
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        # Single-site only (mimics pre-AC1 state — DO NOT call mock_scan_llm fixture).
        received: list[dict] = []
        monkeypatch.setattr("kb.capture.call_llm_json", _make_fake_call(received))

        # Simulate the cycle-36 contamination: del sys.modules["kb.capture"]
        # + reimport. Use monkeypatch.delitem for auto-teardown.
        monkeypatch.delitem(sys.modules, "kb.capture", raising=False)
        kb_capture_fresh = importlib.import_module("kb.capture")

        # FRESH binding (not the pre-collection snapshot from test_capture.py).
        # capture_items_fresh.__globals__ is the NEW module's __dict__.
        capture_items_fresh = kb_capture_fresh.capture_items

        # Without dual-site patch, NEW module's call_llm_json was bound at
        # re-import time from kb.utils.llm (the REAL function, since we did
        # NOT patch utils.llm). The REAL function tries the Anthropic SDK
        # with no key set; it should raise an error rather than land in our
        # received list.
        from kb.errors import LLMError

        with pytest.raises((LLMError, Exception)):
            capture_items_fresh("we decided X" * 5, provenance="cycle38-case-b")

        # Mock did NOT fire — single-site patch is broken post-reimport.
        assert received == [], (
            f"single-site patch should NOT survive reimport; mock fired with {received!r}"
        )

    def test_dual_site_install_survives_post_reimport(
        self, tmp_captures_dir, reset_rate_limit, monkeypatch
    ):
        """Case (c): dual-site patch survives sys.modules deletion + reimport.

        Manual revert check: revert AC1's dual-site widening locally and run
        ONLY this test (`pytest tests/test_cycle38_*.py::*case_c`). It MUST
        FAIL (mock fires zero times). Documents `feedback_test_behavior_over_signature`.
        """
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        # Dual-site patch via the cycle-38 widened fixture pattern: utils.llm FIRST.
        received: list[dict] = []
        fake = _make_fake_call(received)
        monkeypatch.setattr("kb.utils.llm.call_llm_json", fake)
        monkeypatch.setattr("kb.capture.call_llm_json", fake)

        # Same reimport sequence as case (b).
        monkeypatch.delitem(sys.modules, "kb.capture", raising=False)
        kb_capture_fresh = importlib.import_module("kb.capture")
        capture_items_fresh = kb_capture_fresh.capture_items

        result = capture_items_fresh(
            "we decided X" * 5, provenance="cycle38-case-c"
        )

        # Mock fired (NEW kb.capture's `from kb.utils.llm import call_llm_json`
        # picked up the patched value because we patched utils.llm BEFORE the
        # reimport).
        assert len(received) == 1, f"dual-site patch should fire mock; received={received!r}"
        assert result.rejected_reason is None
        assert len(result.items) == 1
```

**Test expectations:**
- Cases (a) and (c) PASS. Case (b) PASSES (asserts mock did NOT fire — proves single-site broken).
- Manual revert check: revert AC1; case (c) FAILS. Verify locally before commit.

**Verification:**
- `pytest tests/test_cycle38_mock_scan_llm_reload_safe.py -v` shows 3 PASSED.
- After local revert of AC1 line `monkeypatch.setattr("kb.utils.llm.call_llm_json", fake_call)`: case (c) fails. Restore AC1.

**Criteria**: AC5; CONDITIONS §3.

**Threat**: T1 (regression contract).

---

## TASK 5 — AC3 + AC4 remove `_REQUIRES_REAL_API_KEY` decorators

**Files**:
- `tests/test_capture.py` lines 1062, 1106, 1130, 1140, 1170, 1262, 1420 (7 sites)
- `tests/test_mcp_core.py` lines 339, 372, 395 (3 sites)

**Change**: Drop `@_REQUIRES_REAL_API_KEY` decorator from each. Keep the `_REQUIRES_REAL_API_KEY` definition itself in case future tests need it; document the cycle-38 disposition.

**Test expectations:** All 10 tests run on CI dummy key without 401 auth-error failures.

**Verification:**
- `grep -nE "@_REQUIRES_REAL_API_KEY" tests/test_capture.py tests/test_mcp_core.py` returns 0 hits after this task.
- Full pytest locally on developer machine (skips count drops by 10).

**Criteria**: AC3 + AC4.

**Threat**: T6 (CI regression risk on re-enable) — mitigated by AC0 + AC1.

---

## TASK 6 — AC6 widen atomic_text_write patches in 2 tests + drop `@_WINDOWS_ONLY`

**File**: `tests/test_capture.py` lines 734-757 (`test_cleans_up_reservation_on_inner_write_failure` + `test_cleans_up_on_keyboard_interrupt`)

**Change**: For each test, ADD `monkeypatch.setattr("kb.utils.io.atomic_text_write", boom/interrupted)` BEFORE the existing `monkeypatch.setattr("kb.capture.atomic_text_write", ...)` line. Drop `@_WINDOWS_ONLY` from both.

**Test expectations:** Both tests pass on POSIX (after AC0 lands; reload-leak on `kb.capture.atomic_text_write` is also defended).

**Verification:**
- `grep -nE "@_WINDOWS_ONLY" tests/test_capture.py` returns 2 hits (only `test_creates_dir_if_missing` and `test_pre_existing_file_collision` remain).
- `grep -nE "kb\.utils\.io\.atomic_text_write" tests/test_capture.py` ≥ 2 hits (both cleans_up tests).

**Criteria**: AC6; CONDITIONS §6.

**Threat**: T1 (atomic_text_write reload-leak peer); strict-scope per design Q3.

---

## TASK 7 — AC7 + AC8 POSIX off-by-one slug + creates_dir probes (probe-style commits)

**Strategy**: Two-commit probe-revert pattern per design D6.

**Probe commit:**
- Add `print()` diagnostics in `src/kb/capture.py::_scan_existing_slugs`, `_build_slug`, `_reserve_hidden_temp`, and `_write_item_files` mkdir line.
- Drop `@_WINDOWS_ONLY` from `test_creates_dir_if_missing` and `test_pre_existing_file_collision`.
- Push to feature branch.
- ubuntu CI emits the diagnostic prints in the failed-test output.

**Analysis pass:**
- Read CI logs to identify the actual POSIX state (extra ghost files? slugs returned in different order? `_build_slug` skipping a number?).
- Diagnose root cause.

**Fix commit:**
- Apply targeted fix (production OR test loosen, per cycle-38 design preference: test-side fix preferred).
- REVERT the `print()` diagnostics in the same commit.
- `grep -n "print(" src/kb/capture.py` against the cycle-38 diff returns zero new lines.

**M1 standing pre-auth fallback:** if probe inconclusive after two iterations, restore `@_WINDOWS_ONLY` on the offending test, file cycle-39 BACKLOG entry per design CONDITIONS §7-§8, and continue.

**Verification:**
- After fix commit: both tests pass on ubuntu CI.
- `grep -n "print(" src/kb/capture.py` against `git diff main` returns zero lines.
- `grep -nE "@_WINDOWS_ONLY" tests/test_capture.py` returns 0 hits (or 1-2 if M1 fallback fires).

**Criteria**: AC7 + AC8; CONDITIONS §7 + §8.

**Threat**: T3 (POSIX behaviour drift) — bounded by `_SLUG_COLLISION_CEILING=10000` + `O_EXCL`.

---

## TASK 8 — Add ruff T20 to pyproject.toml

**File**: `pyproject.toml` line 62
**Change**: `select = ["E", "F", "I", "W", "UP"]` → `select = ["E", "F", "I", "W", "UP", "T20"]`

This catches any `print()` left in `src/kb/` after probe commits. Defense-in-depth per design Q5.

**Test expectations:** `ruff check src/` passes (no current `print()` in src/kb/ except acceptable ones — verify via grep before committing).

**Verification:**
- Pre-flight: `ruff check src/ --select T20` shows current state. If hits, decide whether to fix or noqa-ignore (legit prints, e.g., CLI `--version` output).
- After T20 add: `ruff check src/ --select T20` clean.

**Criteria**: design Q5 amendment.

**Threat**: T3-adjacent (probe-print escape).

---

## TASK 9 — AC9 Dependabot drift refresh

**File**: `BACKLOG.md` (the two cycle-38+ litellm GHSA-r75f / GHSA-v4p8 entries)
**Change**: Update re-check dates to 2026-04-26.

**Pre-flight**:
- Re-run `gh api repos/Asun28/llm-wiki-flywheel/dependabot/alerts --paginate --jq ...`. Verified 2026-04-26: 4 open alerts (3 litellm + 1 ragas).
- Re-run `pip-audit --ignore-vuln=GHSA-xqmj-j6mv-4862 --format=json` (live-env mode, no `-r`). Verify whether GHSA-r75f / GHSA-v4p8 surface.
- Expected outcome (no-change branch): pip-audit does NOT surface those IDs.

**If catch-up branch fires** (pip-audit DOES surface them): add the IDs to `.github/workflows/ci.yml` `--ignore-vuln` arg using existing narrow-role rationale.

**Test expectations:** None (BACKLOG-only change in expected branch). If catch-up: `pip-audit` step in CI passes with new --ignore-vuln IDs.

**Verification:**
- Expected: `git diff main -- .github/workflows/ci.yml SECURITY.md requirements.txt` shows no diff.
- BACKLOG diff shows date refresh only.

**Criteria**: AC9.

**Threat**: T4 (drift attestation).

---

## TASK 10 — AC10 BACKLOG cleanup + cycle-39 fold pre-register + scratch-file hygiene

**File**: `BACKLOG.md`
**Change**:
1. Delete the two cycle-38+ entries that are RESOLVED:
   - `mock_scan_llm POSIX reload-leak investigation` (AC0+AC1+AC5 close it)
   - `TestExclusiveAtomicWrite + TestWriteItemFiles POSIX cleanup behaviour` (AC6+AC7+AC8 close it)
2. ADD new cycle-39+ entry: `Fold tests/test_cycle38_mock_scan_llm_reload_safe.py into tests/test_capture.py::TestMockScanLlmReloadSafety` (LOW; cycle-4 L4 freeze-and-fold).
3. Verify scratch files absent: `ls findings.md progress.md task_plan.md claude4.6.md docs/repo_review.md docs/repo_review.html 2>&1 | grep "No such"` should match all 6.

**Test expectations:** `tests/test_cycle34_release_hygiene.py::test_scratch_files_absent` (or similar — grep to confirm name) still passes.

**Verification:**
- BACKLOG diff matches expected (2 deletes + 1 add).
- `tests/test_cycle34_release_hygiene.py` passes.

**Criteria**: AC10; CONDITIONS §10.

---

## Step-9 commit ordering

| # | Commit subject | ACs | Approx files |
|---|---|---|---|
| 1 | `test(cycle 38): subprocess refactor of TestSymlinkGuard (AC0)` | AC0 | tests/test_capture.py |
| 2 | `test(cycle 38): widen mock_scan_llm + inline patches dual-site (AC1, AC2)` | AC1, AC2 | tests/conftest.py, tests/test_capture.py |
| 3 | `test(cycle 38): regression test for mock_scan_llm reload-safety (AC5)` | AC5 | tests/test_cycle38_mock_scan_llm_reload_safe.py (NEW) |
| 4 | `test(cycle 38): re-enable POSIX SDK + Windows-only tests (AC3, AC4, AC6)` | AC3, AC4, AC6 | tests/test_capture.py, tests/test_mcp_core.py |
| 5 | `probe(cycle 38): diagnostic prints for AC7/AC8 POSIX investigation` | AC7-a, AC8-a | src/kb/capture.py, tests/test_capture.py |
| 6 | `fix(cycle 38): POSIX off-by-one slug + creates_dir + revert probe (AC7, AC8)` | AC7-b, AC8-b | src/kb/capture.py, tests/test_capture.py |
| 7 | `chore(cycle 38): add ruff T20 (flake8-print) for src/ defense (Q5)` | design Q5 | pyproject.toml |
| 8 | `docs(cycle 38): CHANGELOG + BACKLOG cleanup + cycle-39 fold pre-register (AC9, AC10)` | AC9, AC10 | BACKLOG.md, CHANGELOG.md, CHANGELOG-history.md, CLAUDE.md, docs/reference/* |

Squash-merge mandate: PR is squash-merged so probe + revert pair never lands as separate commits on main per design Q5.

---

## Step-10 CI hard gate (local mirror, post-task-7)

Run BEFORE Step 13 PR open per cycle-34 L6 (mirror EVERY `run:` step in `.github/workflows/ci.yml` exactly).

ci.yml has 10 named steps: Checkout, Set up Python 3.12, Install package + ALL extras, Install CI tooling, Ruff check, Pytest collection, Pytest full suite, Pip resolver check (soft-fail), Pip-audit (4 --ignore-vuln IDs), Build + twine check.

The first four (checkout / setup-python / install-extras / install-tooling) are pre-flight steps that happen at venv-setup time on a local developer machine (we already have `.venv/Scripts/*` populated). Re-running them mid-cycle is unnecessary unless cycle 38 modifies dependencies (it does not — verified by `git diff main -- pyproject.toml requirements.txt`). Document this assumption explicitly:

```bash
# 0. Pre-flight (assumed already done; re-run only if pyproject.toml or requirements.txt changed in this cycle)
#    .venv/Scripts/python.exe -m pip install -e '.[dev,formats,augment,hybrid,eval]'
#    .venv/Scripts/python.exe -m pip install build twine pip-audit

# 1. Ruff check (mirrors ci.yml step "Ruff check")
.venv/Scripts/ruff.exe check src/ tests/

# 2. Pytest collection smoke (mirrors ci.yml step "Pytest collection (smoke check)")
.venv/Scripts/python.exe -m pytest --collect-only -q

# 3. Pytest full suite strict (mirrors ci.yml step "Pytest full suite (strict — cycle 36 closure)")
.venv/Scripts/python.exe -m pytest -q

# 4. Pip resolver check (soft-fail per ci.yml comment — three known conflicts; output is informational)
.venv/Scripts/python.exe -m pip check
# Exit code is non-zero on existing conflicts; that's expected per cycle-34 T5 ; no action needed.

# 5. Pip-audit (live-env mode with EXACT ci.yml --ignore-vuln IDs — design Q4)
.venv/Scripts/pip-audit.exe \
  --ignore-vuln=CVE-2025-69872 \
  --ignore-vuln=GHSA-xqmj-j6mv-4862 \
  --ignore-vuln=CVE-2026-3219 \
  --ignore-vuln=CVE-2026-6587

# 6. Build + twine check (mirrors ci.yml step "Build distribution + twine check")
.venv/Scripts/python.exe -m build && .venv/Scripts/twine.exe check dist/*

# 7. Probe-print escape grep (design Q5; not a ci.yml step but pre-PR hygiene)
grep -n 'print(' src/kb/capture.py | grep -v '^\s*#'
# Expected: zero new lines vs main; only legitimate src/kb/cli.py --version prints.
```

`ruff format --check` is NOT in ci.yml — the project relies on `ruff check` for both lint and format-violation detection (UP and W rules cover formatting). The plan does NOT add a separate format-check step, matching ci.yml. Run `ruff format src/ tests/` manually if local edits introduce stylistic drift; ci.yml does not gate on it.

All MUST pass (with the documented `pip check` soft-fail exception) before Step 13.

---

## Step-11 security verify checklist

Per threat-model §7 (with Q4 amendment to live-env pip-audit). Each threat maps to a CONCRETE verification command (not a status):

| Threat | Check | Verification command |
|---|---|---|
| T1 | mock_scan_llm dual-site patch landed | `grep -nE "kb\.utils\.llm\.call_llm_json" tests/conftest.py` ≥ 1 hit AND fixture docstring contains "patch utils.llm FIRST" |
| T2 | New AC5 regression test does NOT leak state into sibling tests in collection order | `python -m pytest tests/test_cycle38_mock_scan_llm_reload_safe.py tests/test_capture.py tests/test_mcp_core.py -v` (full sibling-order run) — must show ALL tests passed; no late-arriving 401-auth errors in subsequent test files |
| T3a | POSIX off-by-one fix landed | `python -m pytest tests/test_capture.py::TestWriteItemFiles::test_pre_existing_file_collision tests/test_capture.py::TestWriteItemFiles::test_creates_dir_if_missing -v` passes on ubuntu-latest CI |
| T3b | No production print() escape | `git diff main -- src/kb/capture.py \| grep -E '^\+.*print\('` returns zero lines |
| T4 | Dependabot drift status updated | `git diff main -- BACKLOG.md \| grep -E "(GHSA-r75f-5x8p-qvmc\|GHSA-v4p8-mg3p-g94g).*2026-04-26"` matches both refreshed entries |
| T5 | mock_scan_llm canned response unchanged in shape | `grep -nE "schema\s*is\s*not\s*_REQUIRED\|isinstance\(schema, dict\)" tests/conftest.py` matches the existing assertion pattern (count unchanged from main) |
| T6 | All 14 re-enabled tests pass on ubuntu-latest | `python -m pytest tests/test_capture.py::TestCaptureItems tests/test_capture.py::TestPipelineFrontmatterStrip::test_frontmatter_stripped_for_capture_source tests/test_capture.py::TestRoundTripIntegration::test_capture_then_ingest_renders_wiki_summary tests/test_capture.py::TestExclusiveAtomicWrite tests/test_capture.py::TestWriteItemFiles tests/test_mcp_core.py::TestKbCaptureWrapper -v` shows all 14 tests in PASSED state on ubuntu-latest CI |
| T7 | PR-introduced CVE diff zero | `.venv/Scripts/pip-audit.exe --format=json > /tmp/branch.json && python -c "import json; b=json.loads(open('/tmp/branch.json').read()[(open('/tmp/branch.json').read().index('{'))::]); m=json.loads(open('.data/cycle-38/cve-baseline.json').read()[(open('.data/cycle-38/cve-baseline.json').read().index('{'))::]); branch_ids={v['id'] for d in b['dependencies'] for v in d.get('vulns',[])}; main_ids={v['id'] for d in m['dependencies'] for v in d.get('vulns',[])}; print('introduced:', branch_ids - main_ids)"` — must print `introduced: set()` |

---

## Risk register update

R1 (AC7/AC8 root-cause depth) — covered by M1 standing pre-auth.
R2 (mock_scan_llm extractors collision) — DROPPED (design Q1 resolves to capture+utils.llm only).
R3 (reload-leak might not be root cause) — DROPPED (R2 Codex confirmed sys.modules deletion is the real mechanism).
R4 (AC0 subprocess +0.3-0.5s runtime) — accepted; trivial CI cost.
R5 (subprocess env-var passing OS quirks) — mitigated via `env` kwarg + capture_output.
R6 (NEW) — ruff T20 add may flag legitimate prints in `src/kb/cli.py --version` etc. Mitigation: pre-flight ruff check; add `# noqa: T201` on legitimate sites.

---

## Step-7 plan-gate handoff

Plan covers:
- ✓ Every AC0-AC10 from design's FINAL AC LIST.
- ✓ Every CONDITIONS §1-§11 from design.
- ✓ Every threat T1-T7 verification step (T2 maps to sibling-order pytest; T3 split into T3a fix + T3b print-escape; T6 maps to specific 14-test pytest invocation; T7 maps to baseline-diff Python script).
- ✓ Step-10 CI mirror matches ci.yml exactly (10 named steps; pre-flight install steps documented as already-done; pip-audit uses all 4 --ignore-vuln IDs from ci.yml; no extraneous `ruff format --check`).
- ✓ Probe-revert hygiene (Q5 hardened).
- ✓ Squash-merge mandate.
- ✓ M1 scope-cut pre-auth on AC7/AC8.

Ready for Step-8 plan-gate Codex review.

---

## Plan-gate Round 2 amendments (2026-04-26)

Step-8 R1 plan-gate (Codex) returned REJECT with three findings:
- F2/F7: T2 mapped to AC0-verification grep, not the sibling-leak threat. T6 mapped to vague "CI green".
- F6: Step-10 mirror missing 4 ci.yml steps (Checkout / setup-python / install-extras / install-tooling); pip-audit had wrong --ignore-vuln args (1 ID instead of 4); included extraneous `ruff format --check` not in ci.yml.

Per cycle-21 L1 (plan-gate REJECT resolved inline when operator holds full context, gaps are documentation/design clarifications not code-exploration), all three findings resolved in this same plan doc:
- Step-10 mirror block rewritten to mirror ci.yml's 10 named steps exactly, with pre-flight install assumption documented; pip-audit args extended to 4 IDs.
- Step-11 verification table rewritten so each threat row contains a concrete grep/pytest/python command that returns a binary pass/fail.
- T2 now maps to a full sibling-order pytest invocation (the threat-model §7 reference).
- T6 now maps to a 14-test pytest invocation, not "CI green".
- T3 split into T3a (test passes) and T3b (no print() escape) for cleaner audit.

These amendments do not change AC ordering or any task body — they refine Step-10 mirror and Step-11 verify only.
