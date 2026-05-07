"""Cycle 68 AC13 — audit_docstrings generator+raise + warn-only pins.

TDD red→green pin for ``scripts/audit_docstrings.py`` (added by AC05).

Four pins:

1. Normal function with parameters + return value MUST be flagged when
   missing ``Args:`` / ``Returns:`` sections.
2. Function with ``raise X(...)`` body MUST be flagged when missing
   ``Raises:`` section.
3. Generator function (``yield`` AND ``raise`` in body) MUST require a
   ``Raises:`` section per FW-4 (covers cycle-67 carry-over: generators
   must NOT be exempt from the raises rule).
4. ``--warn-only`` mode MUST exit 0 even when violations found.

Tests invoke the script as a subprocess against a synthetic single-file
package under tmp_path; stdout is parsed as JSON (auditor convention).
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "audit_docstrings.py"


def _run_audit_against_temp_pkg(
    tmp_path: Path, pkg_source: str, *, warn_only: bool = True
) -> subprocess.CompletedProcess:
    """Run scripts/audit_docstrings.py against a synthetic single-file package.

    Args:
        tmp_path: Per-test pytest tmp_path.
        pkg_source: Python source written to the synthetic ``__init__.py``.
        warn_only: Whether to pass ``--warn-only`` (cycle-68 transition mode).

    Returns:
        CompletedProcess with captured stdout/stderr; never raises.
    """
    pkg_dir = tmp_path / "fakepkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(pkg_source, encoding="utf-8")
    args = [sys.executable, str(SCRIPT_PATH), "--paths", str(pkg_dir)]
    if warn_only:
        args.append("--warn-only")
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(PROJECT_ROOT),
    )


def _audit_findings(stdout: str) -> list[dict]:
    """Parse audit JSON output; tolerate {findings: [...]} or bare list."""
    text = stdout.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict) and "findings" in parsed:
        return list(parsed["findings"])
    return []


def test_audit_docstrings_normal_func_with_args_returns(tmp_path: Path) -> None:
    """AC13 — function with parameters + return MUST be flagged for missing Args:/Returns:."""
    pkg_source = textwrap.dedent(
        '''
        def add(a: int, b: int) -> int:
            """Add two ints."""
            return a + b
        '''
    ).strip()
    result = _run_audit_against_temp_pkg(tmp_path, pkg_source)
    findings = _audit_findings(result.stdout)
    flagged = [f for f in findings if f.get("name") == "add"]
    assert flagged, (
        f"Expected 'add' to be flagged for missing Args:/Returns:; got findings={findings!r} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    sections = flagged[0].get("missing", [])
    assert "Args" in sections or "args" in sections, (
        f"Expected Args missing, got {flagged[0]!r}"
    )
    assert "Returns" in sections or "returns" in sections, (
        f"Expected Returns missing, got {flagged[0]!r}"
    )


def test_audit_docstrings_func_with_raise_requires_raises_section(tmp_path: Path) -> None:
    """AC13 — function with raise in body MUST require Raises: section."""
    pkg_source = textwrap.dedent(
        '''
        def validate(x):
            """Validate x.

            Args:
                x: Value to validate.

            Returns:
                Validated value.
            """
            if x is None:
                raise ValueError("x cannot be None")
            return x
        '''
    ).strip()
    result = _run_audit_against_temp_pkg(tmp_path, pkg_source)
    findings = _audit_findings(result.stdout)
    flagged = [f for f in findings if f.get("name") == "validate"]
    assert flagged, (
        f"Expected 'validate' to be flagged for missing Raises:; got findings={findings!r} "
        f"stdout={result.stdout!r}"
    )
    sections = flagged[0].get("missing", [])
    assert "Raises" in sections or "raises" in sections, (
        f"Expected Raises missing, got {flagged[0]!r}"
    )


def test_audit_docstrings_generator_with_yield_and_raise(tmp_path: Path) -> None:
    """AC13 / FW-4 — generator (yield AND raise) MUST require Raises: section."""
    pkg_source = textwrap.dedent(
        '''
        def stream(values):
            """Stream values.

            Args:
                values: Iterable to stream.

            Yields:
                Each non-None value.
            """
            for v in values:
                if v is None:
                    raise ValueError("None encountered")
                yield v
        '''
    ).strip()
    result = _run_audit_against_temp_pkg(tmp_path, pkg_source)
    findings = _audit_findings(result.stdout)
    flagged = [f for f in findings if f.get("name") == "stream"]
    assert flagged, (
        f"FW-4: generator with raise MUST be flagged for missing Raises:; got "
        f"findings={findings!r} stdout={result.stdout!r}"
    )
    sections = flagged[0].get("missing", [])
    assert "Raises" in sections or "raises" in sections, (
        f"FW-4 violation — generator missed Raises check; got {flagged[0]!r}"
    )


def test_audit_docstrings_warn_only_exit_zero(tmp_path: Path) -> None:
    """AC13 — --warn-only exits 0 even when violations exist."""
    pkg_source = textwrap.dedent(
        '''
        def bad():
            pass
        '''
    ).strip()
    result = _run_audit_against_temp_pkg(tmp_path, pkg_source, warn_only=True)
    assert result.returncode == 0, (
        f"--warn-only must exit 0 even with violations; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


@pytest.mark.timeout(120)
def test_audit_docstrings_warn_only_against_real_repo() -> None:
    """AC13 / AC06 integration — script runs warn-only against real repo and exits 0."""
    if not SCRIPT_PATH.exists():
        pytest.skip("scripts/audit_docstrings.py not yet created (AC05 pending)")
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--warn-only"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, (
        f"warn-only should exit 0 (transition mode); got {result.returncode}, "
        f"stderr={result.stderr[-1000:]!r}"
    )
