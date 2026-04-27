"""Cycle 17 AC11-AC13 — lint augment resume wiring across lib/CLI/MCP.

AC11: `run_augment(resume=...)` skips Phase A and iterates incomplete gaps.
AC12: `kb lint --resume <id>` forwards to run_augment with `--augment` required.
AC13: `kb_lint(resume=...)` MCP surface with shared `_validate_run_id` helper.

All three call sites use the SAME shared validator in `kb.mcp.app._validate_run_id`.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from kb.cli import cli
from kb.lint._augment_manifest import Manifest


def _write_manifest(path: Path, run_id: str, gaps: list[dict]) -> None:
    """Write a manifest file directly for test setup."""
    data = {
        "schema": 1,
        "run_id": run_id,
        "started_at": "2026-04-20T00:00:00Z",
        "ended_at": None,
        "mode": "execute",
        "max_gaps": 5,
        "gaps": gaps,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class TestAC11ManifestResumeExactMatch:
    """AC11 — Manifest.resume uses exact 8-char match, no glob prefix."""

    def test_exact_match_returns_manifest(self, tmp_path: Path) -> None:
        run_id = "deadbeef" + "00" * 12  # 32-char uuid-like string; filename uses [:8]
        path = tmp_path / "augment-run-deadbeef.json"
        _write_manifest(
            path,
            run_id,
            [{"page_id": "p1", "title": "P1", "state": "pending", "transitions": []}],
        )

        manifest = Manifest.resume(run_id="deadbeef", data_dir=tmp_path)
        assert manifest is not None
        assert manifest.run_id == run_id

    def test_no_match_returns_none(self, tmp_path: Path) -> None:
        # Directory exists but no matching manifest file.
        tmp_path.mkdir(exist_ok=True)
        assert Manifest.resume(run_id="deadbeef", data_dir=tmp_path) is None

    def test_completed_run_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "augment-run-deadbeef.json"
        data = {
            "schema": 1,
            "run_id": "deadbeef-full-uuid",
            "started_at": "2026-04-20T00:00:00Z",
            "ended_at": "2026-04-20T01:00:00Z",  # completed
            "mode": "execute",
            "max_gaps": 5,
            "gaps": [],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        assert Manifest.resume(run_id="deadbeef", data_dir=tmp_path) is None

    def test_resume_signature_uses_run_id_not_prefix(self) -> None:
        """Regression pin — the parameter MUST be `run_id`, not `run_id_prefix`.

        Cycle 17 design gate Q8 renamed the parameter to reflect exact-match
        semantics. A future revert to `run_id_prefix` would re-enable the
        prefix-collision ambiguity that Q8 eliminated.
        """
        import inspect

        sig = inspect.signature(Manifest.resume)
        assert "run_id" in sig.parameters
        assert "run_id_prefix" not in sig.parameters


class TestAC12CliResumeFlag:
    """AC12 — `kb lint --resume <id>` CLI option with --augment dependency."""

    def test_help_includes_resume(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["lint", "--help"])
        assert result.exit_code == 0
        assert "--resume" in result.output

    def test_resume_without_augment_errors(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["lint", "--resume", "abc12345"])
        assert result.exit_code != 0
        assert "--resume requires --augment" in result.output

    def test_resume_invalid_id_errors(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["lint", "--resume", "../etc", "--augment"])
        assert result.exit_code != 0
        assert "Invalid resume id" in result.output

    def test_resume_valid_forwards_to_run_augment(self, tmp_path: Path) -> None:
        captured_kwargs = {}

        def spy_run_augment(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "summary": "ok",
                "run_id": "deadbeef",
                "mode": "propose",
                "gaps_examined": 0,
                "gaps_eligible": 0,
            }

        runner = CliRunner()
        with (
            patch("kb.lint.augment.orchestrator.run_augment", side_effect=spy_run_augment),
            patch(
                "kb.lint.runner.run_all_checks",
                return_value={"summary": {"error": 0}, "fixes_applied": []},
            ),
            patch("kb.lint.runner.format_report", return_value=""),
        ):
            result = runner.invoke(cli, ["lint", "--augment", "--resume", "abc12345"])
        assert result.exit_code == 0, result.output
        assert captured_kwargs.get("resume") == "abc12345"


class TestAC13McpResumeParam:
    """AC13 — `kb_lint(resume=...)` MCP wrapper with shared validator."""

    def test_resume_without_augment_returns_error(self) -> None:
        from kb.mcp.health import kb_lint

        result = kb_lint(resume="abc12345")
        assert result.startswith("Error:")
        assert "resume requires augment" in result

    def test_resume_invalid_id_returns_error(self) -> None:
        from kb.mcp.health import kb_lint

        result = kb_lint(resume="../etc", augment=True)
        assert result.startswith("Error:")
        assert "Invalid resume id" in result

    def test_resume_forwards_to_run_augment(self, tmp_path: Path) -> None:
        from kb.mcp.health import kb_lint

        captured_kwargs = {}

        def spy_run_augment(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "summary": "ok",
                "run_id": "abc12345",
                "mode": "propose",
                "gaps_examined": 0,
                "gaps_eligible": 0,
            }

        with (
            patch("kb.lint.augment.orchestrator.run_augment", side_effect=spy_run_augment),
            patch(
                "kb.lint.runner.run_all_checks",
                return_value={"summary": {"error": 0}, "fixes_applied": []},
            ),
            patch("kb.lint.runner.format_report", return_value=""),
        ):
            kb_lint(resume="abc12345", augment=True)
        assert captured_kwargs.get("resume") == "abc12345"


class TestSharedValidatorSingleSourceOfTruth:
    """Cycle 17 C8 — CLI + MCP must share the same `_validate_run_id` helper."""

    def test_cli_and_mcp_use_same_validator(self) -> None:
        """Both paths reject the same bad input with equivalent messages."""
        from kb.mcp.app import _validate_run_id
        from kb.mcp.health import kb_lint

        bad = "too-short"
        lib_err = _validate_run_id(bad)
        mcp_err = kb_lint(resume=bad, augment=True)

        assert lib_err is not None
        assert mcp_err.startswith("Error:")
        # The MCP surface prepends "Error:" and embeds the lib error text.
        assert "Invalid resume id" in lib_err
        assert "Invalid resume id" in mcp_err
