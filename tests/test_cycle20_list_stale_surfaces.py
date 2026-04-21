"""Cycle 20 AC14/AC15/AC17/AC18/AC19 — MCP + CLI surfaces for sweep & list-stale.

Pins:
- AC14 MCP kb_refine_sweep: JSON result, ValidationError → Error string.
- AC15 CLI kb refine-sweep: --dry-run returns candidates.
- AC17 MCP kb_refine_list_stale: projects to minimal fields
  (attempt_id, page_id, timestamp, notes_length) — revision_notes NOT leaked.
- AC18 CLI kb refine-list-stale: returns full helper dict (local-use exception).
- AC19: asymmetric MCP projection vs CLI full-dict.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from kb.review.refiner import save_review_history


def _iso(delta_hours: float) -> str:
    return (datetime.now() - timedelta(hours=delta_hours)).isoformat()


def _seed_history(tmp_kb_env: Path, rows: list[dict]) -> Path:
    data_dir = tmp_kb_env / ".data"
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "review_history.json"
    save_review_history(rows, path)
    return path


@pytest.fixture
def seeded_history(tmp_kb_env: Path, monkeypatch) -> Path:
    """Seed review_history.json with 1 stale + 1 fresh pending row.

    Belt-and-braces: besides the tmp_kb_env mirror-rebind, explicitly patch
    ``kb.review.refiner.REVIEW_HISTORY_PATH`` (and ``kb.mcp.quality.WIKI_DIR``)
    so MCP + CLI tools resolve to this fixture's paths even if the owner
    modules were imported before ``tmp_kb_env`` ran under a full-suite
    ordering that missed the mirror-rebind window.
    """
    path = _seed_history(
        tmp_kb_env,
        [
            {
                "page_id": "entities/stale-a",
                "attempt_id": "stale001",
                "status": "pending",
                "timestamp": _iso(300),
                "revision_notes": "this should NOT leak via MCP",
            },
            {
                "page_id": "entities/fresh-b",
                "attempt_id": "fresh001",
                "status": "pending",
                "timestamp": _iso(0.1),
                "revision_notes": "fresh note",
            },
        ],
    )
    # Defensive explicit monkeypatch — cycle-19 L1 snapshot-binding hazard
    # resurfaces under full-suite ordering for new modules imported after
    # mirror-rebind has already run.
    import kb.mcp.quality as _quality
    import kb.review.refiner as _refiner

    monkeypatch.setattr(_refiner, "REVIEW_HISTORY_PATH", path, raising=False)
    monkeypatch.setattr(_refiner, "WIKI_DIR", tmp_kb_env / "wiki", raising=False)
    monkeypatch.setattr(_quality, "WIKI_DIR", tmp_kb_env / "wiki", raising=False)
    return path


class TestMcpKbRefineSweep:
    """AC14 — MCP kb_refine_sweep returns JSON; ValidationError → Error string."""

    def test_happy_path_returns_json(self, seeded_history: Path) -> None:
        # Clear lazy monkeypatch scope — call the tool directly.
        from kb.mcp.quality import kb_refine_sweep

        out = kb_refine_sweep(hours=168, action="mark_failed")
        # MCP tool wrappers are @mcp.tool() decorated — FastMCP may return a
        # callable or the raw return. If it's callable, invoke it.
        if callable(out):
            out = out(hours=168, action="mark_failed")
        payload = json.loads(out)
        assert payload["swept"] == 1
        assert payload["action"] == "mark_failed"
        assert payload["dry_run"] is False
        assert payload["sweep_id"] and len(payload["sweep_id"]) == 8

    def test_validation_error_returns_error_string(self, seeded_history: Path) -> None:
        from kb.mcp.quality import kb_refine_sweep

        out = kb_refine_sweep(hours=168, action="nope")
        if callable(out):
            out = out(hours=168, action="nope")
        assert isinstance(out, str)
        assert out.startswith("Error:")
        assert "unknown sweep action" in out

    def test_dry_run_returns_candidates(self, seeded_history: Path) -> None:
        from kb.mcp.quality import kb_refine_sweep

        out = kb_refine_sweep(hours=168, action="mark_failed", dry_run=True)
        if callable(out):
            out = out(hours=168, action="mark_failed", dry_run=True)
        payload = json.loads(out)
        assert payload["dry_run"] is True
        assert payload["swept"] == 1
        assert any(c["attempt_id"] == "stale001" for c in payload["candidates"])

    def test_dry_run_candidates_omit_revision_notes(self, seeded_history: Path) -> None:
        """Cycle-20 R3 MAJOR — dry_run candidates must NOT carry revision_notes.

        Regression for T5 extension: the underlying helper returns full row
        dicts so the CLI can render them, but the MCP boundary projects to
        the same minimal field set as `kb_refine_list_stale`.
        """
        from kb.mcp.quality import kb_refine_sweep

        out = kb_refine_sweep(hours=168, action="mark_failed", dry_run=True)
        if callable(out):
            out = out(hours=168, action="mark_failed", dry_run=True)
        payload = json.loads(out)
        for cand in payload["candidates"]:
            assert set(cand.keys()) == {"attempt_id", "page_id", "timestamp", "notes_length"}
            assert "revision_notes" not in cand, (
                "MCP must NOT leak revision_notes through dry_run candidates"
            )
            # notes_length should reflect the seeded revision_notes length.
            if cand["attempt_id"] == "stale001":
                assert cand["notes_length"] == len("this should NOT leak via MCP")


class TestMcpKbRefineListStaleProjection:
    """AC17 / AC19 / T5 — MCP projection excludes revision_notes, adds notes_length."""

    def test_projects_to_minimal_field_set(self, seeded_history: Path) -> None:
        from kb.mcp.quality import kb_refine_list_stale

        out = kb_refine_list_stale(hours=24)
        if callable(out):
            out = out(hours=24)
        rows = json.loads(out)
        assert len(rows) == 1  # only the 300h-old row is stale
        row = rows[0]
        assert row["attempt_id"] == "stale001"
        assert row["page_id"] == "entities/stale-a"
        assert "timestamp" in row
        # T5 mitigation — notes_length is the projection of revision_notes.
        assert row["notes_length"] == len("this should NOT leak via MCP")
        assert "revision_notes" not in row, "MCP must NOT leak revision_notes"

    def test_invalid_hours_returns_error_string(self, seeded_history: Path) -> None:
        from kb.mcp.quality import kb_refine_list_stale

        out = kb_refine_list_stale(hours=0)
        if callable(out):
            out = out(hours=0)
        assert isinstance(out, str) and out.startswith("Error:")


class TestCliRefineSweepCliDryRun:
    """AC15 — CLI --dry-run prints candidates JSON."""

    def test_cli_dry_run_prints_candidates(self, seeded_history: Path) -> None:
        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["refine-sweep", "--age-hours", "168", "--action", "mark_failed", "--dry-run"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["dry_run"] is True
        assert payload["swept"] == 1


class TestCliRefineListStaleFullDict:
    """AC18 / AC19 — CLI local-use exception: returns full helper dict."""

    def test_cli_returns_revision_notes_unlike_mcp(self, seeded_history: Path) -> None:
        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["refine-list-stale", "--hours", "24"], catch_exceptions=False)
        assert result.exit_code == 0, result.output
        rows = json.loads(result.output)
        assert len(rows) == 1
        # CLI keeps the full helper dict including revision_notes (local-use exception).
        assert rows[0]["revision_notes"] == "this should NOT leak via MCP"


class TestToolGroupsIncludesNewTools:
    """AC14 / AC17 — _TOOL_GROUPS must list kb_refine_sweep + kb_refine_list_stale."""

    def test_tool_groups_contains_new_tools(self) -> None:
        from kb.mcp.app import _TOOL_GROUPS

        all_names: set[str] = set()
        for _group, tools in _TOOL_GROUPS:
            for name, _desc in tools:
                all_names.add(name)
        assert "kb_refine_sweep" in all_names
        assert "kb_refine_list_stale" in all_names
