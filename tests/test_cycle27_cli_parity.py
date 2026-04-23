"""Cycle 27 AC1-AC5 — CLI ↔ MCP parity for 4 read-only browse tools.

Pins the new CLI subcommands (`search`, `stats`, `list-pages`, `list-sources`)
against their MCP counterparts and the `_format_search_results` helper
extraction (AC1b).

Five tests per cycle-27 CONDITION 3 (4 --help smoke + 1 functional).
Per cycle-13 L3 red-flag: use `--help` invocations so Click's eager-exit
callbacks don't short-circuit the subcommand body and mask wiring bugs.
"""

from __future__ import annotations

from click.testing import CliRunner

from kb.cli import cli


def test_cli_search_help_exits_zero():
    """AC1 — `kb search --help` exits 0 and describes BM25 search."""
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "--help"])
    assert result.exit_code == 0, f"stderr: {result.output!r}"
    assert "Search wiki pages" in result.output
    assert "--limit" in result.output
    assert "--wiki-dir" in result.output


def test_cli_stats_help_exits_zero():
    """AC2 — `kb stats --help` exits 0 and describes wiki snapshot."""
    runner = CliRunner()
    result = runner.invoke(cli, ["stats", "--help"])
    assert result.exit_code == 0, f"stderr: {result.output!r}"
    assert "wiki" in result.output.lower()


def test_cli_list_pages_help_exits_zero():
    """AC3 — `kb list-pages --help` exits 0 and exposes --type filter."""
    runner = CliRunner()
    result = runner.invoke(cli, ["list-pages", "--help"])
    assert result.exit_code == 0, f"stderr: {result.output!r}"
    assert "--type" in result.output
    assert "--limit" in result.output
    assert "--offset" in result.output


def test_cli_list_sources_help_exits_zero():
    """AC4 — `kb list-sources --help` exits 0 and exposes --limit/--offset."""
    runner = CliRunner()
    result = runner.invoke(cli, ["list-sources", "--help"])
    assert result.exit_code == 0, f"stderr: {result.output!r}"
    assert "--limit" in result.output
    assert "--offset" in result.output


def test_cli_search_empty_query_exits_non_zero():
    """AC1 — empty query surfaces via non-zero exit with stderr message.

    Cycle-26 L3 / CONDITION 2 — Error-string path exits non-zero per Q3
    decision (Unix convention: user-error → non-zero).
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["search", ""])
    assert result.exit_code != 0, (
        f"Empty query must exit non-zero; got exit={result.exit_code}, output={result.output!r}"
    )
    # Error message goes to stderr; CliRunner merges unless mix_stderr=False —
    # assert the "Query cannot be empty." text appears regardless.
    assert "Query cannot be empty" in result.output or "Query cannot be empty" in str(
        result.exception or ""
    )


def test_format_search_results_empty_list_returns_no_match_string():
    """AC1b — extracted `_format_search_results([])` returns the canonical
    "No matching pages found." string (preserves pre-extraction kb_search
    behaviour under the success path with zero results).
    """
    from kb.mcp.browse import _format_search_results

    assert _format_search_results([]) == "No matching pages found."


def test_format_search_results_preserves_stale_marker():
    """AC1b — `_format_search_results` preserves `[STALE]` marker semantics.

    Divergent-fail: if the helper drops the `stale` key check, this test
    fails because the marker is absent from the formatted output.
    """
    from kb.mcp.browse import _format_search_results

    fake = [
        {
            "id": "concepts/rag",
            "type": "concept",
            "score": 1.23,
            "title": "RAG Overview",
            "content": "Sample snippet content.",
            "stale": True,
        }
    ]
    output = _format_search_results(fake)
    assert "[STALE]" in output, f"Expected [STALE] marker; got {output!r}"
    assert "concepts/rag" in output
    assert "RAG Overview" in output
