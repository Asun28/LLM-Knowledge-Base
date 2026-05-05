"""AC23 — validator contract consolidation regression test.

Ensures the three historical validator sites were properly migrated to
_assert_under_project_root per AC9. Uses AST-walk (NOT string grep) per
design.md Q2.9 + threat-model.md condition C8 to avoid false-positive
matches on docstrings/comments and to scan the full src/kb/ tree rather
than two hardcoded files.
"""

from __future__ import annotations

from pathlib import Path

from tests._helpers.ast_walk import find_calls_of


def _src_kb_python_files() -> list[Path]:
    return sorted(Path("src/kb").rglob("*.py"))


def test_three_historical_sites_present() -> None:
    """C8 — Assert three historical validators migrated to _assert_under_project_root.

    Uses find_calls_of (AST walk over Call nodes) instead of string grep so
    that:
      - docstrings/comments mentioning the helper do NOT count as call sites
      - the assertion runs against the full src/kb/ tree, not a hardcoded
        2-file allowlist (cycle-23 L4 same-class peer scan discipline)
      - a future revert that converts a real call back into a comment fails
        the test (revert-tolerant, cycle-7 L4 + cycle-24 L4 lessons)
    """
    files = _src_kb_python_files()
    assert files, "no src/kb/**/*.py files found; misconfigured worktree?"

    call_sites = find_calls_of(files, "_assert_under_project_root")

    # Group call sites by file for the per-file historical-site assertions.
    by_file: dict[str, int] = {}
    for path, _line in call_sites:
        # Normalise to forward-slash relative paths so the assertions read
        # the same on Windows and POSIX.
        rel = path.relative_to(Path("src/kb")).as_posix()
        by_file[rel] = by_file.get(rel, 0) + 1

    # Historical site 1+2: mcp/app.py contains both _validate_wiki_dir AND
    # the _validate_page_id containment migration; expect ≥2 calls.
    app_count = by_file.get("mcp/app.py", 0)
    assert app_count >= 2, (
        "AC9 historical sites missing from migration: mcp/app.py expected ≥2 "
        f"calls (_validate_wiki_dir + _validate_page_id), found {app_count}. "
        f"All call sites: {by_file}"
    )

    # Historical site 3: compile/compiler.py contains the
    # _validate_path_under_project_root migration; expect ≥1 call.
    compiler_count = by_file.get("compile/compiler.py", 0)
    assert compiler_count >= 1, (
        "AC9 historical site missing from migration: compile/compiler.py "
        f"expected ≥1 call (_validate_path_under_project_root), "
        f"found {compiler_count}. All call sites: {by_file}"
    )

    # Q2.9 Option B: ADDITIONAL callers are allowed. Total floor is 3 across
    # the historical sites; new callers can add to the count.
    total = sum(by_file.values())
    assert total >= 3, (
        f"AC9 total call-site floor not met: expected ≥3, found {total}. "
        f"Distribution: {by_file}"
    )
