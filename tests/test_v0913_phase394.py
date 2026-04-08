"""Tests for Phase 3.94 backlog fixes (v0.9.13)."""

import pytest

# ── Task 1: BM25 & Query Engine ─────────────────────────────────────────────


class TestBM25DuplicateTokens:
    def test_duplicate_tokens_do_not_inflate_score(self):
        from kb.query.bm25 import BM25Index

        docs = [["neural", "network", "training"], ["python", "code"]]
        index = BM25Index(docs)
        score_single = index.score(["neural"])[0]
        score_double = index.score(["neural", "neural"])[0]
        assert score_single == score_double, (
            f"Duplicate tokens inflated score: single={score_single}, double={score_double}"
        )

    def test_unique_tokens_still_sum_correctly(self):
        from kb.query.bm25 import BM25Index

        docs = [["neural", "network"], ["python", "code"]]
        index = BM25Index(docs)
        score_two = index.score(["neural", "network"])[0]
        score_one = index.score(["neural"])[0]
        assert score_two > score_one


class TestQueryEngineMaxResults:
    def test_max_results_clamped_at_library_level(self, monkeypatch):
        """search_pages must not return more than MAX_SEARCH_RESULTS pages."""
        from kb.config import MAX_SEARCH_RESULTS
        from kb.query.engine import search_pages

        # Create MAX_SEARCH_RESULTS + 10 fake pages, all matching the query
        fake_pages = [
            {
                "id": f"concepts/fake-{i}",
                "path": f"wiki/concepts/fake-{i}.md",
                "title": f"Fake Concept {i}",
                "type": "concept",
                "confidence": "stated",
                "sources": [],
                "created": "2026-01-01",
                "updated": "2026-01-01",
                "content": "neural network deep learning",
                "raw_content": "neural network deep learning",
            }
            for i in range(MAX_SEARCH_RESULTS + 10)
        ]
        monkeypatch.setattr("kb.query.engine.load_all_pages", lambda *a, **kw: fake_pages)

        results = search_pages("neural network", max_results=9999)
        assert len(results) <= MAX_SEARCH_RESULTS, (
            f"Expected at most {MAX_SEARCH_RESULTS} results, got {len(results)}"
        )


class TestQueryContextTopPageWarning:
    def test_warns_when_top_page_excluded_by_limit(self, caplog):
        import logging

        from kb.query.engine import _build_query_context

        big_page = {
            "id": "concepts/big",
            "type": "concept",
            "confidence": "stated",
            "title": "Big Page",
            "content": "x" * 1000,
        }
        small_page = {
            "id": "concepts/small",
            "type": "concept",
            "confidence": "stated",
            "title": "Small Page",
            "content": "y" * 10,
        }
        with caplog.at_level(logging.WARNING, logger="kb.query.engine"):
            _build_query_context([big_page, small_page], max_chars=100)
        assert any("big" in r.message.lower() for r in caplog.records), (
            "Expected WARNING mentioning excluded top-page 'big'"
        )


class TestCitationsWikilinkNormalization:
    def test_wikilink_wrapped_path_extracted(self):
        from kb.query.citations import extract_citations

        text = "See [source: [[concepts/rag]]] for details."
        citations = extract_citations(text)
        paths = [c["path"] for c in citations]
        assert "concepts/rag" in paths, f"Expected 'concepts/rag' in {paths}"

    def test_plain_path_still_extracted(self):
        from kb.query.citations import extract_citations

        text = "See [source: concepts/rag] for details."
        citations = extract_citations(text)
        assert len(citations) == 1
        assert citations[0]["path"] == "concepts/rag"


# ── Task 2: Lint Runner, Checks, Verdicts ───────────────────────────────────


