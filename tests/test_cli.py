"""Tests for the CLI commands."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from kb.cli import cli

runner = CliRunner()


def test_cli_version():
    """CLI --version prints version (cycle 34 bumped 0.10.0 → 0.11.0)."""
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.11.0" in result.output


def test_cli_help():
    """CLI --help lists all commands."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "ingest" in result.output
    assert "compile" in result.output
    assert "query" in result.output
    assert "lint" in result.output
    assert "evolve" in result.output


@patch("kb.ingest.pipeline.extract_from_source")
def test_cli_ingest(mock_extract, tmp_path):
    """CLI ingest command processes a source file."""
    mock_extract.return_value = {
        "title": "Test",
        "entities_mentioned": [],
        "concepts_mentioned": [],
    }

    # Set up temp dirs
    raw_dir = tmp_path / "raw" / "articles"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "test.md"
    source.write_text("# Test Article\n\nContent here.")

    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True)
    (wiki_dir / "index.md").write_text(
        "---\ntitle: Wiki Index\nupdated: 2026-04-06\n---\n\n"
        "## Entities\n\n*No pages yet.*\n\n## Concepts\n\n*No pages yet.*\n\n"
        "## Comparisons\n\n*No pages yet.*\n\n## Summaries\n\n*No pages yet.*\n\n"
        "## Synthesis\n\n*No pages yet.*\n"
    )
    (wiki_dir / "_sources.md").write_text("---\ntitle: Sources\nupdated: 2026-04-06\n---\n\n")
    (wiki_dir / "log.md").write_text("---\ntitle: Log\nupdated: 2026-04-06\n---\n\n")

    with (
        patch("kb.ingest.pipeline.RAW_DIR", tmp_path / "raw"),
        patch("kb.utils.paths.RAW_DIR", tmp_path / "raw"),
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
    ):
        result = runner.invoke(cli, ["ingest", str(source), "--type", "article"])

    assert result.exit_code == 0
    assert "Ingesting" in result.output
    assert "Done" in result.output


def test_cli_lint(tmp_path):
    """CLI lint command runs checks."""
    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    with (
        patch("kb.lint.runner.WIKI_DIR", wiki_dir),
        patch("kb.lint.runner.RAW_DIR", raw_dir),
        patch("kb.lint.checks.WIKI_DIR", wiki_dir),
        patch("kb.lint.checks.RAW_DIR", raw_dir),
    ):
        result = runner.invoke(cli, ["lint"])

    assert result.exit_code == 0
    assert "Lint Report" in result.output


def test_cli_evolve(tmp_path):
    """CLI evolve command runs analysis."""
    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True)

    with patch("kb.evolve.analyzer.WIKI_DIR", wiki_dir):
        result = runner.invoke(cli, ["evolve"])

    assert result.exit_code == 0
    assert "Evolution Report" in result.output


# ── Cycle 11 CLI import smoke tests (folded from test_cycle11_cli_imports.py) ─


def _assert_ok(result) -> None:
    assert result.exit_code == 0, f"output:\n{result.output}\nexception:\n{result.exception!r}"


def test_ingest_cli_runner_smoke(monkeypatch, tmp_path):
    from kb.ingest import pipeline

    source = tmp_path / "source.md"
    source.write_text("# Source\n", encoding="utf-8")

    def fake_ingest_source(source_path, source_type):
        return {
            "source_type": source_type or "article",
            "content_hash": "abc123",
            "pages_created": [],
            "pages_updated": [],
            "pages_skipped": [],
            "affected_pages": [],
            "wikilinks_injected": 0,
        }

    monkeypatch.setattr(pipeline, "ingest_source", fake_ingest_source)
    result = CliRunner().invoke(cli, ["ingest", str(source)])
    _assert_ok(result)


def test_compile_cli_runner_smoke(monkeypatch):
    from kb.compile import compiler

    def fake_compile_wiki(*, incremental=True):
        return {
            "sources_processed": 0,
            "pages_created": [],
            "pages_updated": [],
            "pages_skipped": [],
            "errors": [],
        }

    monkeypatch.setattr(compiler, "compile_wiki", fake_compile_wiki)
    result = CliRunner().invoke(cli, ["compile"])
    _assert_ok(result)


