"""Test that dependency pinning is correctly applied (AC11)."""

from pathlib import Path


def test_gitpython_has_floor_and_ceiling():
    """Assert GitPython has both floor (>=3.1.47) and ceiling (<3.2) in requirements.txt."""
    requirements_path = Path("requirements.txt")
    content = requirements_path.read_text(encoding="utf-8")

    # Find the GitPython line
    gitpython_line = None
    for line in content.splitlines():
        if line.startswith("GitPython"):
            gitpython_line = line
            break

    assert gitpython_line is not None, "GitPython not found in requirements.txt"

    # Check for both floor and ceiling
    assert ">=3.1.47" in gitpython_line, f"Floor version >=3.1.47 not found in: {gitpython_line}"
    assert "<3.2" in gitpython_line, f"Ceiling version <3.2 not found in: {gitpython_line}"
