"""Tests for evidence trail sections in wiki pages (Phase 4)."""

from datetime import date

from kb.ingest.evidence import append_evidence_trail, build_evidence_entry


class TestBuildEvidenceEntry:
    def test_basic_entry(self):
        entry = build_evidence_entry(
            source_ref="raw/articles/example.md",
            action="Initial extraction: core concept definition",
        )
        assert entry.startswith(f"- {date.today().isoformat()}")
        assert "raw/articles/example.md" in entry
        assert "Initial extraction" in entry

    def test_custom_date(self):
        entry = build_evidence_entry(
            source_ref="raw/papers/paper.md",
            action="Updated: added formulation",
            entry_date="2026-01-15",
        )
        assert entry.startswith("- 2026-01-15")

    def test_entry_is_single_line(self):
        entry = build_evidence_entry(
            source_ref="raw/articles/a.md",
            action="Some action",
        )
        assert "\n" not in entry.strip()


class TestAppendEvidenceTrail:
    def test_adds_section_to_page_without_trail(self, tmp_path):
        page = tmp_path / "test.md"
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-04-12\nupdated: 2026-04-12\n"
            "type: concept\nconfidence: stated\n---\n\n"
            "# Test\n\nSome content.\n",
            encoding="utf-8",
        )
        append_evidence_trail(page, "raw/articles/a.md", "Initial extraction: definition")
        text = page.read_text(encoding="utf-8")
        assert "## Evidence Trail" in text
        assert "raw/articles/a.md" in text
        assert "Initial extraction: definition" in text
        # Content above trail is preserved
        assert "# Test" in text
        assert "Some content." in text

    def test_appends_to_existing_trail(self, tmp_path):
        page = tmp_path / "test.md"
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-04-12\nupdated: 2026-04-12\n"
            "type: concept\nconfidence: stated\n---\n\n"
            "# Test\n\nContent.\n\n## Evidence Trail\n"
            "- 2026-04-10 | raw/articles/a.md | First entry\n",
            encoding="utf-8",
        )
        append_evidence_trail(page, "raw/articles/b.md", "Updated: new info")
        text = page.read_text(encoding="utf-8")
        # New entry at top (reverse chronological)
        trail_idx = text.index("## Evidence Trail")
        trail = text[trail_idx:]
        lines = [line for line in trail.split("\n") if line.startswith("- ")]
        assert len(lines) == 2
        assert "raw/articles/b.md" in lines[0]  # Newest first
        assert "raw/articles/a.md" in lines[1]

    def test_preserves_frontmatter(self, tmp_path):
        page = tmp_path / "test.md"
        original = (
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-04-12\nupdated: 2026-04-12\n"
            "type: concept\nconfidence: stated\n---\n\n"
            "Body content.\n"
        )
        page.write_text(original, encoding="utf-8")
        append_evidence_trail(page, "raw/articles/a.md", "action")
        text = page.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert 'title: "Test"' in text