def test_query_cli_runner_smoke(monkeypatch):
    from kb.query import engine

    def fake_query_wiki(question, *, output_format=None):
        return {
            "answer": "ok",
            "citations": [],
            "source_pages": [],
            "context_pages": [],
        }

    monkeypatch.setattr(engine, "query_wiki", fake_query_wiki)
    result = CliRunner().invoke(cli, ["query", "what is tested?"])
    _assert_ok(result)


def test_lint_cli_runner_smoke(monkeypatch):
    from kb.lint import runner as lint_runner

    def fake_run_all_checks(*, wiki_dir=None, fix=False):
        return {
            "issues": [],
            "summary": {"error": 0, "warning": 0, "info": 0},
            "fixes_applied": [],
        }

    monkeypatch.setattr(lint_runner, "run_all_checks", fake_run_all_checks)
    monkeypatch.setattr(lint_runner, "format_report", lambda report: "Lint Report")
    result = CliRunner().invoke(cli, ["lint"])
    _assert_ok(result)


def test_evolve_cli_runner_smoke(monkeypatch):
    from kb.evolve import analyzer

    def fake_generate_evolution_report():
        return {"suggestions": []}

    monkeypatch.setattr(analyzer, "generate_evolution_report", fake_generate_evolution_report)
    monkeypatch.setattr(analyzer, "format_evolution_report", lambda report: "Evolution Report")
    result = CliRunner().invoke(cli, ["evolve"])
    _assert_ok(result)


def test_mcp_cli_runner_smoke(monkeypatch):
    from kb import mcp_server

    monkeypatch.setattr(mcp_server, "main", lambda: None)
    result = CliRunner().invoke(cli, ["mcp"])
    _assert_ok(result)


def _version_short_circuit_env() -> dict[str, str]:
    """Build a minimal env for the short-circuit subprocess.

    R1 Sonnet fix — copying ``os.environ`` would let a polluted parent
    ``PYTHONPATH`` (e.g. a rogue ``kb/config.py`` on an existing entry) shadow
    our explicit ``<repo>/src`` entry. Build a minimal dict from scratch that
    contains only the keys required to launch Python on this platform.
    """
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": src_path,
    }
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    return env


def _run_version_short_circuit(flag: str) -> subprocess.CompletedProcess[str]:
    code = f"""
import sys
sys.argv = ["kb.cli", "{flag}"]
try:
    import kb.cli
except SystemExit as exc:
    assert exc.code == 0
    assert "kb.config" not in sys.modules
    raise
raise AssertionError("kb.cli import did not short-circuit")
"""
    return subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env=_version_short_circuit_env(),
        cwd=Path(__file__).resolve().parents[1],
    )


def test_version_short_circuit_long():
    result = _run_version_short_circuit("--version")
    assert result.returncode == 0, result.stderr
    assert "kb, version" in result.stdout


def test_version_short_circuit_short():
    result = _run_version_short_circuit("-V")
    assert result.returncode == 0, result.stderr
    assert "kb, version" in result.stdout


# ── CLI boot sweep_orphan_tmp wiring (cycle 43 AC12 fold from test_cycle13_sweep_wiring.py) ─

import time  # noqa: E402  — imported here to keep the canonical-home import block above untouched

from kb import cli as cli_mod  # noqa: E402


class TestCliBootSweep:
    """AC14 — CLI boot sweep wiring.

    The kb.cli:cli group callback sweeps PROJECT_ROOT/.data and WIKI_DIR for
    orphan atomic-write .tmp siblings on every CLI invocation (after the AC30
    --version short-circuit and Click's eager --version/--help callbacks).

    Sub-tests:
    - spy on kb.cli.sweep_orphan_tmp asserts it's called with both deduped
      resolved paths
    - pre-aged .tmp files older than 1h are removed; fresh ones survive
    """

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


