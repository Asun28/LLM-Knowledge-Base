"""Cycle 13 — AC7/AC14: kb CLI boot sweep_orphan_tmp wiring regression.

The kb.cli:cli group callback sweeps PROJECT_ROOT/.data and WIKI_DIR for
orphan atomic-write .tmp siblings on every CLI invocation (after the AC30
--version short-circuit and Click's eager --version/--help callbacks).

Sub-tests:
- spy on kb.cli.sweep_orphan_tmp asserts it's called with both deduped
  resolved paths
- pre-aged .tmp files older than 1h are removed; fresh ones survive

Banned-pattern reminder (cycle-11 L1 / cycle-12 inspect-source lessons):
no inspect.getsource, no Path.read_text + splitlines source-scan.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from click.testing import CliRunner

from kb import cli as cli_mod


class TestCliBootSweep:
    """AC14 — CLI boot sweep wiring."""

    def test_sweep_called_with_both_dirs(self, tmp_kb_env, monkeypatch):
        """Spy proves sweep_orphan_tmp is called with .data and WIKI_DIR."""
        calls: list[Path] = []
        real = cli_mod.sweep_orphan_tmp

        def _spy(target):
            calls.append(target)
            return real(target)

        monkeypatch.setattr(cli_mod, "sweep_orphan_tmp", _spy)

        runner = CliRunner()
        result = runner.invoke(cli_mod.cli, ["lint", "--help"])
        assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"

        # Spy MUST receive both the .data and the wiki paths (resolved + deduped).
        expected_data = (tmp_kb_env / ".data").resolve()
        expected_wiki = (tmp_kb_env / "wiki").resolve()
        # On Windows tmp paths the resolved value may be the same shape — assert
        # by membership in the set of call args.
        call_set = {p.resolve() if isinstance(p, Path) else Path(p).resolve() for p in calls}
        assert expected_data in call_set, f"Expected {expected_data} in spy calls; got {call_set}"
        assert expected_wiki in call_set, f"Expected {expected_wiki} in spy calls; got {call_set}"

    def test_stale_tmp_actually_removed(self, tmp_kb_env):
        """Pre-aged .tmp files (mtime > 1 h) are reaped; fresh ones survive."""
        data_dir = tmp_kb_env / ".data"
        data_dir.mkdir(exist_ok=True)
        wiki_dir = tmp_kb_env / "wiki"
        wiki_dir.mkdir(exist_ok=True)

        old_data = data_dir / "old.tmp"
        old_data.write_text("stale", encoding="utf-8")
        old_wiki = wiki_dir / "old.tmp"
        old_wiki.write_text("stale", encoding="utf-8")
        fresh_data = data_dir / "fresh.tmp"
        fresh_data.write_text("hot", encoding="utf-8")

        # Backdate the two old files by 2 hours.
        two_hours_ago = time.time() - 7200
        os.utime(old_data, (two_hours_ago, two_hours_ago))
        os.utime(old_wiki, (two_hours_ago, two_hours_ago))

        runner = CliRunner()
        result = runner.invoke(cli_mod.cli, ["lint", "--help"])
        assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"

        assert not old_data.exists(), f"stale {old_data} should have been removed"
        assert not old_wiki.exists(), f"stale {old_wiki} should have been removed"
        assert fresh_data.exists(), f"fresh {fresh_data} must NOT be removed"

    def test_sweep_dedup_pathological_alias(self, tmp_kb_env, monkeypatch):
        """When PROJECT_ROOT/.data and WIKI_DIR resolve to the same path,
        the sweep runs ONCE on that path (not twice).
        """
        # Force a pathological alias by patching WIKI_DIR to PROJECT_ROOT/.data
        import kb.config as config

        aliased = (tmp_kb_env / ".data").resolve()
        aliased.mkdir(exist_ok=True)
        monkeypatch.setattr(config, "WIKI_DIR", aliased)

        calls: list[Path] = []
        real = cli_mod.sweep_orphan_tmp

        def _spy(target):
            calls.append(Path(target).resolve())
            return real(target)

        monkeypatch.setattr(cli_mod, "sweep_orphan_tmp", _spy)

        runner = CliRunner()
        result = runner.invoke(cli_mod.cli, ["lint", "--help"])
        assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"

        # Dedup means the aliased path appears at most once in the calls.
        unique_calls = set(calls)
        assert aliased in unique_calls
        assert calls.count(aliased) == 1, (
            f"Expected dedup to call {aliased} once; got {calls.count(aliased)} times "
            f"(all calls: {calls})"
        )
