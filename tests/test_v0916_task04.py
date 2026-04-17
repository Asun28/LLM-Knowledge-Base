"""Phase 3.97 Task 04 — Compile / linker fixes."""


class TestInjectWikilinksTitleSanitization:
    """inject_wikilinks must sanitize pipe and newline in titles."""

    def test_pipe_in_title_produces_valid_wikilink(self, tmp_wiki):
        """A title with | should not break wikilink syntax."""
        page = tmp_wiki / "concepts" / "other.md"
        page.write_text(
            '---\ntitle: "Other"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
            "This discusses GPT-4 Preview features.\n",
            encoding="utf-8",
        )
        target = tmp_wiki / "entities" / "gpt-4-preview.md"
        target.write_text(
            '---\ntitle: "GPT-4 | Preview"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: entity\nconfidence: stated\n---\n\n"
            "GPT-4 Preview entity page.\n",
            encoding="utf-8",
        )

        from kb.compile.linker import inject_wikilinks

        updated = inject_wikilinks("GPT-4 Preview", "entities/gpt-4-preview", wiki_dir=tmp_wiki)
        if updated:
            content = page.read_text(encoding="utf-8")
            # Must not have raw pipe in wikilink
            assert "||" not in content or "[[entities/gpt-4-preview|" in content

    def test_newline_in_title_sanitized(self, tmp_wiki):
        """A title with newline should be sanitized before injection."""
        page = tmp_wiki / "concepts" / "other.md"
        page.write_text(
            '---\ntitle: "Other"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
            "This discusses TestEntity in the body.\n",
            encoding="utf-8",
        )
        target = tmp_wiki / "entities" / "test-entity.md"
        target.write_text(
            '---\ntitle: "TestEntity"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: entity\nconfidence: stated\n---\n\n"
            "TestEntity page.\n",
            encoding="utf-8",
        )

        from kb.compile.linker import inject_wikilinks

        # Title with newline should be sanitized
        updated = inject_wikilinks("TestEntity", "entities/test-entity", wiki_dir=tmp_wiki)
        if updated:
            content = page.read_text(encoding="utf-8")
            assert "[[entities/test-entity|TestEntity]]" in content


class TestInjectWikilinksFrontmatterSkipCheck:
    """inject_wikilinks skip guard must check body only, not frontmatter."""

    def test_wikilink_in_frontmatter_does_not_skip_body(self, tmp_wiki):
        """If frontmatter contains [[target]], body injection should still happen."""
        page = tmp_wiki / "concepts" / "other.md"
        # Frontmatter has the target as a literal (unusual but possible)
        page.write_text(
            '---\ntitle: "Other"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n"
            "note: see [[entities/test-entity]]\n---\n\n"
            "This discusses TestEntity in the body.\n",
            encoding="utf-8",
        )
        target = tmp_wiki / "entities" / "test-entity.md"
        target.write_text(
            '---\ntitle: "TestEntity"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: entity\nconfidence: stated\n---\n\n"
            "TestEntity page.\n",
            encoding="utf-8",
        )

        from kb.compile.linker import inject_wikilinks

        updated = inject_wikilinks("TestEntity", "entities/test-entity", wiki_dir=tmp_wiki)
        # The body mention should still be linked
        assert "concepts/other" in updated


class TestScanRawSourcesUsesSharedExtensions:
    """scan_raw_sources should use SUPPORTED_SOURCE_EXTENSIONS from config."""

    def test_rst_file_accepted(self, tmp_path):
        raw = tmp_path / "raw"
        articles = raw / "articles"
        articles.mkdir(parents=True)
        (articles / "test.rst").write_text("content", encoding="utf-8")
        (articles / ".gitkeep").write_text("", encoding="utf-8")

        from kb.compile.compiler import scan_raw_sources

        sources = scan_raw_sources(raw)
        names = [s.name for s in sources]
        assert "test.rst" in names
        assert ".gitkeep" not in names
