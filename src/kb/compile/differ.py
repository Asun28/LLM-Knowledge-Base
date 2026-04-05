"""Diff-based wiki updates — propose changes, not full rewrites."""

import difflib
from pathlib import Path


def compute_diff(old_content: str, new_content: str, filename: str = "") -> str:
    """Compute a unified diff between old and new content.

    Args:
        old_content: The existing page content.
        new_content: The proposed new content.
        filename: Optional filename for diff header.

    Returns:
        Unified diff string, empty if no changes.
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filename}" if filename else "a/old",
        tofile=f"b/{filename}" if filename else "b/new",
        lineterm="",
    )
    return "".join(diff)


def apply_diff(page_path: Path, new_content: str, dry_run: bool = False) -> dict:
    """Apply changes to a wiki page, producing a diff for review.

    Args:
        page_path: Path to the wiki page.
        new_content: The proposed new content.
        dry_run: If True, only produce the diff without writing.

    Returns:
        dict with keys: path, changed (bool), diff (str), applied (bool).
    """
    if page_path.exists():
        old_content = page_path.read_text(encoding="utf-8")
    else:
        old_content = ""

    diff = compute_diff(old_content, new_content, page_path.name)
    changed = bool(diff)

    if changed and not dry_run:
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(new_content, encoding="utf-8")

    return {
        "path": str(page_path),
        "changed": changed,
        "diff": diff,
        "applied": changed and not dry_run,
    }
