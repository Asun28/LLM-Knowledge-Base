"""CLI: kb lint --augment / --execute / --auto-ingest / --max-gaps / --dry-run."""

from click.testing import CliRunner


def _entry_names(path):
    return {p.name for p in path.iterdir()} if path.exists() else set()


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


def test_cycle12_ac12_augment_execute_wiki_dir_containment(
    tmp_project, create_wiki_page, monkeypatch
):
    from kb import config
    from kb.cli import cli
    from kb.lint import augment
    from kb.lint.fetcher import FetchResult

    wiki = tmp_project / "wiki"
    raw = tmp_project / "raw"

    create_wiki_page(
        page_id="entities/cycle12-target",
        title="Cycle Twelve Target",
        content="Brief.",
        wiki_dir=wiki,
        page_type="entity",
    )
    create_wiki_page(
        page_id="concepts/cycle12-linker",
        title="Cycle Twelve Linker",
        content="See [[entities/cycle12-target]] for the containment case. " * 5,
        wiki_dir=wiki,
        page_type="concept",
    )

    project_raw_before = _entry_names(config.PROJECT_ROOT / "raw")
    project_data_before = _entry_names(config.PROJECT_ROOT / ".data")

    monkeypatch.setattr(augment, "RAW_DIR", raw)
    monkeypatch.setattr(
        augment,
        "_propose_urls",
        lambda *, stub, purpose_text: {
            "action": "propose",
            "urls": ["https://en.wikipedia.org/wiki/Cycle_Twelve_Target"],
            "rationale": "cycle12 deterministic proposal",
        },
    )
    monkeypatch.setattr("kb.lint.augment._relevance_score", lambda **kwargs: 0.95)

    def fake_fetch(self, url, *, respect_robots=True):
        return FetchResult(
            status="ok",
            content="Cycle twelve target content.",
            extracted_markdown="Cycle twelve target content. " * 20,
            content_type="text/html",
            bytes=128,
            reason=None,
            url=url,
        )

    monkeypatch.setattr("kb.lint.fetcher.AugmentFetcher.fetch", fake_fetch)

    runner = CliRunner()
    propose = runner.invoke(cli, ["lint", "--augment", "--wiki-dir", str(wiki)])
    assert propose.exit_code == 0, propose.output
    assert (wiki / "_augment_proposals.md").exists()

    execute = runner.invoke(
        cli,
        ["lint", "--augment", "--execute", "--wiki-dir", str(wiki)],
    )
    assert execute.exit_code == 0, execute.output

    assert list((raw / "articles").glob("cycle-twelve-target*.md"))
    assert list((tmp_project / ".data").glob("augment-run-*.json"))
    assert _entry_names(config.PROJECT_ROOT / "raw") == project_raw_before
    assert _entry_names(config.PROJECT_ROOT / ".data") == project_data_before


def test_cycle12_ac12_execute_without_propose_is_rejected(tmp_project, monkeypatch):
    """R1 edge-case negative pin: `--execute` must not proceed when no
    `_augment_proposals.md` exists (gate 2/3 short-circuit at augment.py:605-625).

    Exercises the same `--wiki-dir` surface as the positive test but without the
    propose phase; verifies the execute run is a no-op rather than silently
    fetching URLs, and that no raw / .data / manifest writes occur anywhere.
    """
    from kb import config
    from kb.cli import cli
    from kb.lint import augment

    wiki = tmp_project / "wiki"
    raw = tmp_project / "raw"

    # Must not have a proposals file — this is the precondition under test.
    assert not (wiki / "_augment_proposals.md").exists()

    # Redirect augment's raw_dir the same way the positive test does so a
    # hypothetical regression (writes despite missing proposals) would land
    # under tmp, not real PROJECT_ROOT.
    monkeypatch.setattr(augment, "RAW_DIR", raw)

    project_raw_before = _entry_names(config.PROJECT_ROOT / "raw")
    project_data_before = _entry_names(config.PROJECT_ROOT / ".data")
    tmp_data_before = _entry_names(tmp_project / ".data")

    runner = CliRunner()
    result = runner.invoke(cli, ["lint", "--augment", "--execute", "--wiki-dir", str(wiki)])

    # Short-circuit path is non-erroring — CLI prints the summary and exits 0.
    assert result.exit_code == 0, result.output
    assert "no proposals file" in result.output.lower() or "propose" in result.output.lower()

    # No raw artefacts written anywhere.
    assert not list((raw / "articles").glob("*.md"))
    # No manifest written anywhere under tmp/.data or real .data.
    assert _entry_names(tmp_project / ".data") == tmp_data_before
    assert _entry_names(config.PROJECT_ROOT / "raw") == project_raw_before
    assert _entry_names(config.PROJECT_ROOT / ".data") == project_data_before
