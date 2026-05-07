"""Cycle 67 AC10 + AC11 — CI dummy-key-leak-guard scope broadening + snapshot-update reject.

AC10 (verified-already-shipped via cycle 65 AC19): cycle 65's
`tests/test_cycle65_ci_snapshot_flags.py::test_ci_yml_no_snapshot_update`
asserts `--snapshot-update` is absent from any CI run block via YAML AST.
This file does NOT duplicate that test; it adds AC11 broadening
verification on top, plus a defensive AC10 backstop.

AC11: cycle 65 AC22 shipped a `dummy-key-leak-guard` step scoped to
`src/**` only. Mimo r5 Q7 flagged a real risk: a test mocking HTTP at
the httpx layer (rather than the SDK constructor) could bake the dummy
literal into a VCR cassette / snapshot file under `tests/__snapshots__/`.
Cycle 67 AC11 broadens the scan to ALL tracked files with an explicit
allowlist for legitimate references.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_CI_YML = Path(".github/workflows/ci.yml")


def _find_step(step_name: str) -> dict:
    """Return the raw step dict for the named step, or pytest.fail."""
    assert _CI_YML.exists(), f"{_CI_YML} not found (run from repo root)"
    ci_data = yaml.safe_load(_CI_YML.read_text(encoding="utf-8"))
    for job_data in ci_data.get("jobs", {}).values():
        for step in job_data.get("steps", []):
            if isinstance(step, dict) and step.get("name") == step_name:
                return step
    pytest.fail(f"step '{step_name}' not found in {_CI_YML}")


def test_dummy_key_leak_guard_extracts_value_dynamically() -> None:
    """AC11 / R1-F8: the step pulls the dummy key value from ci.yml at runtime
    (not hardcoded as a literal substring). Catches a future drift where the
    dummy value rotates and the literal in the grep regex stays stale.
    """
    step = _find_step("dummy-key-leak-guard")
    run_block = step.get("run", "")
    assert "grep -oE" in run_block, (
        "AC11: dummy-key step must extract the key value dynamically via "
        "`grep -oE 'sk-ant-dummy...' .github/workflows/ci.yml`. Hardcoding "
        "the literal substring drifts when the dummy value rotates."
    )
    assert "DUMMY=" in run_block, (
        "AC11: dummy-key step must capture the extracted value into a shell "
        "variable so the grep target is the FULL key, not a partial substring."
    )


def test_dummy_key_leak_guard_scopes_to_all_tracked_files() -> None:
    """AC11 broadening: scope changed from `src/**` only (cycle 65 AC22) to
    `git ls-files` with no path filter. Catches the mimo r5 Q7 case where a
    cassette / snapshot file under tests/__snapshots__/ might bake the
    dummy literal in.
    """
    step = _find_step("dummy-key-leak-guard")
    run_block = step.get("run", "")
    # The new step uses `git ls-files | xargs grep -l "$DUMMY"` (no path arg).
    assert "git ls-files |" in run_block or "git ls-files\n" in run_block, (
        "AC11: `git ls-files` must be invoked WITHOUT a path filter (no "
        "`'src/**'` argument). The cycle-65 src-only scope is broadened to "
        "all tracked files in cycle 67."
    )
    # Defensive: the literal `'src/**'` should NOT appear as a path argument
    # to git ls-files in the broadened step (it can still appear in comments).
    code_lines = [line for line in run_block.splitlines() if not line.strip().startswith("#")]
    code_text = "\n".join(code_lines)
    assert "'src/**'" not in code_text, (
        "AC11: src-only scoping has been broadened; `git ls-files 'src/**'` "
        "should no longer appear in the active step body."
    )


def test_dummy_key_leak_guard_has_allowlist() -> None:
    """AC11 / C-AC11-allowlist: the broadened step must allowlist legitimate
    documentation references so BACKLOG / CHANGELOG / decision-notes /
    docs/reference/testing.md / cycle-65 guard test / api_key helper /
    cycle-67 tests do not trigger false positives.
    """
    step = _find_step("dummy-key-leak-guard")
    run_block = step.get("run", "")
    required_allowlist_entries = [
        "BACKLOG",
        "CHANGELOG",
        "docs/reference/testing",
        "docs/superpowers/decisions",
    ]
    for entry in required_allowlist_entries:
        assert entry in run_block, (
            f"AC11 / C-AC11-allowlist: legitimate doc reference `{entry}` "
            f"must be in the dummy-key-leak-guard allowlist regex.\n"
            f"Step run block:\n{run_block}"
        )


def test_dummy_key_leak_guard_excludes_self_from_grep() -> None:
    """AC11 sanity check: the step itself uses `sk-ant-dummy` (in the grep
    pattern), so the allowlist MUST exempt `.github/workflows/ci.yml` to
    avoid the step always failing on itself."""
    step = _find_step("dummy-key-leak-guard")
    run_block = step.get("run", "")
    assert ".github/workflows/ci.yml" in run_block, (
        "AC11: ci.yml itself must be in the allowlist (otherwise the step's "
        "own grep pattern matches and the step always fails)."
    )


def test_ac10_snapshot_update_guard_backstop() -> None:
    """AC10 backstop: cycle 65 AC19 already shipped the snapshot-update
    guard via `tests/test_cycle65_ci_snapshot_flags.py::test_ci_yml_no_snapshot_update`.
    This test re-asserts the same invariant against current ci.yml so the
    AC10 contract survives even if the cycle-65 test file is ever refactored.
    """
    assert _CI_YML.exists()
    ci_data = yaml.safe_load(_CI_YML.read_text(encoding="utf-8"))
    for job_name, job_data in ci_data.get("jobs", {}).items():
        for step in job_data.get("steps", []):
            if isinstance(step, dict):
                run_block = step.get("run", "")
                assert "--snapshot-update" not in run_block, (
                    f"AC10 / cycle-65 AC19: job '{job_name}' contains "
                    f"--snapshot-update in run block. AC09 paired-negative-controls "
                    f"would pass trivially. Regenerate snapshots locally + commit."
                )
