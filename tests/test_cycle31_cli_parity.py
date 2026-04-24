"""Cycle 31 — CLI parity for page_id-input MCP tools.

Pins three new CLI subcommands (`read-page`, `affected-pages`, `lint-deep`)
against their MCP counterparts via the cycle-27/30 thin-wrapper pattern,
plus the new shared `_is_mcp_error_response` discriminator helper.

Key test patterns (per Step-5 design `2026-04-25-cycle31-design.md`):

- **Helper unit tests** (TestIsMcpErrorResponse) pin the three prefix
  shapes + first-line anchor + empty-as-success behaviour (T3, Q1, Q2).
- **Body-spy** tests patch the OWNER module (`kb.mcp.browse` /
  `kb.mcp.quality`), NOT `kb.cli`, because the wrappers use function-local
  imports that resolve at call time against the source module (Q5,
  cycle-30 L2).
- **Non-colon boundary** tests per subcommand force the runtime-error
  path of the wrapped MCP tool to verify the discriminator actually
  routes to exit 1 (Q7, cycle-24 L4 revert-tolerance).
- **Parity tests** use `CliRunner(mix_stderr=False)` and assert strict
  stream semantics: `stdout == mcp_output + "\\n"` on success,
  `stderr == mcp_output + "\\n"` + `exit_code == 1` on error (Q3).
- **AC8 retrofit** tests force the non-colon runtime-error paths in
  existing cycle 27/30 wrappers (`stats`, `reliability-map`,
  `lint-consistency`) that previously exited 0 under
  `startswith("Error:")` — tests must fail if the wrapper reverts to
  the legacy discriminator.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# AC4 — _is_mcp_error_response helper unit tests (TASK 1)
# ---------------------------------------------------------------------------


class TestIsMcpErrorResponse:
    """AC4 — shared discriminator helper.

    Classifies MCP tool string responses by FIRST-LINE prefix only against
    three shapes: `"Error:"` (colon), `"Error "` (space), `"Page not found:"`.
    Empty / blank-first-line outputs are NOT errors by design (preserves
    MCP parity for zero-length page bodies).
    """

    def test_colon_form_matches(self):
        """Validator-class errors (`Error: <reason>`)."""
        from kb.cli import _is_mcp_error_response

        assert _is_mcp_error_response("Error: invalid page_id") is True

    def test_space_form_matches(self):
        """Runtime-exception shapes (`Error <verb> ...`)."""
        from kb.cli import _is_mcp_error_response

        assert _is_mcp_error_response("Error computing affected pages: boom") is True

    def test_page_not_found_matches(self):
        """Logical-miss shape unique to kb_read_page at browse.py:125."""
        from kb.cli import _is_mcp_error_response

        assert _is_mcp_error_response("Page not found: concepts/rag") is True

    def test_empty_is_not_error(self):
        """Empty string = legitimate empty page body (browse.py:161)."""
        from kb.cli import _is_mcp_error_response

        assert _is_mcp_error_response("") is False

    def test_blank_first_line_is_not_error(self):
        """Leading newline = blank first line; body on line 2 is legit."""
        from kb.cli import _is_mcp_error_response

        assert _is_mcp_error_response("\nBody text on line 2") is False

    def test_mid_body_error_not_matched(self):
        """First-line anchor: page body with `Error:` on line 2 is legit."""
        from kb.cli import _is_mcp_error_response

        assert _is_mcp_error_response("# Real Page\nError: not first line") is False

    def test_crlf_first_line_still_matches(self):
        """CRLF line endings: `split('\\n', 1)[0]` = 'Error:\\r', still
        `.startswith('Error:')` because '\\r' is after the match."""
        from kb.cli import _is_mcp_error_response

        assert _is_mcp_error_response("Error:\r\ndetails") is True