class TestDeadLinkFilterAfterFix:
    """lint/runner.py run_all_checks: fixed dead links removed from report."""

    def test_fixed_links_excluded_from_report(self, tmp_wiki, create_wiki_page):
        """After --fix, dead links that were fixed must not appear in the report."""
        from kb.lint.runner import run_all_checks

        # Create a page that links to a non-existent page
        create_wiki_page(
            page_id="concepts/linker",
            title="Linker",
            content="See [[concepts/nonexistent]] for more.",
            wiki_dir=tmp_wiki,
        )

        report = run_all_checks(wiki_dir=tmp_wiki, fix=True)
        dead_link_issues = [
            i
            for i in report["issues"]
            if i.get("check") == "dead_link" and "nonexistent" in i.get("target", "")
        ]
        assert len(dead_link_issues) == 0, (
            f"Fixed dead link still appears in report: {dead_link_issues}"
        )


class TestStalenessDatetimeBug:
    """lint/checks.py check_staleness: handles datetime.datetime updated field."""

    def test_staleness_does_not_raise_for_datetime_updated(self, tmp_wiki):
        """check_staleness must not crash when python-frontmatter parses updated as datetime."""
        from kb.lint.checks import check_staleness

        # Write a page with a full ISO datetime string that frontmatter parses as datetime
        page_dir = tmp_wiki / "concepts"
        page_dir.mkdir(exist_ok=True)
        page_path = page_dir / "datetime-page.md"
        page_path.write_text(
            "---\n"
            "title: Datetime Page\n"
            'source:\n  - "raw/articles/src.md"\n'
            "created: 2025-01-01\n"
            "updated: 2025-01-01T12:00:00\n"
            "type: concept\n"
            "confidence: stated\n"
            "---\n\nContent here.\n",
            encoding="utf-8",
        )
        # Should not raise TypeError
        issues = check_staleness(tmp_wiki)
        # The result is a list — no exception means pass
        assert isinstance(issues, list)


class TestVerdictPathTraversal:
    """lint/verdicts.py add_verdict: rejects path traversal in page_id."""

    def test_add_verdict_rejects_path_traversal(self, tmp_path):
        """add_verdict must raise ValueError for page_ids with '..' or leading '/'."""
        import pytest

        from kb.lint.verdicts import add_verdict

        with pytest.raises(ValueError, match="Invalid page_id"):
            add_verdict("../etc/passwd", "fidelity", "pass", path=tmp_path / "v.json")

        with pytest.raises(ValueError, match="Invalid page_id"):
            add_verdict("/absolute/path", "fidelity", "pass", path=tmp_path / "v.json")


class TestVerdictNotesCap:
    """lint/verdicts.py add_verdict: notes length is capped."""

    def test_add_verdict_rejects_oversized_notes(self, tmp_path):
        """add_verdict must raise ValueError when notes exceed MAX_NOTES_LEN."""
        import pytest

        from kb.lint.verdicts import add_verdict

        with pytest.raises(ValueError, match="Notes too long"):
            add_verdict(
                "concepts/test",
                "fidelity",
                "pass",
                notes="x" * 2001,
                path=tmp_path / "v.json",
            )


# ── Task 3: Ingest Pipeline HIGH ─────────────────────────────────────────────


class TestUpdateExistingPageFrontmatterOnly:
    """ingest/pipeline.py _update_existing_page: regex scoped to frontmatter only."""

    def test_body_matching_line_does_not_corrupt_frontmatter(self, tmp_wiki):
        """Source entry must be inserted in frontmatter, not mid-body."""

        from kb.ingest.pipeline import _update_existing_page

        page_dir = tmp_wiki / "concepts"
        page_dir.mkdir(exist_ok=True)
        page_path = page_dir / "test-page.md"
        # Body contains a line that matches the source-entry pattern
        page_path.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/first.md"\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
            '  - "raw/articles/body-line.md"\n\nSome body content.\n',
            encoding="utf-8",
        )
        _update_existing_page(page_path, "raw/articles/second.md")
        content = page_path.read_text(encoding="utf-8")
        # New source must appear inside the frontmatter block (before the closing ---)
        fm_end = content.index("---\n\n")
        assert "raw/articles/second.md" in content[: fm_end + 5], (
            "New source entry not found in frontmatter"
        )
        # The body must NOT have an extra YAML source-list entry (  - "...") for second.md
        # (A reference in ## References is expected and acceptable)
        body = content[fm_end + 5 :]
        source_list_entry = '  - "raw/articles/second.md"'
        assert source_list_entry not in body, (
            f"YAML source entry was incorrectly inserted into the body: {body!r}"
        )


