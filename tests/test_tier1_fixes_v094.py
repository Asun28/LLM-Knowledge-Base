"""Tests for v0.9.4 tier-1 fixes: backlinks, coverage, suggest_new_pages, JSON fences."""

from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helper: create a wiki page with proper frontmatter
# ---------------------------------------------------------------------------
def _create_page(path, title="Test", content="# Test\n\nContent"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'---\ntitle: "{title}"\nsource:\n  - "raw/articles/a.md"\n'
        f"created: 2026-01-01\nupdated: 2026-01-01\n"
        f"type: entity\nconfidence: stated\n---\n\n{content}\n",
        encoding="utf-8",
    )


# ===========================================================================
# Fix 1 — build_backlinks() excludes non-existent targets
# ===========================================================================
class TestBuildBacklinksExcludesBroken:
    """build_backlinks should only include targets that actually exist."""

    def test_excludes_broken_links(self, tmp_wiki):
        """Backlinks must not contain entries for pages that don't exist."""
        from kb.compile.linker import build_backlinks

        _create_page(
            tmp_wiki / "entities" / "page-a.md",
            title="Page A",
            content="See [[concepts/existing]] and [[concepts/nonexistent]].",
        )
        _create_page(
            tmp_wiki / "concepts" / "existing.md",
            title="Existing",
            content="# Existing\n\nHello.",
        )

        backlinks = build_backlinks(tmp_wiki)

        assert "concepts/nonexistent" not in backlinks
        assert "concepts/existing" in backlinks
        assert "entities/page-a" in backlinks["concepts/existing"]

    def test_includes_valid_links(self, tmp_wiki):
        """Valid backlinks between two existing pages are recorded."""
        from kb.compile.linker import build_backlinks

        _create_page(
            tmp_wiki / "entities" / "alpha.md",
            title="Alpha",
            content="Links to [[entities/beta]].",
        )
        _create_page(
            tmp_wiki / "entities" / "beta.md",
            title="Beta",
            content="# Beta",
        )

        backlinks = build_backlinks(tmp_wiki)

        assert "entities/beta" in backlinks
        assert "entities/alpha" in backlinks["entities/beta"]


# ===========================================================================
# Fix 2 — analyze_coverage() uses parent directory, not string containment
# ===========================================================================
class TestAnalyzeCoverageParentDir:
    """analyze_coverage should classify pages by their parent directory name."""

    def test_uses_parent_dir_not_string_containment(self, tmp_wiki):
        """A page named 'concepts-overview.md' inside entities/ counts as entity."""
        from kb.evolve.analyzer import analyze_coverage

        _create_page(
            tmp_wiki / "entities" / "concepts-overview.md",
            title="Concepts Overview",
            content="# Overview of concepts",
        )

        result = analyze_coverage(tmp_wiki)

        assert result["by_type"]["entities"] == 1
        assert result["by_type"]["concepts"] == 0

    def test_counts_all_types(self, tmp_wiki):
        """One page in each subdir is counted correctly."""
        from kb.evolve.analyzer import analyze_coverage

        for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
            _create_page(
                tmp_wiki / subdir / f"page-{subdir}.md",
                title=f"Page {subdir}",
            )

        result = analyze_coverage(tmp_wiki)

        for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
            assert result["by_type"][subdir] == 1, f"{subdir} should have count 1"
        assert result["total_pages"] == 5


# ===========================================================================
# Fix 3 — suggest_new_pages() no redundant .removesuffix(".md")
# ===========================================================================
class TestSuggestNewPagesNoRedundantSuffix:
    """suggest_new_pages should not double-strip .md suffix."""

    def test_suggestion_target_has_no_md_suffix(self, tmp_wiki):
        """Suggested target should be 'concepts/test', not 'concepts/test.md'."""
        from kb.evolve.analyzer import suggest_new_pages

        _create_page(
            tmp_wiki / "entities" / "linker.md",
            title="Linker",
            content="See [[concepts/test]] for details.",
        )

        suggestions = suggest_new_pages(tmp_wiki)

        targets = [s["target"] for s in suggestions]
        assert "concepts/test" in targets
        # Ensure no .md suffix leaked through
        for t in targets:
            assert not t.endswith(".md"), f"Target {t!r} should not end with .md"


# ===========================================================================
# Fix 4 — JSON fence stripping handles whitespace after opening fence
# ===========================================================================
class TestJsonFenceStripping:
    """extract_from_source should handle various JSON fence formats."""

    @patch("kb.ingest.extractors.call_llm")
    def test_multiline_fence_with_whitespace(self, mock_llm):
        """Standard multiline ```json fence with indented content."""
        from kb.ingest.extractors import extract_from_source

        mock_llm.return_value = '```json\n  {"title": "test", "summary": "ok"}\n```'

        result = extract_from_source("Some content", "article")

        assert result["title"] == "test"
        assert result["summary"] == "ok"

    @patch("kb.ingest.extractors.call_llm")
    def test_single_line_fence(self, mock_llm):
        """Single-line ```json{...}``` fence (no newline)."""
        from kb.ingest.extractors import extract_from_source

        mock_llm.return_value = '```json{"title":"test","summary":"ok"}```'

        result = extract_from_source("Some content", "article")

        assert result["title"] == "test"
        assert result["summary"] == "ok"

    @patch("kb.ingest.extractors.call_llm")
    def test_single_line_fence_with_space_before_json(self, mock_llm):
        """Single-line ``` json{...}``` — space between ``` and json."""
        from kb.ingest.extractors import extract_from_source

        mock_llm.return_value = '``` json{"title":"test"}```'

        result = extract_from_source("Some content", "article")

        assert result["title"] == "test"
