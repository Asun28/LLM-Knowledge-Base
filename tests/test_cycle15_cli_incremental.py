"""Cycle 15 AC13/AC29 — kb publish --incremental/--no-incremental flag.

T8 — containment check at cli.py:369-388 runs BEFORE flag plumbing at
cli.py:391; --no-incremental must NOT be able to bypass path validation.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner


def _seed_wiki_and_project(tmp_path: Path) -> Path:
    """Create a minimal project tree with wiki/ + pyproject.toml."""
    wiki = tmp_path / "wiki"
    for sub in ("concepts", "entities", "summaries", "comparisons", "synthesis"):
        (wiki / sub).mkdir(parents=True, exist_ok=True)
    page = wiki / "concepts" / "seed.md"
    page.write_text(
        """---
title: seed
source:
  - raw/articles/seed.md
created: 2026-04-20
updated: 2026-04-20
type: concept
confidence: stated
---
Body.
""",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='test-kb'\nversion='0.1.0'\n", encoding="utf-8"
    )
    return wiki


class TestIncrementalFlag:
    """AC29 — default is --incremental; --no-incremental forces regen."""

    def test_publish_default_uses_incremental_true(self, tmp_path, monkeypatch):
        _seed_wiki_and_project(tmp_path)
        monkeypatch.setenv("KB_PROJECT_ROOT", str(tmp_path))
        # Reload config to pick up new PROJECT_ROOT
        import importlib

        import kb.config as config

        importlib.reload(config)
        import kb.cli as cli_mod
        import kb.compile.publish as publish

        importlib.reload(publish)
        importlib.reload(cli_mod)

        captured: list[bool] = []
        real_builder = publish.build_llms_txt

        def _spy_builder(*args, incremental=False, **kw):
            captured.append(incremental)
            return real_builder(*args, incremental=incremental, **kw)

        monkeypatch.setattr(cli_mod, "publish", cli_mod.publish)  # no-op; stabilises ref
        monkeypatch.setattr(publish, "build_llms_txt", _spy_builder)
        monkeypatch.setattr(publish, "build_llms_full_txt", _spy_builder)
        monkeypatch.setattr(publish, "build_graph_jsonld", _spy_builder)

        runner = CliRunner()
        out = tmp_path / "outputs"
        result = runner.invoke(cli_mod.cli, ["publish", "--out-dir", str(out), "--format", "llms"])
        assert result.exit_code == 0, result.output
        assert captured == [True], (
            f"default --incremental should pass incremental=True; got {captured}"
        )

    def test_publish_no_incremental_disables(self, tmp_path, monkeypatch):
        _seed_wiki_and_project(tmp_path)
        monkeypatch.setenv("KB_PROJECT_ROOT", str(tmp_path))
        import importlib

        import kb.config as config

        importlib.reload(config)
        import kb.cli as cli_mod
        import kb.compile.publish as publish

        importlib.reload(publish)
        importlib.reload(cli_mod)

        captured: list[bool] = []
        real_builder = publish.build_llms_txt

        def _spy_builder(*args, incremental=False, **kw):
            captured.append(incremental)
            return real_builder(*args, incremental=incremental, **kw)

        monkeypatch.setattr(publish, "build_llms_txt", _spy_builder)
        monkeypatch.setattr(publish, "build_llms_full_txt", _spy_builder)
        monkeypatch.setattr(publish, "build_graph_jsonld", _spy_builder)

        runner = CliRunner()
        out = tmp_path / "outputs"
        result = runner.invoke(
            cli_mod.cli,
            ["publish", "--out-dir", str(out), "--format", "llms", "--no-incremental"],
        )
        assert result.exit_code == 0, result.output
        assert captured == [False], (
            f"--no-incremental should pass incremental=False; got {captured}"
        )


class TestContainmentPreservedT8:
    """AC29 T8 — --no-incremental must not bypass path containment."""

    def test_no_incremental_out_dir_outside_project_rejected(self, tmp_path, monkeypatch):
        """Containment check at cli.py:369-388 fires BEFORE --incremental plumbing."""
        _seed_wiki_and_project(tmp_path)
        monkeypatch.setenv("KB_PROJECT_ROOT", str(tmp_path))
        import importlib

        import kb.config as config

        importlib.reload(config)
        import kb.cli as cli_mod

        importlib.reload(cli_mod)

        # Use a distinct temporary area OUTSIDE the seeded project root.
        # tmp_path's parent is typically pytest's cache root — use a sibling
        # to guarantee outside-project. Do NOT create it — containment check
        # rejects outside + non-existent paths.
        outside = tmp_path.parent / f"outside-{tmp_path.name}-nowhere"
        assert not outside.exists()

        runner = CliRunner()
        result = runner.invoke(
            cli_mod.cli,
            ["publish", "--out-dir", str(outside), "--no-incremental"],
        )
        assert result.exit_code != 0, (
            "outside-project + non-existent --out-dir must raise UsageError"
        )
        # outside dir must NOT be created by the CLI
        assert not outside.exists(), "containment rejection must fire BEFORE mkdir (T8)"