class TestProcessItemBatchTypeGuard:
    """ingest/pipeline.py _process_item_batch: non-string items are skipped."""

    def test_none_in_list_does_not_crash(self, tmp_wiki):
        """A None element in items_raw must be skipped, not raise AttributeError."""
        from kb.ingest.pipeline import _process_item_batch

        # None element in the middle
        created, updated, skipped, _, _ = _process_item_batch(
            [None, "ValidEntity", 42, "AnotherEntity"],
            "entities_mentioned",
            50,
            "entity",
            "raw/articles/test.md",
            {"title": "Test"},
            wiki_dir=tmp_wiki,
        )
        # Only valid strings should produce pages
        entity_ids = created + updated
        assert any("validentity" in p for p in entity_ids), "ValidEntity not created"
        assert any("anotherentity" in p for p in entity_ids), "AnotherEntity not created"


class TestIngestSourceEmptySlug:
    """ingest/pipeline.py ingest_source: empty slug triggers fallback, not hidden file."""

    def test_punctuation_only_title_uses_stem_fallback(self, tmp_project):
        """A title like '???' must not create 'wiki/summaries/.md'."""
        from unittest.mock import patch

        from kb.ingest.pipeline import ingest_source

        raw_dir = tmp_project / "raw"
        wiki_dir = tmp_project / "wiki"
        raw_path = raw_dir / "articles" / "punc-title.md"
        raw_path.write_text("# ???\n\nSome content about punctuation.\n", encoding="utf-8")

        extraction = {
            "title": "???",  # slugifies to empty string
            "entities_mentioned": [],
            "concepts_mentioned": [],
        }
        with (
            patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
            patch("kb.utils.paths.RAW_DIR", raw_dir),
            patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
            patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
            patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
            patch("kb.ingest.pipeline.append_wiki_log"),
            patch("kb.ingest.pipeline._is_duplicate_content", return_value=False),
            patch("kb.compile.compiler.load_manifest", return_value={}),
            patch("kb.compile.compiler.save_manifest"),
        ):
            result = ingest_source(raw_path, "article", extraction=extraction)
        # Summary must be created with a non-empty slug (fallback to stem)
        assert result["pages_created"] or result["pages_updated"]
        hidden_md = wiki_dir / "summaries" / ".md"
        assert not hidden_md.exists(), "Hidden .md file must not be created"


# ── Task 4: Compile Linker ───────────────────────────────────────────────────


class TestInjectWikilinksNestedGuardWarning:
    """compile/linker.py inject_wikilinks: warns when guard blocks injection."""

    def test_unmatched_bracket_does_not_silently_skip_all(self, tmp_wiki, caplog, create_wiki_page):
        """An unmatched [[ earlier in body must not silently suppress all injections."""
        import logging

        from kb.compile.linker import inject_wikilinks

        # Create a target page
        create_wiki_page(
            page_id="concepts/rag",
            title="RAG",
            content="Retrieval-augmented generation.",
            wiki_dir=tmp_wiki,
        )
        # Create a source page with an unmatched [[ before the mention of RAG
        source_dir = tmp_wiki / "concepts"
        src_path = source_dir / "other-concept.md"
        src_path.write_text(
            '---\ntitle: "Other"\nsource:\n  - "raw/articles/s.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
            "Broken bracket [[unclosed somewhere. RAG is a technique.\n",
            encoding="utf-8",
        )
        # The guard fires because RAG appears after an unmatched [[
        # The fix must emit a WARNING log — not silently swallow the skip
        with caplog.at_level(logging.WARNING, logger="kb.compile.linker"):
            result = inject_wikilinks("RAG", "concepts/rag", wiki_dir=tmp_wiki)
        assert isinstance(result, list)
        assert any(
            "unmatched" in r.message.lower() or "skipping" in r.message.lower()
            for r in caplog.records
            if r.levelno >= logging.WARNING
        ), "Expected a WARNING log about unmatched [[ / skipped replacement, got: " + str(
            [r.message for r in caplog.records]
        )


