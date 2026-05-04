"""Tests for AC22 — CI dummy-key leak guard step.

Cycle 65 AC22 — verify that the CI includes a step to guard against accidental
commits of the dummy API key pattern to production code files.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def test_grep_step_present_in_ci_yml():
    """Assert CI has the dummy-key-leak-guard step with proper grep logic.

    C19 — verify the leak-guard grep step is present and correct.
    """
    ci_file = Path(".github/workflows/ci.yml")
    assert ci_file.exists(), ".github/workflows/ci.yml not found"

    with open(ci_file, encoding="utf-8") as f:
        content = f.read()

    # Parse YAML to extract steps
    try:
        ci_data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        pytest.fail(f"Failed to parse CI YAML: {exc}")

    # Find the dummy-key-leak-guard step
    jobs = ci_data.get("jobs", {})
    found_step = False
    step_content = ""

    for job_name, job_data in jobs.items():
        steps = job_data.get("steps", [])
        for step in steps:
            if isinstance(step, dict):
                if step.get("name") == "dummy-key-leak-guard":
                    found_step = True
                    step_content = step.get("run", "")
                    break
        if found_step:
            break

    assert found_step, "dummy-key-leak-guard step not found in CI"

    # Verify the step content contains the required elements
    assert (
        "sk-ant-dummy" in step_content
    ), "step does not search for 'sk-ant-dummy'"
    assert (
        "git ls-files" in step_content
    ), "step does not use 'git ls-files'"
    assert (
        "xargs grep" in step_content or "xargs" in step_content
    ), "step does not use 'xargs grep'"
    assert (
        ".github/workflows/ci.yml" in step_content
    ), "step does not exclude CI file itself"
