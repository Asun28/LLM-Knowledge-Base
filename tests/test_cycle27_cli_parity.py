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


def test_format_search_results_suppresses_stale_marker_when_absent_or_false():
    """R1 Sonnet M2 fix — negative case for `[STALE]` marker (AC1b).

    Divergent-fail: if a refactor emits `[STALE]` unconditionally (e.g.
    drops the `r.get("stale")` truthiness check), this test fails. Pins
    both the `stale: False` explicit path AND the absent-key path.
    """
    from kb.mcp.browse import _format_search_results

    results_stale_false = [
        {
            "id": "concepts/rag",
            "type": "concept",
            "score": 1.23,
            "title": "RAG Overview",
            "content": "Sample snippet content.",
            "stale": False,
        }
    ]
    out_false = _format_search_results(results_stale_false)
    assert "[STALE]" not in out_false, (
        f"Expected no [STALE] marker for stale=False; got {out_false!r}"
    )

    results_stale_absent = [
        {
            "id": "concepts/rag",
            "type": "concept",
            "score": 1.23,
            "title": "RAG Overview",
            "content": "Sample snippet content.",
            # No `stale` key at all — `r.get("stale")` returns None (falsy).
        }
    ]
    out_absent = _format_search_results(results_stale_absent)
    assert "[STALE]" not in out_absent, (
        f"Expected no [STALE] marker when stale key absent; got {out_absent!r}"
    )


def test_cli_stats_body_executes(tmp_path, monkeypatch):
    """R1 Sonnet M1 fix — `kb stats` body executes `kb_stats`, not just
    Click option parsing.

    Divergent-fail: if the subcommand body were replaced with `pass`
    (or a misrouted handler called the wrong MCP tool), the spy's
    `called` flag would stay False. Pins AC2 wiring beyond `--help`.
    """
    from kb.mcp import browse as browse_mod

    called = {"value": False, "wiki_dir": None}

    def _spy_kb_stats(wiki_dir=None):
        called["value"] = True
        called["wiki_dir"] = wiki_dir
        return "Wiki stats: 0 pages"

    monkeypatch.setattr(browse_mod, "kb_stats", _spy_kb_stats)

    runner = CliRunner()
    result = runner.invoke(cli, ["stats"])
    assert result.exit_code == 0, f"output: {result.output!r}"
    assert called["value"] is True, "kb stats subcommand body must call kb_stats"
    assert "Wiki stats" in result.output


def test_cli_list_pages_body_executes(tmp_path, monkeypatch):
    """R1 Sonnet M1 fix — `kb list-pages` body executes `kb_list_pages`."""
    from kb.mcp import browse as browse_mod

    called = {"value": False, "page_type": None, "limit": None}

    def _spy_kb_list_pages(page_type="", limit=200, offset=0):
        called["value"] = True
        called["page_type"] = page_type
        called["limit"] = limit
        return f"Listing pages (type={page_type!r}, limit={limit}, offset={offset})"

    monkeypatch.setattr(browse_mod, "kb_list_pages", _spy_kb_list_pages)

    runner = CliRunner()
    result = runner.invoke(cli, ["list-pages", "--type", "concept", "--limit", "5"])
    assert result.exit_code == 0, f"output: {result.output!r}"
    assert called["value"] is True, "kb list-pages body must call kb_list_pages"
    assert called["page_type"] == "concept"
    assert called["limit"] == 5


def test_cli_list_sources_body_executes(tmp_path, monkeypatch):
    """R1 Sonnet M1 fix — `kb list-sources` body executes `kb_list_sources`."""
    from kb.mcp import browse as browse_mod

    called = {"value": False, "limit": None, "offset": None}

    def _spy_kb_list_sources(limit=200, offset=0):
        called["value"] = True
        called["limit"] = limit
        called["offset"] = offset
        return f"Listing sources (limit={limit}, offset={offset})"

    monkeypatch.setattr(browse_mod, "kb_list_sources", _spy_kb_list_sources)

    runner = CliRunner()
    result = runner.invoke(cli, ["list-sources", "--limit", "3", "--offset", "1"])
    assert result.exit_code == 0, f"output: {result.output!r}"
    assert called["value"] is True, "kb list-sources body must call kb_list_sources"
    assert called["limit"] == 3
    assert called["offset"] == 1
