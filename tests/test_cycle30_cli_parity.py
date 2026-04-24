"""Cycle 30 AC2-AC6 — CLI parity for 5 read-only MCP tools.

Pins new CLI subcommands `graph-viz`, `verdict-trends`, `detect-drift`,
`reliability-map`, `lint-consistency` against their MCP counterparts via
the cycle-27 thin-wrapper pattern (function-local import + forward args
raw + `"Error:" prefix → sys.exit(1)` contract).

Per cycle-27 L2: each subcommand has BOTH a `--help` smoke test AND a
body-executing spy test. The spy patches the MCP SOURCE MODULE
(`kb.mcp.health` / `kb.mcp.quality`) because the CLI's function-local
import resolves at call time — patching `kb.cli` would silently fail.

Per cycle-13 L3: `--help` invocations are parser-only (body never runs);
body tests use `runner.invoke(cli, [<subcmd>, ...args])` without `--help`.
"""

from __future__ import annotations

from click.testing import CliRunner

from kb.cli import cli

# ---------------------------------------------------------------------------
# AC2 — `kb graph-viz`
# ---------------------------------------------------------------------------


class TestGraphVizCli:
    """AC2 — CLI parity for MCP `kb_graph_viz`."""

    def test_graph_viz_help_exits_zero(self):
        """`kb graph-viz --help` exits 0 and documents the 1-500 range."""
        runner = CliRunner()
        result = runner.invoke(cli, ["graph-viz", "--help"])
        assert result.exit_code == 0, f"stderr: {result.output!r}"
        assert "--max-nodes" in result.output
        assert "--wiki-dir" in result.output
        # R1 Opus amendment C5 — help text must document the range.
        assert "1-500" in result.output
        assert "0 rejected" in result.output

    def test_graph_viz_body_executes_forwards_max_nodes(self, monkeypatch):
        """`kb graph-viz --max-nodes 50` invokes MCP tool with the kwarg.

        Divergent-fail: if the CLI body were replaced with `pass`, `called`
        stays False and the test fails.
        """
        from kb.mcp import health as health_mod

        called = {"value": False, "max_nodes": None, "wiki_dir": None}

        def _spy(max_nodes=30, wiki_dir=None):
            called["value"] = True
            called["max_nodes"] = max_nodes
            called["wiki_dir"] = wiki_dir
            return "graph TD\nA-->B"

        monkeypatch.setattr(health_mod, "kb_graph_viz", _spy)

        runner = CliRunner()
        result = runner.invoke(cli, ["graph-viz", "--max-nodes", "50"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert called["value"] is True
        assert called["max_nodes"] == 50
        assert called["wiki_dir"] is None
        assert "graph TD" in result.output

    def test_graph_viz_error_prefix_exits_non_zero(self, monkeypatch):
        """MCP `Error:` prefix surfaces via non-zero exit + stderr."""
        from kb.mcp import health as health_mod

        monkeypatch.setattr(
            health_mod, "kb_graph_viz", lambda max_nodes=30, wiki_dir=None: "Error: bad thing"
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["graph-viz"])
        assert result.exit_code != 0
        assert "Error: bad thing" in result.output

    def test_graph_viz_max_nodes_zero_exits_non_zero(self, monkeypatch):
        """R1 Sonnet MAJOR 2 — `--max-nodes 0` hits MCP tool's `"Error:"`-prefix
        rejection path and surfaces via non-zero exit.

        The MCP tool `kb_graph_viz` at `src/kb/mcp/health.py:191-197` rejects
        `max_nodes=0` with an explicit `"Error: max_nodes=0 is not allowed..."`
        string. This test pins the CLI → MCP zero-rejection contract so a
        future MCP refactor that drops the `"Error:"` prefix on the 0-path
        would surface as a test failure instead of silent exit-0 drift
        (cycle-16 L2 class).
        """
        # NO monkeypatch — exercise the real MCP tool's 0-rejection path.
        runner = CliRunner()
        result = runner.invoke(cli, ["graph-viz", "--max-nodes", "0"])
        assert result.exit_code != 0, (
            f"--max-nodes 0 must exit non-zero; got exit={result.exit_code}, "
            f"output={result.output!r}"
        )
        assert "max_nodes=0" in result.output or "Error:" in result.output

    def test_graph_viz_max_nodes_negative_clamps_at_mcp(self, monkeypatch):
        """R1 Sonnet MAJOR 2 follow-up — `--max-nodes -1` reaches MCP layer
        which clamps negatives via `max(1, min(n, 500))`.

        Divergent-fail: if CLI added its own rejection for negatives
        (diverging from the MCP tool's clamp semantics), this test would
        flip because `called["max_nodes"]` would not be -1. The CLI
        passthrough contract is that negatives reach the MCP layer
        un-modified.
        """
        from kb.mcp import health as health_mod

        called = {"max_nodes": None}

        def _spy(max_nodes=30, wiki_dir=None):
            called["max_nodes"] = max_nodes
            # Echo the MCP clamp behavior (not under test — we just
            # assert the CLI forwarded -1 un-modified).
            return "graph TD\nA-->B"

        monkeypatch.setattr(health_mod, "kb_graph_viz", _spy)

        runner = CliRunner()
        result = runner.invoke(cli, ["graph-viz", "--max-nodes", "-1"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        # CLI forwarded -1 raw — MCP is responsible for clamping.
        assert called["max_nodes"] == -1, (
            f"CLI must forward --max-nodes raw to MCP; got {called['max_nodes']}"
        )


# ---------------------------------------------------------------------------
# AC3 — `kb verdict-trends`
# ---------------------------------------------------------------------------


class TestVerdictTrendsCli:
    """AC3 — CLI parity for MCP `kb_verdict_trends`."""

    def test_verdict_trends_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["verdict-trends", "--help"])
        assert result.exit_code == 0, f"stderr: {result.output!r}"
        assert "--wiki-dir" in result.output

    def test_verdict_trends_body_executes(self, monkeypatch):
        from kb.mcp import health as health_mod

        called = {"value": False, "wiki_dir": None}

        def _spy(wiki_dir=None):
            called["value"] = True
            called["wiki_dir"] = wiki_dir
            return "# Verdict Trends\nNo history yet."

        monkeypatch.setattr(health_mod, "kb_verdict_trends", _spy)

        runner = CliRunner()
        result = runner.invoke(cli, ["verdict-trends"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert called["value"] is True
        assert called["wiki_dir"] is None
        assert "Verdict Trends" in result.output


# ---------------------------------------------------------------------------
# AC4 — `kb detect-drift`
# ---------------------------------------------------------------------------


class TestDetectDriftCli:
    """AC4 — CLI parity for MCP `kb_detect_drift`."""

    def test_detect_drift_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["detect-drift", "--help"])
        assert result.exit_code == 0, f"stderr: {result.output!r}"
        assert "--wiki-dir" in result.output

    def test_detect_drift_body_executes(self, monkeypatch):
        from kb.mcp import health as health_mod

        called = {"value": False, "wiki_dir": None}

        def _spy(wiki_dir=None):
            called["value"] = True
            called["wiki_dir"] = wiki_dir
            return "# Source Drift Detection\nNo drift detected."

        monkeypatch.setattr(health_mod, "kb_detect_drift", _spy)

        runner = CliRunner()
        result = runner.invoke(cli, ["detect-drift"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert called["value"] is True
        assert "Source Drift Detection" in result.output


# ---------------------------------------------------------------------------
# AC5 — `kb reliability-map`
# ---------------------------------------------------------------------------


class TestReliabilityMapCli:
    """AC5 — CLI parity for MCP `kb_reliability_map` (zero args)."""

    def test_reliability_map_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["reliability-map", "--help"])
        assert result.exit_code == 0, f"stderr: {result.output!r}"
        # No options — but help text should mention trust scores.
        assert "trust" in result.output.lower()
        # Cycle-30 C7/C12 — reliability-map takes no args, no --wiki-dir.
        assert "--wiki-dir" not in result.output

    def test_reliability_map_no_feedback_exits_zero(self, monkeypatch):
        """Empty-state message is NOT an Error: prefix → exit 0.

        Cycle 30 AC5 specifically calls out this edge — do not conflate
        "No feedback recorded yet" with an error.
        """
        from kb.mcp import quality as quality_mod

        monkeypatch.setattr(
            quality_mod,
            "kb_reliability_map",
            lambda: "No feedback recorded yet. Use kb_query_feedback after queries.",
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["reliability-map"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert "No feedback recorded yet" in result.output

    def test_reliability_map_body_executes(self, monkeypatch):
        from kb.mcp import quality as quality_mod

        called = {"value": False}

        def _spy():
            called["value"] = True
            return "# Page Reliability Map\n- concepts/rag: trust=0.80"

        monkeypatch.setattr(quality_mod, "kb_reliability_map", _spy)

        runner = CliRunner()
        result = runner.invoke(cli, ["reliability-map"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert called["value"] is True
        assert "Page Reliability Map" in result.output


# ---------------------------------------------------------------------------
# AC6 — `kb lint-consistency`
# ---------------------------------------------------------------------------


class TestLintConsistencyCli:
    """AC6 — CLI parity for MCP `kb_lint_consistency`."""

    def test_lint_consistency_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["lint-consistency", "--help"])
        assert result.exit_code == 0, f"stderr: {result.output!r}"
        assert "--page-ids" in result.output
        # Cycle-30 C7 — lint-consistency MCP tool has no wiki_dir param;
        # CLI must NOT expose --wiki-dir to avoid a silent-drop surface.
        assert "--wiki-dir" not in result.output

    def test_lint_consistency_body_executes_with_ids_raw(self, monkeypatch):
        """`--page-ids` forwarded RAW (not split) to the MCP tool.

        Cycle-30 C6 — MCP tool is the single source of truth for comma
        splitting. Divergent-fail: if CLI were to call `.split(",")` and
        pass a list, this assertion (comparing to the exact raw string)
        would flip.
        """
        from kb.mcp import quality as quality_mod

        called = {"value": False, "page_ids": None}

        def _spy(page_ids=""):
            called["value"] = True
            called["page_ids"] = page_ids
            return "# Consistency Report\nNo contradictions found."

        monkeypatch.setattr(quality_mod, "kb_lint_consistency", _spy)

        runner = CliRunner()
        result = runner.invoke(cli, ["lint-consistency", "--page-ids", "concepts/rag,concepts/llm"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert called["value"] is True
        # Raw-string passthrough — NOT split into a list.
        assert called["page_ids"] == "concepts/rag,concepts/llm"
        assert "Consistency Report" in result.output

    def test_lint_consistency_body_empty_defaults_to_empty_string(self, monkeypatch):
        """No `--page-ids` → MCP tool receives `""` (empty string), not None.

        MCP tool maps empty string to its "auto-select" mode at
        `kb.mcp.quality.kb_lint_consistency` line 173.
        """
        from kb.mcp import quality as quality_mod

        called = {"page_ids": "__sentinel__"}

        def _spy(page_ids=""):
            called["page_ids"] = page_ids
            return "# Auto Consistency\nno groups"

        monkeypatch.setattr(quality_mod, "kb_lint_consistency", _spy)

        runner = CliRunner()
        result = runner.invoke(cli, ["lint-consistency"])
        assert result.exit_code == 0
        assert called["page_ids"] == ""
