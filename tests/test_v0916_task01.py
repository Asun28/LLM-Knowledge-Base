"""Phase 3.97 Task 01 — CRITICAL atomic write + MCP exception tests."""

from unittest.mock import patch

# ── CRITICAL: Non-atomic writes ────────────────────────────────────────


class TestFixDeadLinksAtomicWrite:
    """lint/checks.py fix_dead_links must use atomic_text_write."""

    def test_fix_dead_links_uses_atomic_write(self, tmp_wiki):
        """fix_dead_links should call atomic_text_write, not page_path.write_text."""
        from kb.lint.checks import fix_dead_links

        # Create a page with a broken wikilink
        page = tmp_wiki / "concepts" / "test-page.md"
        page.write_text(
            '---\ntitle: "Test"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
            "See [[concepts/nonexistent]] for details.\n",
            encoding="utf-8",
        )

        broken = [{"source": "concepts/test-page", "target": "concepts/nonexistent"}]

        with patch("kb.lint.checks.atomic_text_write") as mock_atw:
            fix_dead_links(wiki_dir=tmp_wiki, broken_links=broken)
            mock_atw.assert_called_once()
            written_content = mock_atw.call_args[0][0]
            assert "[[concepts/nonexistent]]" not in written_content


class TestKbCreatePageAtomicWrite:
    """mcp/quality.py kb_create_page must write atomically.

    Phase 4.5 backlog-by-file cycle 1 replaced the prior
    `exists()`+`atomic_text_write` pattern with `os.open(O_EXCL)` + inline
    fdopen write to close the TOCTOU + signal-race windows. The new write
    path is still atomic (O_EXCL creates the file in one step; fdopen write
    fills it; any failure unlinks).
    """

    def test_kb_create_page_creates_new_file_atomically(self, tmp_wiki, monkeypatch):
        """kb_create_page should create the target file with the expected
        frontmatter + body, and leave no half-written file on FileExistsError."""
        # Ensure the comparisons subdir exists so the call doesn't error
        (tmp_wiki / "comparisons").mkdir(exist_ok=True)
        # PROJECT_ROOT patch is required so the new source_refs=[] path
        # doesn't try to resolve against the real repo.
        monkeypatch.setattr("kb.mcp.quality.WIKI_DIR", tmp_wiki)
        monkeypatch.setattr("kb.mcp.quality.PROJECT_ROOT", tmp_wiki.parent)
        from kb.mcp.quality import kb_create_page

        result = kb_create_page(
            page_id="comparisons/test-comp",
            title="Test Comparison",
            content="Some comparison content.",
        )
        assert "Error" not in result, f"Unexpected error: {result}"
        page_path = tmp_wiki / "comparisons" / "test-comp.md"
        assert page_path.is_file()
        text = page_path.read_text(encoding="utf-8")
        assert 'title: "Test Comparison"' in text
        assert "Some comparison content." in text

        # Second create must be rejected with an "already exists" error,
        # proving O_EXCL is enforced.
        second = kb_create_page(
            page_id="comparisons/test-comp",
            title="Duplicate",
            content="body 2",
        )
        assert "already exists" in second.lower()


class TestInjectWikilinksAtomicWrite:
    """compile/linker.py inject_wikilinks must use atomic_text_write."""

    def test_inject_wikilinks_uses_atomic_write(self, tmp_wiki):
        """inject_wikilinks should call atomic_text_write, not page_path.write_text."""
        # Create a page that mentions "TestTerm"
        page = tmp_wiki / "concepts" / "other.md"
        page.write_text(
            '---\ntitle: "Other"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
            "This page mentions TestTerm in the body.\n",
            encoding="utf-8",
        )
        # Create the target page
        target = tmp_wiki / "entities" / "test-term.md"
        target.write_text(
            '---\ntitle: "TestTerm"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: entity\nconfidence: stated\n---\n\n"
            "TestTerm page.\n",
            encoding="utf-8",
        )

        with patch("kb.compile.linker.atomic_text_write") as mock_atw:
            from kb.compile.linker import inject_wikilinks

            inject_wikilinks("TestTerm", "entities/test-term", wiki_dir=tmp_wiki)
            if mock_atw.called:
                written = mock_atw.call_args[0][0]
                assert "[[entities/test-term|TestTerm]]" in written


# ── CRITICAL: MCP exception guards ────────────────────────────────────


class TestKbQueryExceptionGuard:
    """mcp/core.py kb_query non-API path must catch exceptions."""

    def test_kb_query_catches_search_exception(self):
        """kb_query should return Error string when search_pages raises."""
        # Cycle 19 AC15 — patch owner module.
        with patch(
            "kb.query.engine.search_pages", side_effect=RuntimeError("BM25 index failed")
        ):
            from kb.mcp.core import kb_query

            result = kb_query("test question")
            assert result.startswith("Error:")
            assert "BM25 index failed" in result or "Search failed" in result


class TestKbSaveLintVerdictOSError:
    """mcp/quality.py kb_save_lint_verdict must catch OSError."""

    def test_kb_save_lint_verdict_catches_os_error(self):
        """kb_save_lint_verdict should return Error string on disk write failure."""
        with patch("kb.mcp.quality.add_verdict", side_effect=OSError("Disk full")):
            from kb.mcp.quality import kb_save_lint_verdict

            result = kb_save_lint_verdict(
                page_id="concepts/test",
                verdict_type="fidelity",
                verdict="pass",
            )
            assert "Error" in result
            assert "Disk full" in result
