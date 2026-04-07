"""Tests for stub page detection (v0.9.4 feature)."""

from pathlib import Path

from kb.lint.checks import check_stub_pages
from kb.lint.runner import run_all_checks


def _make_page(wiki_dir: Path, page_id: str, body_content: str) -> Path:
    """Helper: create a wiki page with proper frontmatter."""
    page_path = wiki_dir / f"{page_id}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(
        f'---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
        f"created: 2026-01-01\nupdated: 2026-01-01\n"
        f"type: entity\nconfidence: stated\n---\n\n{body_content}\n",
        encoding="utf-8",
    )
    return page_path


class TestCheckStubPages:
    """Tests for check_stub_pages()."""

    def test_detects_stubs(self, tmp_wiki: Path) -> None:
        """A page with minimal body content is flagged as a stub."""
        _make_page(tmp_wiki, "entities/tiny", "# Title\n\nSome ref")
        issues = check_stub_pages(tmp_wiki)
        assert len(issues) == 1
        assert issues[0]["check"] == "stub_page"
        assert issues[0]["severity"] == "info"
        assert issues[0]["page"] == "entities/tiny"
        assert issues[0]["content_length"] < 100

    def test_skips_substantial_content(self, tmp_wiki: Path) -> None:
        """A page with >100 chars body is NOT flagged."""
        long_body = "This is a substantial wiki page. " * 10  # ~330 chars
        _make_page(tmp_wiki, "entities/substantial", long_body)
        issues = check_stub_pages(tmp_wiki)
        assert len(issues) == 0

    def test_skips_summaries(self, tmp_wiki: Path) -> None:
        """Summaries are auto-generated and should NOT be flagged as stubs."""
        _make_page(tmp_wiki, "summaries/auto-gen", "# Summary")
        issues = check_stub_pages(tmp_wiki)
        assert len(issues) == 0

    def test_custom_threshold(self, tmp_wiki: Path) -> None:
        """Custom min_content_chars threshold is respected."""
        _make_page(tmp_wiki, "entities/medium", "x" * 60)
        _make_page(tmp_wiki, "entities/small", "x" * 40)

        # With threshold=50, only the 40-char page should be flagged
        issues = check_stub_pages(tmp_wiki, min_content_chars=50)
        assert len(issues) == 1
        assert issues[0]["page"] == "entities/small"

    def test_run_all_checks_includes_stubs(self, tmp_wiki: Path, tmp_path: Path) -> None:
        """run_all_checks report includes stub_pages in checks_run."""
        _make_page(tmp_wiki, "entities/stub-test", "# Stub")
        raw_dir = tmp_path / "raw"
        (raw_dir / "articles").mkdir(parents=True, exist_ok=True)
        report = run_all_checks(wiki_dir=tmp_wiki, raw_dir=raw_dir)
        stub_check = [c for c in report["checks_run"] if c["name"] == "stub_pages"]
        assert len(stub_check) == 1
        assert stub_check[0]["issues"] >= 1

    def test_evolve_report_mentions_stubs(self, tmp_wiki: Path) -> None:
        """generate_evolution_report recommendations mention stubs."""
        _make_page(tmp_wiki, "entities/stub-evolve", "# Stub")
        from kb.evolve.analyzer import generate_evolution_report

        report = generate_evolution_report(wiki_dir=tmp_wiki)
        stub_recs = [r for r in report["recommendations"] if "stub" in r.lower()]
        assert len(stub_recs) >= 1
        assert "enrichment" in stub_recs[0].lower()
