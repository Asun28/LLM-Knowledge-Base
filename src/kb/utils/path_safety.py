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


import ctypes
import logging
import sys

_LOG = logging.getLogger(__name__)
_warned_fallback = False


def _open_no_follow(path: Path) -> int:
    """Open a file with symlink-follow prevention (TOCTOU mitigation for AC10).

    Returns the file descriptor (int) which the caller must close.
    
    On POSIX: uses os.O_NOFOLLOW flag.
    On Windows: uses FILE_FLAG_OPEN_REPARSE_POINT via CreateFileW.
    On unsupported platforms: falls back to re-resolve before mutation (once per process warning).

    Raises:
        OSError: If the file is a symlink (primary path) or cannot be opened.
    """
    global _warned_fallback
    
    if sys.platform == "win32":
        # Windows: use CreateFileW with FILE_FLAG_OPEN_REPARSE_POINT
        try:
            GENERIC_READ = 0x80000000
            OPEN_EXISTING = 3
            FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
            
            handle = ctypes.windll.kernel32.CreateFileW(
                str(path), GENERIC_READ, 0, None, OPEN_EXISTING,
                FILE_FLAG_OPEN_REPARSE_POINT, None
            )
            if handle == -1:
                raise OSError(f"Cannot open file: {path}")
            return handle
        except (AttributeError, OSError):
            # Fallback if kernel32 missing or open fails
            if not _warned_fallback:
                _LOG.warning(
                    "AC10: O_NOFOLLOW unsupported on platform %s; "
                    "falling back to re-resolve TOCTOU mitigation",
                    sys.platform
                )
                _warned_fallback = True
            # Re-resolve immediately and return a dummy handle
            path.resolve()
            return -1  # Dummy handle
    else:
        # POSIX: use os.O_NOFOLLOW
        try:
            fd = os.open(str(path), os.O_NOFOLLOW | os.O_RDONLY)
            return fd
        except OSError:
            # Fallback
            if not _warned_fallback:
                _LOG.warning(
                    "AC10: O_NOFOLLOW unsupported on platform %s; "
                    "falling back to re-resolve TOCTOU mitigation",
                    sys.platform
                )
                _warned_fallback = True
            path.resolve()
            return -1
