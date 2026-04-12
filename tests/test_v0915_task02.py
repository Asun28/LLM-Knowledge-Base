"""Phase 3.96 Task 2 — Ingest pipeline fixes."""


class TestAtomicWikiPageWrites:
    """Fix 2.1: Wiki page writes must use atomic_text_write."""

    def test_write_wiki_page_uses_atomic(self, tmp_path, monkeypatch):
        import kb.ingest.pipeline as pipeline

        calls = []

        def tracking_atomic(content, path):
            calls.append(("atomic", str(path)))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        monkeypatch.setattr("kb.ingest.pipeline.atomic_text_write", tracking_atomic)
        page_path = tmp_path / "wiki" / "summaries" / "test.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        pipeline._write_wiki_page(
            page_path, "Test", "summary", "raw/articles/t.md", "stated", "body"
        )
        assert len(calls) == 1
        assert calls[0][0] == "atomic"

    def test_update_existing_page_uses_atomic(self, tmp_path, monkeypatch):
        import kb.ingest.pipeline as pipeline

        page = tmp_path / "concepts" / "test.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\n# Test\n\n## References\n\n"
            "- Mentioned in raw/articles/a.md\n",
            encoding="utf-8",
        )

        calls = []

        def tracking_atomic(content, path):
            calls.append(str(path))
            path.write_text(content, encoding="utf-8")

        monkeypatch.setattr("kb.ingest.pipeline.atomic_text_write", tracking_atomic)
        pipeline._update_existing_page(page, "raw/articles/b.md")
        assert len(calls) == 1


class TestUpdateExistingPageSingleRead:
    """Fix 2.2: _update_existing_page must parse frontmatter from in-memory content."""

    def test_frontmatter_parsed_from_memory(self, tmp_path, monkeypatch):
        import kb.ingest.pipeline as pipeline

        page = tmp_path / "concepts" / "test.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\n# Test\n",
            encoding="utf-8",
        )

        read_count = [0]
        original_read = type(page).read_text

        def counting_read(self, *args, **kwargs):
            read_count[0] += 1
            return original_read(self, *args, **kwargs)

        monkeypatch.setattr(type(page), "read_text", counting_read)
        monkeypatch.setattr(
            "kb.ingest.pipeline.atomic_text_write",
            lambda content, path: path.write_text(content, encoding="utf-8"),
        )
        # Suppress evidence trail to isolate single-read assertion to pipeline core logic
        monkeypatch.setattr("kb.ingest.pipeline.append_evidence_trail", lambda *a, **kw: None)
        pipeline._update_existing_page(page, "raw/articles/b.md")
        assert read_count[0] == 1, f"File read {read_count[0]} times, expected 1"


class TestSourceLinePatternPrecision:
    """Fix 2.3: source ref injection must only target the source: block."""

    def test_tags_list_not_corrupted(self, tmp_path, monkeypatch):
        import kb.ingest.pipeline as pipeline

        page = tmp_path / "concepts" / "test.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            '---\ntitle: "Test"\ntags:\n  - "python"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\n# Test\n\n## References\n\n"
            "- Mentioned in raw/articles/a.md\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "kb.ingest.pipeline.atomic_text_write",
            lambda content, path: path.write_text(content, encoding="utf-8"),
        )
        pipeline._update_existing_page(page, "raw/articles/b.md")
        result = page.read_text(encoding="utf-8")
        lines = result.split("\n")
        source_a_idx = next(i for i, ln in enumerate(lines) if "articles/a.md" in ln)
        source_b_idx = next(i for i, ln in enumerate(lines) if "articles/b.md" in ln)
        tags_idx = next(i for i, ln in enumerate(lines) if '"python"' in ln)
        assert source_b_idx > source_a_idx
        assert source_b_idx != tags_idx + 1


class TestContextBlockDedup:
    """Fix 2.4: context dedup must check section header, not full block."""

    def test_no_duplicate_context_section(self, tmp_path, monkeypatch):
        import kb.ingest.pipeline as pipeline

        page = tmp_path / "entities" / "test.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: entity\n"
            "confidence: stated\n---\n\n# Test\n\n## Context\n\n- Existing\n\n"
            "## References\n\n- Mentioned in raw/articles/a.md\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "kb.ingest.pipeline.atomic_text_write",
            lambda c, p: p.write_text(c, encoding="utf-8"),
        )
        pipeline._update_existing_page(
            page,
            "raw/articles/b.md",
            name="Test",
            extraction={"core_argument": "Test is important"},
        )
        result = page.read_text(encoding="utf-8")
        assert result.count("## Context") == 1


class TestBuildExtractionSchemaGuard:
    """Fix 2.5: clear error on missing extract key."""

    def test_missing_extract_key_raises(self):
        import pytest

        from kb.ingest.extractors import build_extraction_schema

        with pytest.raises(ValueError, match="missing 'extract' key"):
            build_extraction_schema({"name": "test", "description": "test"})


class TestExtractionSchemaRequired:
    """Fix 2.6: at least the first field must be required."""

    def test_first_field_always_required(self):
        from kb.ingest.extractors import build_extraction_schema

        template = {
            "name": "test",
            "description": "test",
            "extract": ["description: Brief description", "entities_mentioned (list): Entities"],
        }
        schema = build_extraction_schema(template)
        assert len(schema["required"]) >= 1