# ── Long-error truncation across CLI commands (cycle 56 fold) ─


class TestCliErrorTruncation:
    """Phase 4 CLI long-error truncation contract — every command's user-facing
    error output must elide payloads longer than the truncate() helper's cap.
    """

    def test_ingest_error_truncates_long_message(self, monkeypatch):
        from kb import cli as _cli
        from kb.ingest import pipeline
        from kb.utils.llm import LLMError

        def _raise_long(*args, **kwargs):
            raise LLMError("x" * 2000)

        monkeypatch.setattr(pipeline, "ingest_source", _raise_long)
        runner_cli = CliRunner()
        result = runner_cli.invoke(_cli.cli, ["ingest", "raw/articles/nope.md"])
        output = result.output or ""
        assert "x" * 2000 not in output
        assert "..." in output

    def test_compile_error_truncates_long_message(self, monkeypatch):
        from kb import cli as _cli
        from kb.compile import compiler
        from kb.utils.llm import LLMError

        def _raise_long(*args, **kwargs):
            raise LLMError("y" * 2000)

        monkeypatch.setattr(compiler, "compile_wiki", _raise_long)
        runner_cli = CliRunner()
        result = runner_cli.invoke(_cli.cli, ["compile"])
        output = result.output or ""
        assert "y" * 2000 not in output
        assert "..." in output

    def test_query_error_truncates_long_message(self, monkeypatch):
        from kb import cli as _cli
        from kb.query import engine
        from kb.utils.llm import LLMError

        def _raise_long(*args, **kwargs):
            raise LLMError("z" * 2000)

        monkeypatch.setattr(engine, "query_wiki", _raise_long)
        runner_cli = CliRunner()
        result = runner_cli.invoke(_cli.cli, ["query", "test"])
        output = result.output or ""
        assert "z" * 2000 not in output
        assert "..." in output

    def test_lint_error_truncates_long_message(self, monkeypatch):
        from kb import cli as _cli
        from kb.lint import runner as lint_runner
        from kb.utils.llm import LLMError

        def _raise_long(*args, **kwargs):
            raise LLMError("a" * 2000)

        monkeypatch.setattr(lint_runner, "run_all_checks", _raise_long)
        runner_cli = CliRunner()
        result = runner_cli.invoke(_cli.cli, ["lint"])
        output = result.output or ""
        assert "a" * 2000 not in output
        assert "..." in output

    def test_evolve_error_truncates_long_message(self, monkeypatch):
        from kb import cli as _cli
        from kb.evolve import analyzer
        from kb.utils.llm import LLMError

        def _raise_long(*args, **kwargs):
            raise LLMError("b" * 2000)

        monkeypatch.setattr(analyzer, "generate_evolution_report", _raise_long)
        runner_cli = CliRunner()
        result = runner_cli.invoke(_cli.cli, ["evolve"])
        output = result.output or ""
        assert "b" * 2000 not in output
        assert "..." in output


# ── Phase 3.96 Task 10 — CLI fixes (cycle 57 fold) ──────────────────────────
#
# Folded from tests/test_v0915_task10.py per cycle-56 test_cli.py receiver
# precedent. All 3 classes folded verbatim. Module-level imports
# (CliRunner, kb.cli.{ingest,lint}) re-imported function-locally to keep
# the receiver's import surface minimal and avoid load-order coupling
# (cycle-19 L2 reload-leak avoidance).


