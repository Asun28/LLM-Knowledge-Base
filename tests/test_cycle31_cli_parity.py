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
- **Parity tests** use `CliRunner()` (Click 8.3+ splits stdout/stderr by
  default; the `mix_stderr` kwarg was removed in Click 8.2) and assert
  strict stream semantics: `stdout == mcp_output + "\\n"` on success,
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


# ---------------------------------------------------------------------------
# AC1 — `kb read-page` (TASK 2)
# ---------------------------------------------------------------------------


class TestReadPageCli:
    """AC1 — CLI parity for MCP `kb_read_page`."""

    def test_read_page_help_exits_zero(self):
        """`kb read-page --help` exits 0 and shows the positional arg."""
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["read-page", "--help"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert "PAGE_ID" in result.output
        assert "Read a wiki page" in result.output

    def test_read_page_body_executes_forwards_page_id(self, monkeypatch):
        """Body spy — CLI forwards `page_id` kwarg RAW to `kb_read_page`.

        Patch the OWNER module (`kb.mcp.browse`) per cycle-30 L2: the
        function-local import in `read_page` resolves against that module
        at call time; patching `kb.cli` would re-bind an attribute that
        is never read.
        """
        from click.testing import CliRunner

        from kb.cli import cli
        from kb.mcp import browse as browse_mod

        called = {"value": False, "page_id": None}

        def _spy(page_id):
            called["value"] = True
            called["page_id"] = page_id
            return "# Fake Page\nBody."

        monkeypatch.setattr(browse_mod, "kb_read_page", _spy)

        runner = CliRunner()
        result = runner.invoke(cli, ["read-page", "concepts/rag"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert called["value"] is True
        assert called["page_id"] == "concepts/rag"
        assert "# Fake Page" in result.output

    def test_read_page_traversal_exits_non_zero(self):
        """AC6a — ``..`` path-traversal hits `_validate_page_id`'s colon-form
        rejection at `src/kb/mcp/app.py`. No monkeypatch — pins the real
        validator contract end-to-end."""
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["read-page", "../etc/passwd"])
        assert result.exit_code != 0
        assert "Error:" in result.output
        assert "Invalid page_id" in result.output

    def test_read_page_trailing_newline_rejected(self):
        """T4/Q6 — `kb_read_page` calls `_validate_page_id` DIRECTLY (no
        `_strip_control_chars` pre-pass); `_CTRL_CHARS_RE` at
        `src/kb/mcp/app.py:188` rejects `\\n`. CLI forwards verbatim."""
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["read-page", "concepts/rag\n"])
        assert result.exit_code != 0
        assert "Error:" in result.output
        assert "control characters" in result.output

    def test_read_page_missing_exits_non_zero_with_page_not_found(self):
        """AC6b — nonexistent page hits `"Page not found:"` at
        `src/kb/mcp/browse.py:125` (no ``"Error"`` prefix at all).
        Revert-divergent: under legacy `startswith("Error:")` discriminator
        this test FAILS with exit 0 + the text on stdout.

        R1 Sonnet MAJOR — assert on `result.stderr` explicitly so the test
        flips not just on exit-code regression but also on a hypothetical
        future bug that routes the error to stdout with exit 1."""
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        # Use a syntactically-valid page_id that passes the validator
        # with `check_exists=False` but resolves to no file on disk.
        result = runner.invoke(cli, ["read-page", "concepts/does-not-exist-cycle31-probe"])
        assert result.exit_code != 0
        assert "Page not found:" in result.stderr
        assert result.stdout == ""


# ---------------------------------------------------------------------------
# AC2 — `kb affected-pages` (TASK 2)
# ---------------------------------------------------------------------------


class TestAffectedPagesCli:
    """AC2 — CLI parity for MCP `kb_affected_pages`."""

    def test_affected_pages_help_exits_zero(self):
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["affected-pages", "--help"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert "PAGE_ID" in result.output

    def test_affected_pages_body_executes_forwards_page_id(self, monkeypatch):
        """Body spy — patch `kb.mcp.quality` owner module."""
        from click.testing import CliRunner

        from kb.cli import cli
        from kb.mcp import quality as quality_mod

        called = {"value": False, "page_id": None}

        def _spy(page_id):
            called["value"] = True
            called["page_id"] = page_id
            return "# Pages Affected by Changes to concepts/rag\n- concepts/llm"

        monkeypatch.setattr(quality_mod, "kb_affected_pages", _spy)

        runner = CliRunner()
        result = runner.invoke(cli, ["affected-pages", "concepts/rag"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert called["value"] is True
        assert called["page_id"] == "concepts/rag"
        assert "Pages Affected" in result.output

    def test_affected_pages_traversal_exits_non_zero(self):
        """AC6a — ``..`` traversal hits validator at MCP boundary."""
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["affected-pages", "../etc/passwd"])
        assert result.exit_code != 0
        assert "Error:" in result.output
        assert "Invalid page_id" in result.output

    def test_affected_pages_trailing_newline_stripped_then_validated(self):
        """T4/Q6 — `kb_affected_pages` calls `_strip_control_chars` BEFORE
        validation (quality.py:275); trailing `\\n` is stripped, not
        rejected. Result depends on post-strip page existence."""
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["affected-pages", "concepts/nonexistent-cycle31\n"])
        # Stripped → `concepts/nonexistent-cycle31` → validator rejects on
        # non-existence (check_exists=True). NOT a control-chars error.
        assert "control characters" not in result.output, (
            "affected-pages must strip (not reject) control chars per MCP contract"
        )

    def test_affected_pages_runtime_exception_exits_non_zero_non_colon_form(
        self, monkeypatch, tmp_path
    ):
        """AC6b — force a runtime exception inside `kb_affected_pages` so
        the MCP tool's except clause emits the non-colon
        ``"Error computing affected pages: ..."`` form at
        `src/kb/mcp/quality.py:290`. Revert-divergent: under legacy
        `startswith("Error:")` discriminator this test FAILS with exit 0."""
        from click.testing import CliRunner

        # Seed a minimal wiki containing the probe page so validator's
        # check_exists=True passes, reaching the build_backlinks call.
        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        page = wiki_dir / "concepts" / "probe-cycle31.md"
        page.write_text(
            "---\ntitle: Probe\nsource:\n  - raw/x.md\n---\n\nBody.",
            encoding="utf-8",
        )
        monkeypatch.setattr("kb.mcp.quality.WIKI_DIR", wiki_dir)
        monkeypatch.setattr("kb.mcp.app.WIKI_DIR", wiki_dir)

        # Force the helper BELOW the MCP tool to raise → MCP's except clause
        # emits the non-colon error shape.
        def _boom():
            raise RuntimeError("forced")

        monkeypatch.setattr("kb.compile.linker.build_backlinks", _boom)

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["affected-pages", "concepts/probe-cycle31"])
        assert result.exit_code != 0, f"output: {result.output!r}"
        assert "Error computing affected pages" in result.output


# ---------------------------------------------------------------------------
# AC3 — `kb lint-deep` (TASK 2)
# ---------------------------------------------------------------------------


class TestLintDeepCli:
    """AC3 — CLI parity for MCP `kb_lint_deep`."""

    def test_lint_deep_help_exits_zero(self):
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["lint-deep", "--help"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert "PAGE_ID" in result.output

    def test_lint_deep_body_executes_forwards_page_id(self, monkeypatch):
        """Body spy — patch `kb.mcp.quality` owner module."""
        from click.testing import CliRunner

        from kb.cli import cli
        from kb.mcp import quality as quality_mod

        called = {"value": False, "page_id": None}

        def _spy(page_id):
            called["value"] = True
            called["page_id"] = page_id
            return "## Page: concepts/rag\n## Sources\n..."

        monkeypatch.setattr(quality_mod, "kb_lint_deep", _spy)

        runner = CliRunner()
        result = runner.invoke(cli, ["lint-deep", "concepts/rag"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert called["value"] is True
        assert called["page_id"] == "concepts/rag"
        assert "Page: concepts/rag" in result.output

    def test_lint_deep_traversal_exits_non_zero(self):
        """AC6a — ``..`` traversal hits validator at MCP boundary."""
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["lint-deep", "../etc/passwd"])
        assert result.exit_code != 0
        assert "Error:" in result.output
        assert "Invalid page_id" in result.output

    def test_lint_deep_trailing_newline_stripped_then_validated(self):
        """T4/Q6 — `kb_lint_deep` calls `_strip_control_chars` BEFORE
        validation (quality.py:139); trailing `\\n` stripped, not rejected."""
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["lint-deep", "concepts/nonexistent-cycle31\n"])
        assert "control characters" not in result.output, (
            "lint-deep must strip (not reject) control chars per MCP contract"
        )

    def test_lint_deep_file_not_found_exits_non_zero_non_colon_form(self, monkeypatch, tmp_path):
        """AC6b — force `build_fidelity_context` to raise `FileNotFoundError`
        so `kb_lint_deep` emits the non-colon
        ``"Error checking fidelity for <id>: ..."`` at
        `src/kb/mcp/quality.py:149,152`. Revert-divergent."""
        from click.testing import CliRunner

        # Seed a minimal wiki with the probe page so the validator passes.
        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        page = wiki_dir / "concepts" / "probe-cycle31.md"
        page.write_text(
            "---\ntitle: Probe\nsource:\n  - raw/x.md\n---\n\nBody.",
            encoding="utf-8",
        )
        monkeypatch.setattr("kb.mcp.quality.WIKI_DIR", wiki_dir)
        monkeypatch.setattr("kb.mcp.app.WIKI_DIR", wiki_dir)

        def _boom(page_id):
            raise FileNotFoundError("/raw/missing-source.md")

        monkeypatch.setattr("kb.lint.semantic.build_fidelity_context", _boom)

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["lint-deep", "concepts/probe-cycle31"])
        assert result.exit_code != 0, f"output: {result.output!r}"
        assert "Error checking fidelity for" in result.output


# ---------------------------------------------------------------------------
# Q3 parity — direct MCP call vs CLI invocation (TASK 4)
# ---------------------------------------------------------------------------


class TestParityCliMcp:
    """Q3 — CLI is a pure projection of MCP.

    Each test (a) calls the real MCP tool directly to capture
    ``mcp_output``, (b) invokes the CLI with the same input, (c) asserts
    strict stream semantics:
      success → ``stdout == mcp_output + "\\n"``; ``stderr == ""``; exit 0.
      error   → ``stderr == mcp_output + "\\n"``; ``stdout == ""``; exit 1.
    Uses ``CliRunner(mix_stderr=False)`` (Click 8.x) so stdout and stderr
    are separately inspectable.

    Parallel-assertion shape across all 6 tests per cycle-30 L3.
    """

    # ----- read-page -----

    def test_read_page_parity_success(self, tmp_path, monkeypatch):
        """Seed a known page in tmp wiki; direct MCP call + CLI return the
        same string. CLI adds a trailing ``\\n`` via ``click.echo``."""
        from click.testing import CliRunner

        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        page = wiki_dir / "concepts" / "parity-probe.md"
        page.write_text("---\ntitle: Parity Probe\n---\n\nBody content.\n", encoding="utf-8")
        monkeypatch.setattr("kb.mcp.browse.WIKI_DIR", wiki_dir)
        monkeypatch.setattr("kb.mcp.app.WIKI_DIR", wiki_dir)

        from kb.cli import _is_mcp_error_response
        from kb.mcp.browse import kb_read_page

        mcp_output = kb_read_page("concepts/parity-probe")
        assert not _is_mcp_error_response(mcp_output), (
            f"precondition failed — mcp_output: {mcp_output!r}"
        )

        from kb.cli import cli

        runner = CliRunner()  # Click 8.3+ splits stdout/stderr by default
        result = runner.invoke(cli, ["read-page", "concepts/parity-probe"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert result.stdout == mcp_output + "\n"
        assert result.stderr == ""

    def test_read_page_parity_error(self, tmp_path, monkeypatch):
        """Nonexistent page_id → both channels return identical
        ``"Page not found: <id>"``. CLI routes to stderr + exit 1."""
        from click.testing import CliRunner

        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        monkeypatch.setattr("kb.mcp.browse.WIKI_DIR", wiki_dir)
        monkeypatch.setattr("kb.mcp.app.WIKI_DIR", wiki_dir)

        from kb.cli import _is_mcp_error_response
        from kb.mcp.browse import kb_read_page

        page_id = "concepts/does-not-exist-parity-probe"
        mcp_output = kb_read_page(page_id)
        assert _is_mcp_error_response(mcp_output), (
            f"precondition failed — mcp_output: {mcp_output!r}"
        )
        assert "Page not found:" in mcp_output

        from kb.cli import cli

        runner = CliRunner()  # Click 8.3+ splits stdout/stderr by default
        result = runner.invoke(cli, ["read-page", page_id])
        assert result.exit_code == 1, f"output: {result.output!r}"
        assert result.stderr == mcp_output + "\n"
        assert result.stdout == ""

    # ----- affected-pages -----

    def test_affected_pages_parity_success(self, tmp_path, monkeypatch):
        """Sparse wiki with one page → empty-state message on both channels."""
        from click.testing import CliRunner

        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        page = wiki_dir / "concepts" / "parity-probe.md"
        page.write_text(
            "---\ntitle: Parity Probe\nsource:\n  - raw/x.md\n---\n\nBody.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("kb.mcp.quality.WIKI_DIR", wiki_dir)
        monkeypatch.setattr("kb.mcp.app.WIKI_DIR", wiki_dir)

        from kb.cli import _is_mcp_error_response
        from kb.mcp.quality import kb_affected_pages

        mcp_output = kb_affected_pages("concepts/parity-probe")
        assert not _is_mcp_error_response(mcp_output), (
            f"precondition failed — mcp_output: {mcp_output!r}"
        )

        from kb.cli import cli

        runner = CliRunner()  # Click 8.3+ splits stdout/stderr by default
        result = runner.invoke(cli, ["affected-pages", "concepts/parity-probe"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert result.stdout == mcp_output + "\n"
        assert result.stderr == ""

    def test_affected_pages_parity_error(self, tmp_path, monkeypatch):
        """Forced exception in ``build_backlinks`` → both channels emit
        identical non-colon ``"Error computing affected pages: ..."``."""
        from click.testing import CliRunner

        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        page = wiki_dir / "concepts" / "parity-probe.md"
        page.write_text(
            "---\ntitle: Parity Probe\nsource:\n  - raw/x.md\n---\n\nBody.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("kb.mcp.quality.WIKI_DIR", wiki_dir)
        monkeypatch.setattr("kb.mcp.app.WIKI_DIR", wiki_dir)

        def _boom():
            raise RuntimeError("forced")

        monkeypatch.setattr("kb.compile.linker.build_backlinks", _boom)

        from kb.cli import _is_mcp_error_response
        from kb.mcp.quality import kb_affected_pages

        mcp_output = kb_affected_pages("concepts/parity-probe")
        assert _is_mcp_error_response(mcp_output), (
            f"precondition failed — mcp_output: {mcp_output!r}"
        )
        assert "Error computing affected pages" in mcp_output

        from kb.cli import cli

        runner = CliRunner()  # Click 8.3+ splits stdout/stderr by default
        result = runner.invoke(cli, ["affected-pages", "concepts/parity-probe"])
        assert result.exit_code == 1, f"output: {result.output!r}"
        assert result.stderr == mcp_output + "\n"
        assert result.stdout == ""

    # ----- lint-deep -----

    def test_lint_deep_parity_success(self, tmp_path, monkeypatch):
        """Spy the direct-below helper ``build_fidelity_context`` to return
        a deterministic string; BOTH channels hit the same spy (owner of
        the output string is the helper, not the MCP tool)."""
        from click.testing import CliRunner

        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        page = wiki_dir / "concepts" / "parity-probe.md"
        page.write_text("---\ntitle: Parity Probe\n---\nBody.\n", encoding="utf-8")
        monkeypatch.setattr("kb.mcp.quality.WIKI_DIR", wiki_dir)
        monkeypatch.setattr("kb.mcp.app.WIKI_DIR", wiki_dir)

        # Helper below MCP returns a deterministic string; both CLI and
        # direct MCP call hit the SAME production code path in the tool.
        monkeypatch.setattr(
            "kb.lint.semantic.build_fidelity_context",
            lambda pid: f"## Page: {pid}\n\n## Sources\n(stub)\n",
        )

        from kb.cli import _is_mcp_error_response
        from kb.mcp.quality import kb_lint_deep

        mcp_output = kb_lint_deep("concepts/parity-probe")
        assert not _is_mcp_error_response(mcp_output), (
            f"precondition failed — mcp_output: {mcp_output!r}"
        )

        from kb.cli import cli

        runner = CliRunner()  # Click 8.3+ splits stdout/stderr by default
        result = runner.invoke(cli, ["lint-deep", "concepts/parity-probe"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert result.stdout == mcp_output + "\n"
        assert result.stderr == ""

    def test_lint_deep_parity_error(self, tmp_path, monkeypatch):
        """Forced ``FileNotFoundError`` in ``build_fidelity_context`` → both
        channels emit identical non-colon ``"Error checking fidelity for"``."""
        from click.testing import CliRunner

        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        page = wiki_dir / "concepts" / "parity-probe.md"
        page.write_text("---\ntitle: Parity Probe\n---\nBody.\n", encoding="utf-8")
        monkeypatch.setattr("kb.mcp.quality.WIKI_DIR", wiki_dir)
        monkeypatch.setattr("kb.mcp.app.WIKI_DIR", wiki_dir)

        def _boom(pid):
            raise FileNotFoundError("/raw/missing-source.md")

        monkeypatch.setattr("kb.lint.semantic.build_fidelity_context", _boom)

        from kb.cli import _is_mcp_error_response
        from kb.mcp.quality import kb_lint_deep

        mcp_output = kb_lint_deep("concepts/parity-probe")
        assert _is_mcp_error_response(mcp_output), (
            f"precondition failed — mcp_output: {mcp_output!r}"
        )
        assert "Error checking fidelity for" in mcp_output

        from kb.cli import cli

        runner = CliRunner()  # Click 8.3+ splits stdout/stderr by default
        result = runner.invoke(cli, ["lint-deep", "concepts/parity-probe"])
        assert result.exit_code == 1, f"output: {result.output!r}"
        assert result.stderr == mcp_output + "\n"
        assert result.stdout == ""


# ---------------------------------------------------------------------------
# AC8 — legacy cycle 27/30 wrapper retrofits (TASK 5)
# ---------------------------------------------------------------------------


class TestLegacyWrapperRetrofit:
    """AC8 — three cycle 27/30 wrappers wrap MCP tools that ALSO emit
    non-colon runtime-error shapes. The legacy ``startswith("Error:")``
    discriminator let those errors exit 0 silently. Retrofit swaps each
    to ``_is_mcp_error_response`` and pins the non-colon error path with
    a revert-divergent regression test (cycle-24 L4 / cycle-16 L2)."""

    def test_stats_non_colon_error_exits_non_zero(self, monkeypatch):
        """`kb_stats` emits ``"Error computing wiki stats: ..."`` at
        `src/kb/mcp/browse.py:348`. Legacy discriminator missed it."""
        from click.testing import CliRunner

        from kb.mcp import browse as browse_mod

        def _spy(wiki_dir=None):
            return "Error computing wiki stats: forced"

        monkeypatch.setattr(browse_mod, "kb_stats", _spy)

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["stats"])
        assert result.exit_code == 1, f"output: {result.output!r}"
        assert "Error computing wiki stats" in result.output

    def test_reliability_map_non_colon_error_exits_non_zero(self, monkeypatch):
        """`kb_reliability_map` emits ``"Error computing reliability map: ..."``
        at `src/kb/mcp/quality.py:245`. Legacy discriminator missed it."""
        from click.testing import CliRunner

        from kb.mcp import quality as quality_mod

        def _spy():
            return "Error computing reliability map: forced"

        monkeypatch.setattr(quality_mod, "kb_reliability_map", _spy)

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["reliability-map"])
        assert result.exit_code == 1, f"output: {result.output!r}"
        assert "Error computing reliability map" in result.output

    def test_lint_consistency_non_colon_error_exits_non_zero(self, monkeypatch):
        """`kb_lint_consistency` emits ``"Error running consistency check: ..."``
        at `src/kb/mcp/quality.py:184`. Legacy discriminator missed it."""
        from click.testing import CliRunner

        from kb.mcp import quality as quality_mod

        def _spy(page_ids=""):
            return "Error running consistency check: forced"

        monkeypatch.setattr(quality_mod, "kb_lint_consistency", _spy)

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["lint-consistency"])
        assert result.exit_code == 1, f"output: {result.output!r}"
        assert "Error running consistency check" in result.output


# ---------------------------------------------------------------------------
# T6 — boot-lean contract (TASK 2)
# ---------------------------------------------------------------------------


class TestBootLean:
    """T6 — `import kb.cli` must not eagerly pull `kb.mcp.browse` /
    `kb.mcp.quality`. Function-local imports with `# noqa: PLC0415`
    defer transitive weight until a subcommand body actually fires.
    """

    def test_cli_import_does_not_eagerly_import_mcp_modules(self):
        import os
        import subprocess
        import sys

        probe = (
            "import sys; "
            "import kb.cli; "
            "bad = [m for m in sys.modules "
            "       if m in ('kb.mcp.browse', 'kb.mcp.quality')]; "
            "assert not bad, f'Eager kb.mcp imports detected: {bad}'; "
            "print('OK')"
        )
        env = {**os.environ, "PYTHONPATH": "src" + os.pathsep + os.environ.get("PYTHONPATH", "")}
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        assert result.returncode == 0, (
            f"subprocess stderr: {result.stderr}\nstdout: {result.stdout}"
        )
        assert "OK" in result.stdout
