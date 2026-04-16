"""Verify documentation stats are in sync with live repository state.

Part of Phase 4.5 CRITICAL Theme 5 (docs-sync). Prevents CLAUDE.md stats drift
and version-string disagreement across `pyproject.toml` / `src/kb/__init__.py` /
`README.md`. Run pre-push or as a CI step:

    python scripts/verify_docs.py

Exit code 0 if all checks pass, 1 if any drift detected. Tolerances documented
per check; set KB_VERIFY_STRICT=1 to treat tolerances as hard matches.

The script only REPORTS drift — it does not auto-fix. Manual reconciliation is
the intent: docs-drift fixes should trace to conscious decisions, not silent
rewrites.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STRICT = os.environ.get("KB_VERIFY_STRICT") == "1"
TEST_COUNT_TOLERANCE = 10  # allow ±10 without flagging (tests land between doc-sync PRs)


class VerifyError(Exception):
    """Single drift finding. Collected and reported at end."""


def _read_pyproject_version() -> str:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def _read_init_version() -> str:
    init_text = (PROJECT_ROOT / "src" / "kb" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_text, re.MULTILINE)
    if match is None:
        raise VerifyError("__version__ not found in src/kb/__init__.py")
    return match.group(1)


def _read_readme_badge_version() -> str | None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r"badge/version-v?([0-9]+\.[0-9]+\.[0-9]+)", readme)
    return match.group(1) if match else None


def _count_tests_collected() -> int:
    """Count pytest-collected test items. Requires .venv with pytest installed."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = result.stdout + result.stderr
    match = re.search(r"(\d+)\s+tests?\s+collected", output)
    if match is None:
        raise VerifyError(f"pytest --collect-only didn't report a count:\n{output[-500:]}")
    return int(match.group(1))


def _count_test_files() -> int:
    return sum(1 for _ in (PROJECT_ROOT / "tests").rglob("test_*.py"))


def _count_src_py_files() -> int:
    return sum(1 for _ in (PROJECT_ROOT / "src" / "kb").rglob("*.py"))


def _read_claude_md_stats() -> list[tuple[str, int, int]]:
    """Extract (context, test_count, file_count) tuples from CLAUDE.md stat lines.

    Returns an empty list if nothing matches; that signals CLAUDE.md no longer
    has the conventional "N tests across M test files" pattern and should be
    reviewed manually.
    """
    claude = (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    pattern = re.compile(r"(\d+)\s+tests\s+(?:across\s+(\d+)\s+test\s+files|,)", re.IGNORECASE)
    hits = []
    for m in pattern.finditer(claude):
        tests = int(m.group(1))
        files = int(m.group(2)) if m.group(2) else 0
        start = max(0, m.start() - 60)
        prefix = claude[start : m.start()]
        context = prefix.splitlines()[-1] if "\n" in prefix else prefix
        hits.append((context[:60], tests, files))
    return hits


def check_version_alignment(errors: list[str]) -> None:
    pyproj = _read_pyproject_version()
    init = _read_init_version()
    readme = _read_readme_badge_version()
    print(f"  pyproject.toml version = {pyproj}")
    print(f"  src/kb/__init__.py     = {init}")
    print(f"  README badge           = {readme if readme else '<not found>'}")
    if pyproj != init:
        errors.append(f"version drift: pyproject.toml={pyproj} vs __init__.py={init}")
    if readme and readme != init:
        errors.append(f"version drift: README badge={readme} vs __init__.py={init}")


def check_test_count(errors: list[str]) -> None:
    collected = _count_tests_collected()
    files = _count_test_files()
    print(f"  pytest collected tests = {collected}")
    print(f"  test file count        = {files}")
    claude_hits = _read_claude_md_stats()
    if not claude_hits:
        errors.append("CLAUDE.md has no recognizable 'N tests across M test files' line")
        return
    for context, claimed_tests, claimed_files in claude_hits:
        drift = abs(claimed_tests - collected)
        if STRICT and drift != 0:
            errors.append(
                f"CLAUDE.md claims {claimed_tests} tests; pytest collected {collected} "
                f"(strict mode, context: {context!r})"
            )
        elif drift > TEST_COUNT_TOLERANCE:
            errors.append(
                f"CLAUDE.md claims {claimed_tests} tests; pytest collected {collected} "
                f"(drift {drift} > tolerance {TEST_COUNT_TOLERANCE}, context: {context!r})"
            )
        if claimed_files and claimed_files != files:
            errors.append(
                f"CLAUDE.md claims {claimed_files} test files; actual {files} "
                f"(context: {context!r})"
            )


def check_src_py_count(errors: list[str]) -> None:
    count = _count_src_py_files()
    print(f"  src/kb/ Python files   = {count}")


def main() -> int:
    errors: list[str] = []
    print("\n== Version alignment ==")
    check_version_alignment(errors)
    print("\n== Test / file counts ==")
    check_test_count(errors)
    print("\n== Source file count ==")
    check_src_py_count(errors)
    print()
    if errors:
        print("FAIL — docs-drift detected:")
        for err in errors:
            print(f"  - {err}")
        print(f"\nFix CLAUDE.md / pyproject.toml / README and re-run. Strict mode: {STRICT}.")
        return 1
    print("OK — docs in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
