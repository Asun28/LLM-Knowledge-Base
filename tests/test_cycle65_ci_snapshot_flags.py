"""Tests for AC19 — CI snapshot flags enforcement.

Cycle 65 AC19 — verify that CI snapshots are not auto-updated and that
unused snapshots are warned about.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def test_ci_yml_no_snapshot_update():
    """Assert CI does NOT auto-update snapshots.

    C22-bis — ensure the --snapshot-update flag is not present in CI.
    """
    ci_file = Path(".github/workflows/ci.yml")
    assert ci_file.exists(), ".github/workflows/ci.yml not found"

    with open(ci_file, encoding="utf-8") as f:
        content = f.read()

    # Parse YAML to extract all run blocks
    try:
        ci_data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        pytest.fail(f"Failed to parse CI YAML: {exc}")

    # Walk all jobs and steps
    jobs = ci_data.get("jobs", {})
    found_snapshot_update = False

    for job_name, job_data in jobs.items():
        steps = job_data.get("steps", [])
        for step in steps:
            if isinstance(step, dict):
                run_block = step.get("run", "")
                if run_block and "--snapshot-update" in run_block:
                    found_snapshot_update = True
                    pytest.fail(
                        f"Job '{job_name}' contains --snapshot-update in run block: {run_block}"
                    )

    # Ensure we actually parsed some steps
    assert len(jobs) > 0, "No jobs found in CI YAML"


def test_ci_yml_has_snapshot_warn_unused():
    """Assert CI includes --snapshot-warn-unused flag.

    C22-bis — ensure snapshots are verified for unused entries.
    """
    ci_file = Path(".github/workflows/ci.yml")
    assert ci_file.exists(), ".github/workflows/ci.yml not found"

    with open(ci_file, encoding="utf-8") as f:
        content = f.read()

    # Parse YAML to extract all run blocks
    try:
        ci_data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        pytest.fail(f"Failed to parse CI YAML: {exc}")

    # Walk all jobs and steps
    jobs = ci_data.get("jobs", {})
    found_snapshot_warn = False

    for job_name, job_data in jobs.items():
        steps = job_data.get("steps", [])
        for step in steps:
            if isinstance(step, dict):
                run_block = step.get("run", "")
                if run_block and "--snapshot-warn-unused" in run_block:
                    found_snapshot_warn = True
                    break
        if found_snapshot_warn:
            break

    assert found_snapshot_warn, "--snapshot-warn-unused not found in any CI step"
