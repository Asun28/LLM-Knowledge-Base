"""kb_lint MCP signature: bundled fix CLAUDE.md:245 (--fix support) + augment kwargs + wiki_dir."""
import inspect


def test_kb_lint_accepts_all_new_kwargs():
    from kb.mcp.health import kb_lint
    sig = inspect.signature(kb_lint)
    params = sig.parameters
    assert "fix" in params
    assert "augment" in params
    assert "dry_run" in params
    assert "execute" in params
    assert "auto_ingest" in params
    assert "max_gaps" in params
    assert "wiki_dir" in params
    # All defaults
    assert params["fix"].default is False
    assert params["augment"].default is False
    assert params["dry_run"].default is False
    assert params["execute"].default is False
    assert params["auto_ingest"].default is False
    assert params["max_gaps"].default == 5
    assert params["wiki_dir"].default is None


def test_kb_lint_default_call_unchanged_behavior(tmp_project, create_wiki_page):
    """Calling kb_lint() with no args still runs the standard lint report."""
    from kb.mcp.health import kb_lint
    create_wiki_page(
        page_id="entities/foo", title="Foo",
        content="A" * 500, wiki_dir=tmp_project / "wiki", page_type="entity",
    )
    report = kb_lint(wiki_dir=str(tmp_project / "wiki"))
    assert "Wiki Lint Report" in report
    assert "## Augment Summary" not in report  # only when augment=True


def test_kb_lint_augment_appends_summary_section(tmp_project, create_wiki_page, monkeypatch):
    """kb_lint(augment=True) appends ## Augment Summary to the report."""
    from kb.mcp.health import kb_lint
    monkeypatch.setattr("kb.lint._augment_manifest.MANIFEST_DIR", tmp_project / ".data")
    create_wiki_page(
        page_id="entities/foo", title="Foo",
        content="A" * 500, wiki_dir=tmp_project / "wiki", page_type="entity",
    )
    # No stubs → augment will examine 0 gaps, but should still append the section
    report = kb_lint(augment=True, wiki_dir=str(tmp_project / "wiki"))
    assert "## Augment Summary" in report
