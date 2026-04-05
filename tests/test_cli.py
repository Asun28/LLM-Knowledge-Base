"""Tests for the CLI commands."""

from unittest.mock import patch

from click.testing import CliRunner

from kb.cli import cli


runner = CliRunner()


def test_cli_version():
    """CLI --version prints version."""
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


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
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
        patch("kb.ingest.pipeline.WIKI_LOG", wiki_dir / "log.md"),
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
