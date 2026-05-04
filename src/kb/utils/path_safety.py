"""Path safety helpers — access control for filesystem operations.

AC9 — centralized path containment validator with optional checks for existence,
directory type, and symlink detection. Used by MCP validators to ensure all
filesystem access stays within the project tree.

Primary usage:
  _assert_under_project_root(path, "wiki_dir", require_exists=True, require_dir=True)

Design notes:
  - Dual anchor: checks both literal form and resolved form under project root
  - Call-time access to KB_PROJECT_ROOT via get_project_root() for reload-leak safety
  - Hard cap: 4 keyword-only parameters (Q2.2 design lock)
  - Raises ValueError with field_name interpolated for traceability
"""

import os
from pathlib import Path

import kb.config


def _assert_under_project_root(
    path: Path,
    field_name: str,
    *,
    require_exists: bool = False,
    require_dir: bool = False,
    dual_anchor: bool = True,
    allow_symlinks: bool = False,
) -> None:
    """Assert that a path is contained within the project root.

    Dual-anchor validation: checks both literal form and resolved form are under
    the project root (per cycle-65 Q2.2 design lock).

    Args:
        path: The path to validate (may be relative or absolute).
        field_name: Name of the field (for error messages).
        require_exists: If True, raise if the path does not exist.
        require_dir: If True, raise if the path is not a directory.
        dual_anchor: If True (default), check both literal and resolved forms.
        allow_symlinks: If False (default), raise if the path is a symlink.

    Raises:
        ValueError: If any check fails. Error message includes field_name.

    Examples:
        _assert_under_project_root(Path("wiki"), "wiki_dir", require_exists=True)
        _assert_under_project_root(Path("raw/foo.md"), "source_path")
    """
    path = Path(path)
    proj_root = kb.config.get_project_root()
    proj_root_resolved = proj_root.resolve()

    # Dual anchor: literal and resolved forms both under project root
    if dual_anchor:
        try:
            path.relative_to(proj_root)
        except ValueError:
            raise ValueError(
                f"{field_name} escapes project root (literal form): {path} "
                f"not under {proj_root}"
            )

    # Resolved anchor (always checked)
    try:
        path.resolve().relative_to(proj_root_resolved)
    except ValueError:
        raise ValueError(
            f"{field_name} escapes project root (resolved form): {path.resolve()} "
            f"not under {proj_root_resolved}"
        )

    # Optional existence check
    if require_exists and not path.exists():
        raise ValueError(f"{field_name} does not exist: {path}")

    # Optional directory check
    if require_dir and not path.is_dir():
        raise ValueError(f"{field_name} is not a directory: {path}")

    # Optional symlink rejection
    if not allow_symlinks and path.is_symlink():
        raise ValueError(f"{field_name} is a symlink (not allowed): {path}")