class TestInjectWikilinksLowercaseTarget:
    """compile/linker.py inject_wikilinks: injected wikilink uses consistent casing."""

    def test_injected_wikilink_uses_lowercase_page_id(self, tmp_wiki, create_wiki_page):
        """Injected [[target_page_id|Title]] must use lowercased target_page_id."""
        from kb.compile.linker import inject_wikilinks

        create_wiki_page(
            page_id="concepts/rag",
            title="RAG",
            content="Retrieval-augmented generation.",
            wiki_dir=tmp_wiki,
        )
        source_dir = tmp_wiki / "entities"
        source_dir.mkdir(exist_ok=True)
        src_path = source_dir / "gpt4.md"
        src_path.write_text(
            '---\ntitle: "GPT-4"\nsource:\n  - "raw/articles/s.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: entity\nconfidence: stated\n---\n\n"
            "RAG is used with GPT-4 for retrieval.\n",
            encoding="utf-8",
        )
        # Pass mixed-case target_page_id
        inject_wikilinks("RAG", "Concepts/RAG", wiki_dir=tmp_wiki)
        updated_content = src_path.read_text(encoding="utf-8")
        # Injected link must use literal lowercase (not just when .lower() is applied to content)
        assert "[[concepts/rag|" in updated_content or "[[concepts/rag]]" in updated_content, (
            f"Expected lowercase wikilink in content, got: {updated_content!r}"
        )


# ── Task 5: MCP Error Handling HIGH ─────────────────────────────────────────


class TestKbIngestContentOSError:
    """mcp/core.py kb_ingest_content: OSError returns error string, no orphan file."""

    def test_write_oserror_returns_error_string(self, monkeypatch, tmp_project):
        """OSError during file write must return 'Error: ...' string."""
        from pathlib import Path

        from kb.mcp import core as mcp_core

        original_write = Path.write_text

        def failing_write(self, *a, **kw):
            if "test-content" in str(self):
                raise OSError("disk full")
            return original_write(self, *a, **kw)

        monkeypatch.setattr(Path, "write_text", failing_write)

        result = mcp_core.kb_ingest_content(
            content="Some article content",
            filename="test-content",
            source_type="article",
            extraction_json='{"title":"Test","entities_mentioned":[],"concepts_mentioned":[]}',
        )
        assert result.startswith("Error:"), f"Expected error string, got: {result[:80]}"

    def test_orphan_file_cleaned_up_on_ingest_failure(self, monkeypatch, tmp_project):
        """If ingest_source raises after write, the written file must be deleted."""
        from kb.mcp import core as mcp_core

        def failing_ingest(*a, **kw):
            raise RuntimeError("ingest boom")

        monkeypatch.setattr("kb.mcp.core.ingest_source", failing_ingest, raising=False)

        result = mcp_core.kb_ingest_content(
            content="Orphan file content",
            filename="orphan-test-file",
            source_type="article",
            extraction_json='{"title":"Orphan","entities_mentioned":[],"concepts_mentioned":[]}',
        )
        assert result.startswith("Error:")
        # The raw file must NOT remain
        from kb.config import SOURCE_TYPE_DIRS

        orphan = SOURCE_TYPE_DIRS["article"] / "orphan-test-file.md"
        assert not orphan.exists(), "Orphaned raw file not cleaned up"


