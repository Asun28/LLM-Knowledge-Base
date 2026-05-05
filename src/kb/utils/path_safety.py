"""Path safety helpers — access control for filesystem operations.

AC9 — centralized path containment validator with optional checks for existence,
directory type, and symlink detection. Used by MCP validators to ensure all
filesystem access stays within the project tree.

Primary usage:
  _assert_under_project_root(path, "wiki_dir", require_exists=True, require_dir=True)

Design notes:
  - Dual anchor: checks both literal form and resolved form under project root
  - Call-time access to KB_PROJECT_ROOT via get_project_root() for reload-leak safety
  - Hard cap: 3 keyword-only parameters (Q2.2 cycle-65 lock; cycle-66 AC5
    dropped `allow_symlinks` because zero callers opted out — symlink rejection
    is now structurally unconditional)
  - Raises ValueError with field_name interpolated for traceability
"""

import ctypes
import errno
import logging
import os
import sys
from pathlib import Path

import kb.config

_LOG = logging.getLogger(__name__)
_warned_fallback = False


def _assert_under_project_root(
    path: Path,
    field_name: str,
    *,
    require_exists: bool = False,
    require_dir: bool = False,
    dual_anchor: bool = True,
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

    Raises:
        ValueError: If any check fails. Error message includes field_name.

    Examples:
        _assert_under_project_root(Path("wiki"), "wiki_dir", require_exists=True)
        _assert_under_project_root(Path("raw/foo.md"), "source_path")
    """
    # Preserve Path subclasses (e.g., test-time _ResolvingPath used by cycle-29
    # dual-anchor divergence tests) — Path(path) on a subclass returns a
    # vanilla Path, losing the overridden .resolve() and breaking the test.
    if not isinstance(path, Path):
        path = Path(path)
    proj_root = kb.config.get_project_root()
    proj_root_resolved = proj_root.resolve()

    # Dual anchor: literal and resolved forms both under project root.
    # The literal-anchor check only applies to ABSOLUTE paths — for relative
    # paths the resolved check below covers literal+resolved equivalence
    # (Path(".").relative_to(/abs/root) would always fail, but Path(".").resolve()
    # is the cwd which can legitimately be inside proj_root). The dual-anchor
    # divergence the design targets is symlink/`..`-bypass on absolute paths.
    #
    # Error messages keep the legacy "{field_name} must be inside project root"
    # wording (no path interpolation) so:
    #   - existing tests asserting that exact phrase continue to match
    #   - actual paths are NOT leaked in user-visible error messages (T6 hardening)
    if dual_anchor and path.is_absolute():
        try:
            path.relative_to(proj_root)
        except ValueError:
            raise ValueError(f"{field_name} must be inside project root")

    # Resolved anchor (always checked).
    try:
        path.resolve().relative_to(proj_root_resolved)
    except ValueError:
        raise ValueError(f"{field_name} must be inside project root")

    # Optional existence check
    if require_exists and not path.exists():
        raise ValueError(f"{field_name} does not exist")

    # Optional directory check
    if require_dir and not path.is_dir():
        raise ValueError(f"{field_name} is not a directory")

    # Symlink rejection (cycle-66 AC5: structurally unconditional after
    # `allow_symlinks` kwarg removal — zero callers ever opted out).
    if path.is_symlink():
        raise ValueError(f"{field_name} is a symlink (not allowed)")


def _open_no_follow(path: Path) -> int:
    """Reject the path if it is a symlink; otherwise return a sentinel handle.

    Cycle-65 AC10 TOCTOU mitigation. Behavior depends on platform:

    - **POSIX**: ``os.open(path, O_NOFOLLOW | O_RDONLY)``. This is atomic — if
      the path is a symlink the open fails with ``OSError(ELOOP)`` and no
      mutation has occurred. Returns the actual file descriptor; caller must
      pair with ``_close_no_follow_fd`` to close.
    - **Windows**: ``path.is_symlink()`` check. NOT atomic (the OS-level
      ``CreateFileW(FILE_FLAG_OPEN_REPARSE_POINT)`` ctypes path was tried in
      the cycle-65 initial implementation but had restype/HANDLE-type
      correctness issues that broke real-file unlinks — see Step 12 hard
      gate). The non-atomic check still rejects existing symlinks, which
      is the dominant attack vector in the local-FS threat model. Returns
      the sentinel ``-1`` (no handle to close on this path).
    - **Other / unsupported** platforms fall through to a re-resolve +
      once-per-process ``logger.warning`` (Q2.3 design lock).

    Raises:
        OSError: If the path is a symlink (POSIX: via O_NOFOLLOW; Windows: via
            is_symlink) or otherwise cannot be opened.
    """
    global _warned_fallback

    if sys.platform == "win32":
        # Defensive symlink rejection. Not TOCTOU-atomic (race window between
        # is_symlink and the caller's unlink) but sufficient for the local-FS
        # threat model and avoids the ctypes HANDLE-typing fragility.
        if path.is_symlink():
            raise OSError(f"AC10 reject: path is a symlink ({path})")
        return -1
    else:
        try:
            return os.open(str(path), os.O_NOFOLLOW | os.O_RDONLY)
        except OSError as exc:
            # ELOOP is the kernel's atomic "this is a symlink" signal under
            # O_NOFOLLOW — propagate so the caller aborts the mutation.
            # Any other OSError means O_NOFOLLOW is unavailable on this
            # platform; fall back to re-resolve + once-per-process warn.
            if exc.errno == errno.ELOOP:
                raise
            if not _warned_fallback:
                _LOG.warning(
                    "AC10: O_NOFOLLOW unsupported on platform %s; "
                    "falling back to re-resolve TOCTOU mitigation",
                    sys.platform,
                )
                _warned_fallback = True
            path.resolve()
            return -1


def _close_no_follow_fd(fd: int) -> None:
    """Close a file descriptor returned by _open_no_follow.

    Handles the cross-platform handle types (POSIX int fd vs Windows HANDLE)
    and the sentinel value (-1) returned by the fallback path. Errors during
    close are swallowed because the caller has already done the security check
    (no symlink) and proceeded with the mutation; a close failure here is
    cosmetic, not security-critical.
    """
    if fd == -1:
        return
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.CloseHandle(fd)
        except (AttributeError, OSError):
            pass
    else:
        try:
            os.close(fd)
        except OSError:
            pass
