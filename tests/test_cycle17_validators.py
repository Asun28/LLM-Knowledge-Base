"""Cycle 17 AC11-13 — shared `_validate_run_id` contract.

The validator protects `lint/augment.py::run_augment(resume=...)` against
path-traversal via `Path.glob`. Cycle 17 design decision Q8 enforces an
EXACT 8 hex-char match (not a prefix), so the glob pattern has no wildcard
segment attacker-controlled.
"""

from __future__ import annotations

import pytest

from kb.mcp.app import _validate_run_id


class TestValidateRunId:
    """T1 (cycle 17) — shared validator contract."""

    def test_empty_string_is_sentinel_for_no_resume(self) -> None:
        assert _validate_run_id("") is None

    def test_valid_8_hex_chars(self) -> None:
        assert _validate_run_id("abc12345") is None
        assert _validate_run_id("00000000") is None
        assert _validate_run_id("ffffffff") is None
        assert _validate_run_id("deadbeef") is None

    @pytest.mark.parametrize(
        "bad_input",
        [
            "../etc",  # traversal
            "../../secret",  # deep traversal
            "abc",  # too short (3 chars)
            "abc1234",  # too short (7 chars)
            "abcdef012",  # too long (9 chars)
            "abcdef0123",  # too long (10 chars)
            "ABCD1234",  # uppercase not allowed
            "abcdefgh",  # non-hex (g, h)
            "abc1234*",  # glob metachar
            "abc1234?",  # glob metachar
            "abc12[34",  # glob metachar
            "abc/1234",  # slash
            "abc\\1234",  # backslash
            "abc 1234",  # whitespace
            "abc-1234",  # hyphen (not hex)
            "abc.1234",  # dot (not hex)
            "  abc12345  ",  # leading/trailing whitespace with otherwise-valid hex
            "abc12345\n",  # trailing newline
            "\x00abc12345",  # null byte
        ],
    )
    def test_rejects_invalid(self, bad_input: str) -> None:
        result = _validate_run_id(bad_input)
        assert result is not None, f"Expected rejection for {bad_input!r}"
        assert "Invalid resume id" in result

    def test_rejection_message_quotes_input(self) -> None:
        """Error message should include the offending value for operator visibility."""
        result = _validate_run_id("../etc")
        assert result is not None
        assert "'../etc'" in result or '"../etc"' in result or "../etc" in result

    def test_rejection_message_hints_format(self) -> None:
        """Error message should state the expected format."""
        result = _validate_run_id("bad")
        assert result is not None
        assert "8 hex" in result or "0-9a-f" in result