class TestKbGraphVizMaxNodes:
    """mcp/health.py kb_graph_viz: max_nodes clamped at 500."""

    def test_max_nodes_clamped(self, monkeypatch):
        """kb_graph_viz with max_nodes=99999 must call export_mermaid with max_nodes<=500."""
        from kb.mcp import health as mcp_health

        calls = []

        def mock_export(max_nodes):
            calls.append(max_nodes)
            return "graph LR"

        monkeypatch.setattr("kb.mcp.health.export_mermaid", mock_export, raising=False)

        mcp_health.kb_graph_viz(max_nodes=99999)
        assert calls and calls[0] <= 500, f"max_nodes not clamped: got {calls}"


# ── Task 6: Utils ────────────────────────────────────────────────────────────


class TestMakeSourceRefRaisesForOutsidePath:
    """utils/paths.py make_source_ref: raises ValueError for paths outside raw/."""

    def test_raises_for_path_outside_raw(self, tmp_path):
        """make_source_ref must raise ValueError if source is outside raw/."""
        from kb.utils.paths import make_source_ref

        outside = tmp_path / "not-raw" / "something.md"
        outside.parent.mkdir()
        outside.touch()

        with pytest.raises(ValueError, match="outside"):
            make_source_ref(outside, raw_dir=tmp_path / "raw")

    def test_valid_path_returns_ref(self, tmp_path):
        """make_source_ref returns canonical ref for paths inside raw/."""
        from kb.utils.paths import make_source_ref

        raw_dir = tmp_path / "raw"
        articles = raw_dir / "articles"
        articles.mkdir(parents=True)
        src = articles / "test.md"
        src.touch()

        ref = make_source_ref(src, raw_dir=raw_dir)
        assert ref == "raw/articles/test.md"


class TestWikiLogPipeSanitization:
    """utils/wiki_log.py append_wiki_log: pipe characters are sanitized."""

    def test_pipe_in_message_does_not_corrupt_log(self, tmp_path):
        """A pipe character in message must be replaced before writing."""
        from kb.utils.wiki_log import append_wiki_log

        log_path = tmp_path / "log.md"
        append_wiki_log("ingest", "Processed raw/articles/a.md | extra column", log_path)
        content = log_path.read_text(encoding="utf-8")
        lines = [ln for ln in content.splitlines() if ln.startswith("-")]
        assert len(lines) == 1, "Pipe in message must not create extra columns"
        # The log line should have exactly 2 pipe separators (date | op | message)
        assert lines[0].count("|") == 2, f"Expected 2 pipes in log line, got: {lines[0]!r}"


class TestNormalizeSourcesTypeCheck:
    """utils/pages.py normalize_sources: non-string list elements filtered."""

    def test_none_in_list_filtered_out(self):
        """None elements in source list must be filtered."""
        from kb.utils.pages import normalize_sources

        result = normalize_sources([None, "raw/articles/a.md", None, "raw/articles/b.md"])
        assert result == ["raw/articles/a.md", "raw/articles/b.md"]

    def test_non_string_converted(self):
        """Non-string elements must be converted to str or dropped."""
        from kb.utils.pages import normalize_sources

        # At minimum, no AttributeError or TypeError
        result = normalize_sources(["raw/articles/a.md", 42])
        assert all(isinstance(s, str) for s in result)


# ── Task 7: Ingest Pipeline MEDIUM ──────────────────────────────────────────


class TestExtractionSchemaCaching:
    """ingest/extractors.py: _build_schema_cached uses LRU cache."""

    def test_schema_cached_across_calls(self):
        """Calling _build_schema_cached twice for the same type returns the same object."""
        from kb.ingest.extractors import _build_schema_cached

        schema1 = _build_schema_cached("article")
        schema2 = _build_schema_cached("article")
        assert schema1 is schema2, "Expected same object from cache"


