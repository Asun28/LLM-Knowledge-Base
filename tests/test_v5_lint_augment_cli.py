"""CLI: kb lint --augment / --execute / --auto-ingest / --max-gaps / --dry-run."""

from click.testing import CliRunner


def test_cli_lint_augment_propose_default(tmp_project, create_wiki_page):
    from kb.cli import cli

    create_wiki_page(
        page_id="entities/foo",
        title="Foo",
        content="A" * 500,
        wiki_dir=tmp_project / "wiki",
        page_type="entity",
    )
    runner = CliRunner()
    # No stubs eligible — should still succeed and emit augment summary
    result = runner.invoke(cli, ["lint", "--augment", "--wiki-dir", str(tmp_project / "wiki")])
    assert result.exit_code == 0, result.output
    assert "Augment Summary" in result.output


def test_cli_lint_augment_dry_run_does_not_write(tmp_project, create_wiki_page):
    from kb.cli import cli

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["lint", "--augment", "--dry-run", "--wiki-dir", str(tmp_project / "wiki")],
    )
    assert result.exit_code == 0
    assert not (tmp_project / "wiki" / "_augment_proposals.md").exists()


def test_cli_lint_max_gaps_validation(tmp_project):
    from kb.cli import cli

    runner = CliRunner()
    # Above hard ceiling (10) → must fail
    result = runner.invoke(
        cli,
        [
            "lint",
            "--augment",
            "--max-gaps",
            "20",
            "--wiki-dir",
            str(tmp_project / "wiki"),
        ],
    )
    assert result.exit_code != 0
    assert "max_gaps" in result.output.lower() or "max-gaps" in result.output.lower()


def test_cli_lint_execute_without_augment_errors(tmp_project):
    from kb.cli import cli

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["lint", "--execute", "--wiki-dir", str(tmp_project / "wiki")],
    )
    assert result.exit_code != 0
    assert "augment" in result.output.lower()


def test_cli_lint_auto_ingest_without_execute_errors(tmp_project):
    from kb.cli import cli

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "lint",
            "--augment",
            "--auto-ingest",
            "--wiki-dir",
            str(tmp_project / "wiki"),
        ],
    )
    assert result.exit_code != 0
    assert "execute" in result.output.lower() or "auto-ingest" in result.output.lower()
