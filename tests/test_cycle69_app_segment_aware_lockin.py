"""Cycle 69 AC05 — segment-aware `..` lock-in (lock-in for AC03 BACKLOG deletion).

Pins ``kb.mcp.app._validate_page_id``'s segment-aware `..` rejection at
``src/kb/mcp/app.py:291`` against a regression to substring `".." in page_id`
form (which would block legitimate filenames containing `..` substrings).

Mutation budget (Step 14 binding):
    Revert ``mcp/app.py:291`` from
        ``if any(seg == ".." for seg in page_id.replace("\\\\", "/").split("/")):``
    to
        ``if ".." in page_id:``
    Rows 1, 3, 5 of the parametrize matrix MUST FAIL under this mutation.

Per amendment A6 (cycle-65 AC9 pattern): pass ``wiki_dir=tmp_path / "wiki"``
so the test is environment-independent (does not depend on production
``WIKI_DIR`` layout).
"""

from __future__ import annotations

import pytest

from kb.mcp.app import _validate_page_id


@pytest.mark.parametrize(
    ("page_id", "expect_error"),
    [
        # Row 1 — substring trap: "notes..draft" is a single segment with `..` substring
        ("notes..draft", False),
        # Row 2 — real segment: "foo/../bar" must be rejected
        ("foo/../bar", True),
        # Row 3 — substring trap: "..bar" is NOT a `..` segment
        ("foo/..bar", False),
        # Row 4 — leading `..` segment must be rejected
        ("../foo", True),
        # Row 5 — Windows-separator handling: "foo\\..\\bar" must be rejected
        (r"foo\..\bar", True),
    ],
)
def test_validate_page_id_segment_aware_not_substring(page_id, expect_error, tmp_path):
    """AC05 lock-in: segment-aware `..` check, not substring match.

    Production guard at ``src/kb/mcp/app.py:291`` uses
    ``any(seg == ".." for seg in page_id.replace("\\\\", "/").split("/"))``
    to permit legitimate `..` substrings (rows 1, 3) while rejecting actual
    parent-directory segments (rows 2, 4, 5).
    """
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    result = _validate_page_id(page_id, check_exists=False, wiki_dir=wiki_dir)
    if expect_error:
        assert result is not None, f"Expected error for {page_id!r}, got None"
        assert "parent-directory segment" in result, (
            f"Expected 'parent-directory segment' phrasing in error, got: {result!r}"
        )
    else:
        assert result is None, (
            f"Expected None (legitimate filename with `..` substring) "
            f"for {page_id!r}, got: {result!r}"
        )
