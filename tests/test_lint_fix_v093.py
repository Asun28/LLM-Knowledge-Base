"""Tests for kb lint --fix (dead link auto-fix)."""

from unittest.mock import patch

from click.testing import CliRunner

from kb.cli import cli
from kb.lint.checks import fix_dead_links
from kb.lint.runner import run_all_checks

FRONTMATTER = (
    '---\ntitle: "Page A"\nsource:\n  - "raw/articles/a.md"\n'
    "created: 2026-01-01\nupdated: 2026-01-01\n"
    "type: concept\nconfidence: stated\n---\n\n"
)


def test_fix_dead_links_replaces_broken_wikilink(tmp_wiki):
    """Broken [[concepts/nonexistent]] is replaced with plain text 'nonexistent'."""
    page_a = tmp_wiki / "concepts" / "page-a.md"
    page_a.write_text(
        FRONTMATTER + "# Page A\n\nSee [[concepts/nonexistent]] for details.\n",
        encoding="utf-8",
    )

    fixes = fix_dead_links(tmp_wiki)

    assert len(fixes) >= 1
    content = page_a.read_text(encoding="utf-8")
    assert "[[concepts/nonexistent]]" not in content
    assert "nonexistent" in content  # replaced with basename


def test_fix_dead_links_preserves_display_text(tmp_wiki):
    """[[concepts/nonexistent|My Display Text]] becomes 'My Display Text'."""
    page_a = tmp_wiki / "concepts" / "page-a.md"
    page_a.write_text(
        FRONTMATTER + "# Page A\n\nSee [[concepts/nonexistent|My Display Text]] here.\n",
        encoding="utf-8",
    )

    fixes = fix_dead_links(tmp_wiki)

    assert len(fixes) >= 1
    content = page_a.read_text(encoding="utf-8")
    assert "[[concepts/nonexistent|My Display Text]]" not in content
    assert "My Display Text" in content


def test_fix_dead_links_ignores_valid_links(tmp_wiki):
    """Valid wikilinks are NOT modified by fix_dead_links."""
    # Create the target page so the link is valid
    target = tmp_wiki / "concepts" / "existing.md"
    target.write_text(
        '---\ntitle: "Existing"\nsource:\n  - "raw/articles/b.md"\n'
        "created: 2026-01-01\nupdated: 2026-01-01\n"
        "type: concept\nconfidence: stated\n---\n\n"
        "# Existing\n\nContent here.\n",
        encoding="utf-8",
    )

    page_a = tmp_wiki / "concepts" / "page-a.md"
    original_content = FRONTMATTER + "# Page A\n\nSee [[concepts/existing]] for details.\n"
    page_a.write_text(original_content, encoding="utf-8")

    fixes = fix_dead_links(tmp_wiki)

    # No fixes should have been applied — the link is valid
    assert len(fixes) == 0
    content = page_a.read_text(encoding="utf-8")
    assert "[[concepts/existing]]" in content


def test_run_all_checks_with_fix_true(tmp_wiki, tmp_path):
    """run_all_checks(fix=True) populates fixes_applied when dead links exist."""
    page_a = tmp_wiki / "concepts" / "page-a.md"
    page_a.write_text(
        FRONTMATTER + "# Page A\n\nSee [[concepts/nonexistent]] for details.\n",
        encoding="utf-8",
    )

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(exist_ok=True)

    report = run_all_checks(wiki_dir=tmp_wiki, raw_dir=raw_dir, fix=True)

    assert len(report["fixes_applied"]) >= 1
    assert report["fixes_applied"][0]["check"] == "dead_link_fixed"


def test_run_all_checks_with_fix_false(tmp_wiki, tmp_path):
    """run_all_checks(fix=False) leaves fixes_applied empty."""
    page_a = tmp_wiki / "concepts" / "page-a.md"
    page_a.write_text(
        FRONTMATTER + "# Page A\n\nSee [[concepts/nonexistent]] for details.\n",
        encoding="utf-8",
    )

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(exist_ok=True)

    report = run_all_checks(wiki_dir=tmp_wiki, raw_dir=raw_dir, fix=False)

    assert report["fixes_applied"] == []
    # The dead link issue should still be reported
    dead = [i for i in report["issues"] if i["check"] == "dead_link"]
    assert len(dead) >= 1


def test_lint_cli_fix_flag():
    """CLI 'lint --fix' displays auto-fix results when fixes are applied."""
    mock_report = {
        "checks_run": [{"name": "dead_links", "issues": 1}],
        "total_issues": 1,
        "issues": [
            {
                "check": "dead_link",
                "severity": "error",
                "source": "concepts/page-a",
                "target": "concepts/nonexistent",
                "message": "Broken wikilink: [[concepts/nonexistent]] in concepts/page-a",
            }
        ],
        "summary": {"error": 1, "warning": 0, "info": 0, "verdict_history": None},
        "fixes_applied": [
            {
                "check": "dead_link_fixed",
                "severity": "info",
                "page": "concepts/page-a",
                "target": "concepts/nonexistent",
                "message": "Fixed broken wikilink [[concepts/nonexistent]] in concepts/page-a",
            }
        ],
    }

    runner = CliRunner()
    with patch("kb.lint.runner.run_all_checks", return_value=mock_report) as mock_rac:
        # The command exits with code 1 because there's an error in the report
        result = runner.invoke(cli, ["lint", "--fix"])
        mock_rac.assert_called_once_with(wiki_dir=None, fix=True)

    assert "Auto-fixed 1 issue(s)" in result.output
    assert "Fixed: Fixed broken wikilink" in result.output