class TestCliDuplicateIndicator:
    """Fix 10.1: CLI ingest must show duplicate detection."""

    def test_duplicate_shown_in_output(self, tmp_path, monkeypatch):
        """When ingest_source returns duplicate=True, CLI must display it."""
        from click.testing import CliRunner

        from kb.cli import ingest

        def mock_ingest_source(*args, **kwargs):
            return {
                "source_path": str(tmp_path / "test.md"),
                "source_type": "article",
                "content_hash": "abc123def456",
                "pages_created": [],
                "pages_updated": [],
                "pages_skipped": [],
                "duplicate": True,
            }

        monkeypatch.setattr("kb.ingest.pipeline.ingest_source", mock_ingest_source)

        src = tmp_path / "test.md"
        src.write_text("test content", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(ingest, [str(src)])

        # Should exit successfully (0) on duplicate
        assert result.exit_code == 0
        # Output must contain "Duplicate" (case-insensitive)
        assert "uplicate" in result.output or "Duplicate" in result.output

    def test_normal_ingest_without_duplicate_flag(self, tmp_path, monkeypatch):
        """Normal ingest (no duplicate) should not show duplicate message."""
        from click.testing import CliRunner

        from kb.cli import ingest

        def mock_ingest_source(*args, **kwargs):
            return {
                "source_path": str(tmp_path / "test.md"),
                "source_type": "article",
                "content_hash": "xyz789",
                "pages_created": ["entities/my-entity"],
                "pages_updated": [],
                "pages_skipped": [],
                "duplicate": False,
            }

        monkeypatch.setattr("kb.ingest.pipeline.ingest_source", mock_ingest_source)

        src = tmp_path / "test.md"
        src.write_text("new content", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(ingest, [str(src)])

        assert result.exit_code == 0
        assert "Pages created: 1" in result.output
        # Should NOT show duplicate message
        assert "Duplicate" not in result.output


class TestCliSourceTypesChoice:
    """Fix 10.2: comparison/synthesis must be removed from --type choices."""

    def test_comparison_not_in_choices(self, tmp_path):
        """Verify --type choice does not include 'comparison'."""
        from click.testing import CliRunner

        from kb.cli import ingest

        runner = CliRunner()
        src = tmp_path / "test.md"
        src.write_text("content", encoding="utf-8")

        # Try to use --type comparison; should fail with "Invalid value for '--type'"
        result = runner.invoke(ingest, [str(src), "--type", "comparison"])

        assert result.exit_code != 0
        assert "Invalid value for '--type'" in result.output

    def test_synthesis_not_in_choices(self, tmp_path):
        """Verify --type choice does not include 'synthesis'."""
        from click.testing import CliRunner

        from kb.cli import ingest

        runner = CliRunner()
        src = tmp_path / "test.md"
        src.write_text("content", encoding="utf-8")

        # Try to use --type synthesis; should fail
        result = runner.invoke(ingest, [str(src), "--type", "synthesis"])

        assert result.exit_code != 0
        assert "Invalid value for '--type'" in result.output

    def test_valid_types_accepted(self, tmp_path, monkeypatch):
        """Valid types (article, paper, etc.) should still be accepted."""
        from click.testing import CliRunner

        from kb.cli import ingest

        def mock_ingest_source(*args, **kwargs):
            return {
                "source_path": str(tmp_path / "test.md"),
                "source_type": "article",
                "content_hash": "hash1",
                "pages_created": [],
                "pages_updated": [],
                "pages_skipped": [],
            }

        monkeypatch.setattr("kb.ingest.pipeline.ingest_source", mock_ingest_source)

        src = tmp_path / "test.md"
        src.write_text("content", encoding="utf-8")

        runner = CliRunner()
        # Should accept valid types
        for valid_type in [
            "article",
            "paper",
            "repo",
            "video",
            "podcast",
            "book",
            "dataset",
            "conversation",
        ]:
            result = runner.invoke(ingest, [str(src), "--type", valid_type])
            assert result.exit_code == 0, f"Failed for type {valid_type}"


class TestCliLintExitHandling:
    """Fix 10.3: Verify lint exit handling for error-count checks."""

    def test_lint_exits_1_when_errors_present(self, monkeypatch):
        """Lint should exit with code 1 when report has errors."""
        from click.testing import CliRunner

        from kb.cli import lint

        def mock_run_all_checks(*args, **kwargs):
            return {
                "summary": {
                    "error": 3,  # Has errors
                    "warning": 1,
                },
                "fixes_applied": [],
            }

        def mock_format_report(report):
            return "Found 3 errors, 1 warning"

        monkeypatch.setattr("kb.lint.runner.run_all_checks", mock_run_all_checks)
        monkeypatch.setattr("kb.lint.runner.format_report", mock_format_report)

        runner = CliRunner()
        result = runner.invoke(lint, [])

        assert result.exit_code == 1

    def test_lint_exits_0_when_no_errors(self, monkeypatch):
        """Lint should exit with code 0 when no errors."""
        from click.testing import CliRunner

        from kb.cli import lint

        def mock_run_all_checks(*args, **kwargs):
            return {
                "summary": {
                    "error": 0,
                    "warning": 2,
                },
                "fixes_applied": [],
            }

        def mock_format_report(report):
            return "Found 0 errors, 2 warnings"

        monkeypatch.setattr("kb.lint.runner.run_all_checks", mock_run_all_checks)
        monkeypatch.setattr("kb.lint.runner.format_report", mock_format_report)

        runner = CliRunner()
        result = runner.invoke(lint, [])

        assert result.exit_code == 0

    def test_lint_handles_exception_exit_1(self, monkeypatch):
        """Lint should exit with code 1 on exception."""
        from click.testing import CliRunner

        from kb.cli import lint

        def mock_run_all_checks(*args, **kwargs):
            raise ValueError("Lint failed")

        monkeypatch.setattr("kb.lint.runner.run_all_checks", mock_run_all_checks)

        runner = CliRunner()
        result = runner.invoke(lint, [])

        assert result.exit_code == 1
        assert "Error:" in result.output


# -- Cycle 62 fold from test_v4_11_cli.py --
"""Tests for kb query --format CLI flag."""


from unittest.mock import patch  # noqa: E402,F401,F811

import pytest  # noqa: E402,F401,F811
from click.testing import CliRunner  # noqa: E402,F401,F811

from kb.cli import cli  # noqa: E402,F401,F811


@pytest.fixture
def mocked_query_wiki():
    with patch("kb.query.engine.query_wiki") as m:
        yield m


def test_cli_query_default_format_text(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "RAG is...",
        "citations": [],
        "source_pages": ["concepts/rag"],
    }
    runner = CliRunner()
    result = runner.invoke(cli, ["query", "What is RAG?"])
    assert result.exit_code == 0
    _, kwargs = mocked_query_wiki.call_args
    assert kwargs.get("output_format") in (None, "text")


def test_cli_query_markdown_format(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "RAG is...",
        "citations": [],
        "source_pages": [],
        "output_path": "/tmp/fake.md",
        "output_format": "markdown",
    }
    runner = CliRunner()
    result = runner.invoke(cli, ["query", "What is RAG?", "--format", "markdown"])
    assert result.exit_code == 0
    assert "/tmp/fake.md" in result.output
    _, kwargs = mocked_query_wiki.call_args
    assert kwargs.get("output_format") == "markdown"


def test_cli_query_rejects_invalid_format():
    runner = CliRunner()
    result = runner.invoke(cli, ["query", "q", "--format", "pdf"])
    assert result.exit_code == 2  # Click usage error


def test_cli_query_all_formats_accepted(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "x",
        "citations": [],
        "source_pages": [],
        "output_path": "/tmp/fake",
        "output_format": "markdown",
    }
    runner = CliRunner()
    for fmt in ("text", "markdown", "marp", "html", "chart", "jupyter"):
        res = runner.invoke(cli, ["query", "q", "--format", fmt])
        assert res.exit_code == 0, f"fmt {fmt} failed: {res.output}"


def test_cli_query_surfaces_output_error(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "x",
        "citations": [],
        "source_pages": [],
        "output_error": "simulated failure",
    }
    runner = CliRunner()
    result = runner.invoke(cli, ["query", "q", "--format", "markdown"])
    # Stderr is merged into output by default for CliRunner
    # Check the result captured stderr too
    combined = (result.output or "") + (
        result.stderr_bytes.decode() if hasattr(result, "stderr_bytes") else ""
    )
    assert "simulated failure" in combined or "simulated failure" in result.output
