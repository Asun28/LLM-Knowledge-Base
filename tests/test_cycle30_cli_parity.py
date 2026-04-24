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
