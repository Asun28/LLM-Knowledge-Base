"""Phase 3.96 Task 7 — Review module fixes (v0.9.15)."""


class TestRefinerFrontmatterGuard:
    """Fix 7.1: refine_page must reject empty frontmatter blocks."""

    def test_frontmatter_block_with_keys_rejected(self, tmp_wiki, create_wiki_page):
        """Phase 4.5 HIGH D1: guard requires key:value between fences.

        Empty fences (---\\n---) are allowed (horizontal rules). Only blocks
        containing YAML key: value lines are rejected.
        """
        from kb.review.refiner import refine_page

        create_wiki_page("concepts/test", wiki_dir=tmp_wiki, content="Original.")
        result = refine_page(
            "concepts/test",
            "---\ntitle: Injected\ntype: entity\n---\nReal body",
            wiki_dir=tmp_wiki,
            history_path=tmp_wiki / "history.json",
        )
        assert "error" in result

    def test_normal_horizontal_rule_accepted(self, tmp_wiki, create_wiki_page):
        from kb.review.refiner import refine_page

        create_wiki_page("concepts/test2", wiki_dir=tmp_wiki, content="Original.")
        result = refine_page(
            "concepts/test2",
            "Updated content.\n\n---\n\nMore content.",
            wiki_dir=tmp_wiki,
            history_path=tmp_wiki / "history.json",
        )
        assert "error" not in result


class TestRefinerEmptyContent:
    """Fix 7.2: refine_page must reject empty or whitespace-only content."""

    def test_empty_content_rejected(self, tmp_wiki, create_wiki_page):
        from kb.review.refiner import refine_page

        create_wiki_page("concepts/test", wiki_dir=tmp_wiki, content="Original.")
        result = refine_page(
            "concepts/test",
            "",
            wiki_dir=tmp_wiki,
            history_path=tmp_wiki / "history.json",
        )
        assert "error" in result

    def test_whitespace_only_rejected(self, tmp_wiki, create_wiki_page):
        from kb.review.refiner import refine_page

        create_wiki_page("concepts/test2", wiki_dir=tmp_wiki, content="Original.")
        result = refine_page(
            "concepts/test2",
            "   \n  \n  ",
            wiki_dir=tmp_wiki,
            history_path=tmp_wiki / "history.json",
        )
        assert "error" in result


class TestRefinerAtomicWrite:
    """Fix 7.3: refine_page uses atomic write for page content."""

    def test_successful_write_produces_correct_content(self, tmp_wiki, create_wiki_page):
        from kb.review.refiner import refine_page

        create_wiki_page("concepts/atomic", wiki_dir=tmp_wiki, content="Original content.")
        result = refine_page(
            "concepts/atomic",
            "Updated content.",
            wiki_dir=tmp_wiki,
            history_path=tmp_wiki / "history.json",
        )
        assert "error" not in result
        page_path = tmp_wiki / "concepts/atomic.md"
        written = page_path.read_text(encoding="utf-8")
        assert "Updated content." in written

    def test_history_entry_created_after_successful_write(self, tmp_wiki, create_wiki_page):
        from kb.review.refiner import load_review_history, refine_page

        history_path = tmp_wiki / "history.json"
        create_wiki_page("concepts/atomic2", wiki_dir=tmp_wiki, content="Original.")
        refine_page(
            "concepts/atomic2",
            "New content.",
            revision_notes="test note",
            wiki_dir=tmp_wiki,
            history_path=history_path,
        )
        history = load_review_history(history_path)
        assert len(history) == 1
        assert history[0]["page_id"] == "concepts/atomic2"
        assert history[0]["revision_notes"] == "test note"


class TestPairPageWithSourcesYAMLError:
    """Fix 7.4: pair_page_with_sources handles malformed YAML gracefully."""

    def test_malformed_yaml_returns_error(self, tmp_wiki):
        from kb.review.context import pair_page_with_sources

        page_dir = tmp_wiki / "concepts"
        page_dir.mkdir(parents=True, exist_ok=True)
        bad_page = page_dir / "broken.md"
        # Write a file with malformed YAML frontmatter
        bad_page.write_text(
            "---\ntitle: [unclosed\nsource: raw/x.md\n---\nBody.\n", encoding="utf-8"
        )
        result = pair_page_with_sources("concepts/broken", wiki_dir=tmp_wiki)
        assert "error" in result
        assert result.get("page_id") == "concepts/broken"


class TestVerdictVocabulary:
    """Fix 7.5: build_review_checklist uses pass|warning|fail vocabulary."""

    def test_checklist_uses_correct_verdict_vocabulary(self):
        from kb.review.context import build_review_checklist

        checklist = build_review_checklist()
        # Should use the verdict vocabulary that matches add_verdict() accepted values
        assert "pass | warning | fail" in checklist
        # Should NOT use the old vocabulary
        assert "approve | revise | reject" not in checklist


class TestRefinerCRLF:
    """Fix 7.6: refiner handles CRLF line endings in stored pages."""

    def test_crlf_frontmatter_parsed_correctly(self, tmp_wiki, create_wiki_page):
        from kb.review.refiner import refine_page

        # Create page then manually overwrite with CRLF line endings
        create_wiki_page("concepts/crlf", wiki_dir=tmp_wiki, content="Original.")
        page_path = tmp_wiki / "concepts/crlf.md"
        lf_text = page_path.read_text(encoding="utf-8")
        crlf_text = lf_text.replace("\n", "\r\n")
        page_path.write_bytes(crlf_text.encode("utf-8"))

        result = refine_page(
            "concepts/crlf",
            "Updated body.",
            wiki_dir=tmp_wiki,
            history_path=tmp_wiki / "history.json",
        )
        assert "error" not in result, f"Got error: {result.get('error')}"
        written = page_path.read_text(encoding="utf-8")
        assert "Updated body." in written


class TestRefinerLeadingWhitespaceStripped:
    """Fix 7.7: leading whitespace stripped from updated_content before reconstruction."""

    def test_leading_newlines_stripped_from_body(self, tmp_wiki, create_wiki_page):
        from kb.review.refiner import refine_page

        create_wiki_page("concepts/strip", wiki_dir=tmp_wiki, content="Original.")
        result = refine_page(
            "concepts/strip",
            "\n\nBody with leading newlines.",
            wiki_dir=tmp_wiki,
            history_path=tmp_wiki / "history.json",
        )
        assert "error" not in result
        page_path = tmp_wiki / "concepts/strip.md"
        written = page_path.read_text(encoding="utf-8")
        # After the closing --- of frontmatter there should be exactly one blank line
        # then the body (no multiple leading blank lines from updated_content)
        assert "---\n\nBody with leading newlines." in written
