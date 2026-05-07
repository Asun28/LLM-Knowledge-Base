"""Cycle 68 AC15a — pyproject.toml httpx pin drift regression (FW-8).

Locks AC09's tightened constraint ``httpx>=0.28,<0.29`` against a future
unpinned regression (Phase 4.5 HIGH "httpx constraint mismatch" item). The
runtime assertion at ``src/kb/lint/fetcher.py:51-59`` raises ``RuntimeError``
if installed httpx is not 0.28.x; without an explicit pyproject ceiling, an
install can silently land on 0.27.x or 0.29.x and crash at first import.

Per cycle-22 L4, the second test probes that the constraint is
resolver-compatible via ``pip install --dry-run`` (FW-8 from cycle-67
design carryover).
"""

import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_httpx_pin_has_explicit_ceiling():
    """AC15a-1 — pyproject.toml httpx constraint matches lint/fetcher.py:51 runtime guard.

    The runtime assertion at ``src/kb/lint/fetcher.py:51-59`` raises
    ``RuntimeError`` if installed httpx is not 0.28.x. Without an explicit
    pyproject ceiling, an install can silently land on 0.27.x or 0.29.x.
    """
    pyproject_text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    data = tomllib.loads(pyproject_text)
    # httpx lives in the `augment` optional-dependencies extra (not main deps);
    # cycle-68 BACKLOG entry pinned location at pyproject.toml:29.
    augment = data.get("project", {}).get("optional-dependencies", {}).get("augment", [])
    httpx_constraint = next(
        (d for d in augment if d.startswith("httpx") and "pytest" not in d),
        None,
    )
    assert httpx_constraint is not None, (
        "httpx not in pyproject.toml [project.optional-dependencies].augment"
    )
    assert ">=0.28" in httpx_constraint, (
        f"httpx constraint missing >=0.28 floor: {httpx_constraint!r}"
    )
    assert "<0.29" in httpx_constraint, (
        f"httpx constraint missing <0.29 ceiling: {httpx_constraint!r}"
    )


def test_pyproject_httpx_resolver_compat_dry_run():
    """AC15a-2 / FW-8 — pip can resolve the project's [augment] extra (httpx + sibs).

    Detects transitive-dep conflicts (anthropic/openai/fastmcp/langchain-*
    pinning httpx outside our range). Cost ~30 sec per CI run; acceptable
    for a per-cycle drift check.

    Cycle 68 R2 Codex M4 closed: previous version ran ``pip install --dry-run
    httpx>=0.28,<0.29`` in ISOLATION, which only verified the constraint
    string was satisfiable. It did NOT exercise the project's extras
    section, so a future move of httpx out of [augment] (or a sibling
    constraint conflict introduced by another extras package) would slip
    past silently. We now read the full [augment] list from pyproject.toml
    and dry-run pip against it, mirroring how ``pip install -e .[augment]``
    would resolve at install time.
    """
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    augment_specs = pyproject["project"]["optional-dependencies"]["augment"]
    # Filter test-time extras (pytest plugins) — leave the runtime libs that
    # actually constrain httpx.
    runtime_specs = [s for s in augment_specs if "pytest" not in s.lower()]
    assert "httpx>=0.28,<0.29" in runtime_specs, (
        f"AC09 pin drift — augment extra no longer contains 'httpx>=0.28,<0.29'; "
        f"got {runtime_specs!r}"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--dry-run", "--quiet", *runtime_specs],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        f"pip dry-run could not resolve [augment] extras (extras-aware FW-8 check):\n"
        f"specs: {runtime_specs!r}\nstderr: {result.stderr[:800]}\nstdout: {result.stdout[:800]}"
    )
