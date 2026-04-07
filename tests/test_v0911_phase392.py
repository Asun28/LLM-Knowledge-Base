"""Tests for Phase 3.92 backlog fixes (v0.9.11)."""

from pathlib import Path


# ── Task 2: Review history 10k cap ──────────────────────────────


class TestReviewHistoryCap:
    """review/refiner.py must cap review history at MAX_REVIEW_HISTORY_ENTRIES."""

    def test_review_history_capped_at_limit(self, tmp_path):
        """refine_page caps history at MAX_REVIEW_HISTORY_ENTRIES entries."""
        from kb.config import MAX_REVIEW_HISTORY_ENTRIES
        from kb.review.refiner import load_review_history, save_review_history

        history_path = tmp_path / "review_history.json"

        # Pre-populate with MAX entries
        entries = [
            {"timestamp": f"2026-01-01T00:00:{i % 60:02d}", "page_id": f"p{i}", "status": "applied"}
            for i in range(MAX_REVIEW_HISTORY_ENTRIES)
        ]
        save_review_history(entries, history_path)

        # Create a wiki page to refine
        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        page = wiki_dir / "concepts" / "test.md"
        page.write_text(
            "---\ntitle: Test\nsource:\n  - raw/articles/a.md\n"
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\nBody.",
            encoding="utf-8",
        )

        from kb.review.refiner import refine_page

        refine_page(
            "concepts/test",
            "Updated body.",
            revision_notes="test cap",
            wiki_dir=wiki_dir,
            history_path=history_path,
        )

        history = load_review_history(history_path)
        assert len(history) == MAX_REVIEW_HISTORY_ENTRIES, (
            f"Expected {MAX_REVIEW_HISTORY_ENTRIES} entries, got {len(history)}"
        )


# ── Task 3: MCP browse outer try/except ─────────────────────────


class TestMcpBrowseSafety:
    """kb_read_page and kb_list_sources must not let OSError escape to MCP client."""

    def test_kb_read_page_ioerror_returns_error_string(self, tmp_path, monkeypatch):
        """kb_read_page returns 'Error: ...' string when read_text raises OSError."""
        from unittest.mock import patch

        from kb.mcp import browse

        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        page = wiki_dir / "concepts" / "test.md"
        page.write_text(
            "---\ntitle: T\nsource:\n  - raw/articles/a.md\ncreated: 2026-01-01\n"
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\nBody.",
            encoding="utf-8",
        )
        monkeypatch.setattr(browse, "WIKI_DIR", wiki_dir)

        with patch("pathlib.Path.read_text", side_effect=OSError("disk error")):
            result = browse.kb_read_page("concepts/test")

        assert result.startswith("Error:"), f"Expected error string, got: {result!r}"

    def test_kb_list_sources_ioerror_returns_error_string(self, tmp_path, monkeypatch):
        """kb_list_sources returns 'Error: ...' string when iterdir raises PermissionError."""
        from unittest.mock import patch

        from kb.mcp import browse

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        monkeypatch.setattr(browse, "RAW_DIR", raw_dir)

        with patch("pathlib.Path.iterdir", side_effect=PermissionError("no access")):
            result = browse.kb_list_sources()

        assert result.startswith("Error:"), f"Expected error string, got: {result!r}"


# ── Task 4: fix_dead_links no phantom entries ─────────────────────


class TestFixDeadLinksNoPhantom:
    """fix_dead_links must not append audit entries for targets absent from page text."""

    def test_no_phantom_entry_when_pattern_does_not_match(self, tmp_wiki):
        """If broken link record exists but text lacks it, no fix entry is produced."""
        from unittest.mock import patch

        from kb.lint.checks import fix_dead_links

        # Create a page with NO [[wikilinks]] at all
        page = tmp_wiki / "concepts" / "clean.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            "---\ntitle: Clean\nsource:\n  - raw/articles/a.md\ncreated: 2026-01-01\n"
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\nNo links here.",
            encoding="utf-8",
        )

        # Inject a fake broken-link record pointing at this page
        # with a target NOT present in the page body
        fake_result = {
            "total_links": 1,
            "resolved": 0,
            "broken": [{"source": "concepts/clean", "target": "nonexistent/page"}],
        }
        with patch("kb.lint.checks.resolve_wikilinks", return_value=fake_result):
            fixes = fix_dead_links(tmp_wiki)

        assert fixes == [], f"Expected no phantom fixes, got: {fixes}"


# ── Task 5: inject_wikilinks special-char boundary fix ──────────


class TestInjectWikilinksSpecialChars:
    """inject_wikilinks must handle titles starting/ending with non-word chars."""

    def _make_page(self, wiki_dir, page_id: str, body: str):
        parts = page_id.split("/")
        d = wiki_dir
        for p in parts[:-1]:
            d = d / p
        d.mkdir(parents=True, exist_ok=True)
        page = d / f"{parts[-1]}.md"
        page.write_text(
            f"---\ntitle: {parts[-1]}\nsource:\n  - raw/articles/a.md\n"
            f"created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n{body}",
            encoding="utf-8",
        )
        return page

    def test_inject_cxx_title(self, tmp_wiki):
        """Titles ending with non-word chars (C++) are injected correctly."""
        from kb.compile.linker import inject_wikilinks

        self._make_page(tmp_wiki, "concepts/target", "")
        source_page = self._make_page(
            tmp_wiki, "concepts/source", "We use C++ for performance."
        )

        updated = inject_wikilinks("C++", "concepts/target", wiki_dir=tmp_wiki)

        content = source_page.read_text(encoding="utf-8")
        assert "[[concepts/target|C++]]" in content, f"Wikilink not injected:\n{content}"
        assert "concepts/source" in updated

    def test_inject_dotnet_title(self, tmp_wiki):
        """Titles starting with non-word chars (.NET) are injected correctly."""
        from kb.compile.linker import inject_wikilinks

        self._make_page(tmp_wiki, "concepts/target", "")
        source_page = self._make_page(
            tmp_wiki, "concepts/source", "The .NET ecosystem is large."
        )

        updated = inject_wikilinks(".NET", "concepts/target", wiki_dir=tmp_wiki)

        content = source_page.read_text(encoding="utf-8")
        assert "[[concepts/target|.NET]]" in content, f"Wikilink not injected:\n{content}"
        assert "concepts/source" in updated