class TestUpdateSourcesMappingBacktick:
    """ingest/pipeline.py _update_sources_mapping: backtick-wrapped check avoids prefix match."""

    def test_shorter_ref_does_not_match_longer_ref(self, tmp_wiki):
        """'raw/articles/a.md' must not falsely match when 'raw/articles/abc.md' is present."""
        from kb.ingest.pipeline import _update_sources_mapping

        sources_path = tmp_wiki / "_sources.md"
        sources_path.write_text(
            "# Sources\n\n- `raw/articles/abc.md` → concepts/something\n",
            encoding="utf-8",
        )
        _update_sources_mapping("raw/articles/a.md", ["concepts/new-page"], tmp_wiki)
        content = sources_path.read_text(encoding="utf-8")
        assert "`raw/articles/a.md`" in content, (
            "Shorter ref should have been added despite longer ref present"
        )


class TestBuildSummaryContentTypeGuard:
    """ingest/pipeline.py _build_summary_content: None in authors list is handled."""

    def test_none_in_authors_list_does_not_crash(self):
        """_build_summary_content must not raise TypeError for [None, 'Alice']."""
        from kb.ingest.pipeline import _build_summary_content

        extraction = {
            "title": "Test Article",
            "authors": [None, "Alice Smith"],
        }
        result = _build_summary_content(extraction, "article")
        assert "Alice Smith" in result


# ── Task 8: Compile MEDIUM/LOW ───────────────────────────────────────────────


class TestCompileHashCapturedBeforeIngest:
    """compile/compiler.py compile_wiki: hash captured before ingest_source call."""

    def test_pre_captured_hash_written_to_manifest(self, tmp_project, monkeypatch):
        """The manifest must store the hash computed BEFORE ingest_source runs."""
        from kb.compile.compiler import compile_wiki, load_manifest
        from kb.utils.hashing import content_hash

        raw_path = tmp_project / "raw" / "articles" / "hash-test.md"
        raw_path.write_text("# Hash Test\n\nContent here.\n", encoding="utf-8")
        expected_hash = content_hash(raw_path)

        original_ingest = __import__("kb.ingest.pipeline", fromlist=["ingest_source"]).ingest_source

        def patched_ingest(path, *a, **kw):
            # Modify file AFTER hash would be computed (if captured before ingest)
            path.write_text(path.read_text(encoding="utf-8") + "\nextra\n", encoding="utf-8")
            return original_ingest(path, *a, **kw)

        monkeypatch.setattr("kb.compile.compiler.ingest_source", patched_ingest)

        manifest_path = tmp_project / ".data" / "hashes-test.json"
        manifest_path.parent.mkdir(exist_ok=True)
        compile_wiki(incremental=False, raw_dir=tmp_project / "raw", manifest_path=manifest_path)

        manifest = load_manifest(manifest_path)
        # Hash in manifest should be pre-ingest (original file hash)
        for key, val in manifest.items():
            if "hash-test" in key:
                assert val == expected_hash, (
                    f"Manifest hash should be pre-ingest. Expected {expected_hash}, got {val}"
                )
                break


class TestScanRawSourcesWarnsUnknownSubdir:
    """compile/compiler.py scan_raw_sources: warns for unknown subdirectories."""

    def test_unknown_subdir_emits_warning(self, tmp_path, caplog):
        """scan_raw_sources must emit WARNING for unknown subdirectories."""
        import logging

        from kb.compile.compiler import scan_raw_sources

        # Create a known dir and an unknown dir
        raw_dir = tmp_path / "raw"
        (raw_dir / "articles").mkdir(parents=True)
        (raw_dir / "unknown_type").mkdir()
        (raw_dir / "unknown_type" / "file.md").write_text("content", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="kb.compile.compiler"):
            scan_raw_sources(raw_dir=raw_dir)

        assert any("unknown_type" in r.message for r in caplog.records), (
            "Expected WARNING mentioning unknown subdir 'unknown_type'"
        )
