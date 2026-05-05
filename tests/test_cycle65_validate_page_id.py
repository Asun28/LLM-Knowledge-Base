"""AC6 + AC7 + AC8 tests for _validate_page_id Windows + segment-aware checks."""

import pytest

from kb.mcp.app import _validate_page_id


class TestAC6TrailingDotSpace:
    """AC6 — Trailing dot or space rejection in path segments."""

    @pytest.mark.parametrize(
        "invalid_page_id",
        [
            "foo.",  # trailing dot
            "foo ",  # trailing space
            "path/foo./bar",  # trailing dot in middle segment
            "path/foo /bar",  # trailing space in middle segment
        ],
    )
    def test_ac6_rejects_trailing_dot_or_space(self, invalid_page_id: str) -> None:
        """AC6 — page_id with trailing dot/space in any segment should be rejected."""
        result = _validate_page_id(invalid_page_id, check_exists=False)
        assert result is not None, f"Expected rejection for {invalid_page_id!r}"
        assert "trailing dot or space" in result.lower()


class TestAC7WindowsIllegalChars:
    """AC7 — Windows illegal characters rejection."""

    @pytest.mark.parametrize(
        "invalid_page_id",
        [
            "foo:bar",  # colon
            "foo<bar",  # less-than
            "foo>bar",  # greater-than
            'foo"bar',  # quote
            "foo|bar",  # pipe
            "foo?bar",  # question mark
            "foo*bar",  # asterisk
        ],
    )
    def test_ac7_rejects_windows_illegal_chars(self, invalid_page_id: str) -> None:
        """AC7 — page_id with Windows illegal chars should be rejected."""
        result = _validate_page_id(invalid_page_id, check_exists=False)
        assert result is not None, f"Expected rejection for {invalid_page_id!r}"
        assert "windows-illegal" in result.lower()


class TestAC8SegmentAwareDotDot:
    """AC8 — Segment-aware parent-directory match."""

    def test_ac8_literal_dotdot_filename_accepted(self) -> None:
        """AC8 — page_id 'notes..draft' (literal double-dot filename) should be ACCEPTED."""
        # This is a legitimate filename with double dots, not a parent-dir escape
        result = _validate_page_id("notes..draft", check_exists=False)
        # Either None (valid) or a different error (e.g., path-escapes if we try to resolve)
        # For our test, we just verify it doesn't reject due to segment ".." check
        if result is not None:
            assert "parent-directory" not in result.lower(), (
                f"Should not reject literal 'notes..draft' as parent-directory: {result}"
            )

    def test_ac8_segment_dotdot_rejected(self) -> None:
        """AC8 — page_id 'foo/../bar' (segment-level ..) should be REJECTED."""
        result = _validate_page_id("foo/../bar", check_exists=False)
        assert result is not None, "Expected rejection for path with parent-directory segment"
        assert "parent-directory" in result.lower()

    def test_ac8_dotdot_only_rejected(self) -> None:
        """AC8 — page_id '..' (just parent-directory segment) should be REJECTED."""
        result = _validate_page_id("..", check_exists=False)
        assert result is not None, "Expected rejection for '..' alone"
        assert "parent-directory" in result.lower()
