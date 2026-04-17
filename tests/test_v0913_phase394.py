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
                "content_lower": "neural network deep learning",
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
    def test_wikilink_in_surrounding_text_does_not_interfere(self):
        r"""Wikilinks in surrounding text don't affect citation extraction — Fix 4.2.

        The old implementation had a dead re.sub that normalized [[path]] → path
        over the whole text before parsing. This was removed in Phase 3.96 Task 4
        because it was dead code: the citation regex pattern [\w/_.-]+ cannot match
        '[' characters, so [[path]] inside a [source: ...] bracket was already
        unextractable. The normalization only affected surrounding text, where it
        had no effect on citation parsing.
        """
        from kb.query.citations import extract_citations

        # [[wikilink]] in surrounding text — citation itself is plain
        text = "According to [[concepts/rag]], see [source: concepts/rag] for details."
        citations = extract_citations(text)
        paths = [c["path"] for c in citations]
        assert "concepts/rag" in paths, f"Expected 'concepts/rag' in {paths}"

    def test_wikilink_inside_citation_brackets_extracted_post_t1_widen(self):
        r"""Cycle 5 redo T1b updated this behavior.

        Before T1b: regex ``\[(source|ref):\s*([\w/_.-]+)\]`` couldn't match
        the inner ``[[concepts/rag]]`` because ``[`` wasn't in ``[\w/_.-]+``
        — the whole ``[source: [[concepts/rag]]]`` construct yielded zero
        citations.

        After T1b: regex alternation ``... | \[\[([\w/_.-]+)\]\]`` matches
        the inner ``[[concepts/rag]]``. LLMs that accidentally emit the
        malformed nested form now still produce a working citation rather
        than silently dropping it. Updated from a negative-assert pin to a
        positive behavior check per the cycle 5 redo design decision
        (docs/superpowers/decisions/2026-04-18-cycle5-redo-design.md).
        """
        from kb.query.citations import extract_citations

        text = "See [source: [[concepts/rag]]] for details."
        citations = extract_citations(text)
        assert len(citations) == 1
        assert citations[0]["path"] == "concepts/rag"
        assert citations[0]["type"] == "wiki"

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
    """lint/verdicts.py add_verdict: notes length is capped via truncation."""

    def test_add_verdict_truncates_oversized_notes(self, tmp_path):
        """add_verdict must truncate notes that exceed MAX_NOTES_LEN (not raise)."""
        from kb.lint.verdicts import MAX_NOTES_LEN, add_verdict

        entry = add_verdict(
            "concepts/test",
            "fidelity",
            "pass",
            notes="x" * 2001,
            path=tmp_path / "v.json",
        )
        assert len(entry["notes"]) <= MAX_NOTES_LEN


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
        from unittest.mock import patch

        from kb.mcp import core as mcp_core

        def failing_atomic_write(content, path):
            if "test-content" in str(path):
                raise OSError("disk full")

        with patch.object(mcp_core, "atomic_text_write", side_effect=failing_atomic_write):
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

        def mock_export(max_nodes, wiki_dir=None):
            # Cycle 6 AC2: kb_graph_viz now threads wiki_dir through to
            # export_mermaid; mock accepts the new kwarg.
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
    """compile/compiler.py compile_wiki: failed ingest records failed:<hash> in manifest."""

    def test_compile_runs_ingest_and_records_failed_hash_on_error(self, tmp_project, monkeypatch):
        """When ingest_source raises, compile_wiki records failed:<pre_hash> in manifest."""
        from kb.compile.compiler import compile_wiki, load_manifest
        from kb.utils.hashing import content_hash

        raw_path = tmp_project / "raw" / "articles" / "hash-test.md"
        raw_path.write_text("# Hash Test\n\nContent here.\n", encoding="utf-8")
        expected_hash = content_hash(raw_path)

        def failing_ingest(path, *a, **kw):
            raise RuntimeError("simulated ingest failure")

        monkeypatch.setattr("kb.compile.compiler.ingest_source", failing_ingest)

        manifest_path = tmp_project / ".data" / "hashes-test.json"
        manifest_path.parent.mkdir(exist_ok=True)
        compile_wiki(incremental=False, raw_dir=tmp_project / "raw", manifest_path=manifest_path)

        manifest = load_manifest(manifest_path)
        # When ingest fails, compiler writes failed:<pre_hash> so source is retried next run.
        found = False
        for key, val in manifest.items():
            if "hash-test" in key:
                assert val == f"failed:{expected_hash}", (
                    f"Expected failed:{expected_hash}, got {val}"
                )
                found = True
                break
        assert found, f"No manifest entry found for hash-test source. Keys: {list(manifest.keys())}"


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


# ── Task 9: Graph & Evolve ────────────────────────────────────────────────────


class TestGraphStatsBetweennessException:
    """graph/builder.py graph_stats: betweenness_centrality failure is caught."""

    def test_betweenness_exception_does_not_propagate(self, monkeypatch):
        """A failure in betweenness_centrality must be caught and return empty bridge_nodes."""
        import networkx as nx

        from kb.graph.builder import graph_stats

        def failing_bc(graph, **kw):
            raise RuntimeError("betweenness boom")

        monkeypatch.setattr(nx, "betweenness_centrality", failing_bc)

        g = nx.DiGraph()
        g.add_edge("a", "b")
        stats = graph_stats(g)
        assert stats["bridge_nodes"] == [], (
            f"Expected empty bridge_nodes, got {stats['bridge_nodes']}"
        )


class TestGraphStatsOrphansKeyRenamed:
    """graph/builder.py graph_stats: 'orphans' key renamed to 'no_inbound'."""

    def test_no_inbound_key_present(self):
        """graph_stats must return 'no_inbound' key (not 'orphans')."""
        import networkx as nx

        from kb.graph.builder import graph_stats

        g = nx.DiGraph()
        g.add_edge("a", "b")
        g.add_node("c")  # isolated
        stats = graph_stats(g)
        assert "no_inbound" in stats, f"'no_inbound' key missing from stats: {list(stats.keys())}"


class TestMermaidSanitizeLabel:
    """graph/export.py _sanitize_label: parentheses stripped."""

    def test_parentheses_stripped_from_label(self):
        """_sanitize_label must remove '(' and ')' from page titles."""
        from kb.graph.export import _sanitize_label

        result = _sanitize_label("GPT-4 (OpenAI)")
        assert "(" not in result and ")" not in result, f"Parens not stripped: {result!r}"


# ── Task 10: Feedback, Review & Quality ───────────────────────────────────────


class TestLoadFeedbackShapeValidation:
    """feedback/store.py load_feedback: returns default when shape is wrong."""

    def test_wrong_shape_json_returns_default(self, tmp_path):
        """JSON with missing 'entries' or 'page_scores' must return default structure."""
        from kb.feedback.store import load_feedback

        bad_file = tmp_path / "feedback.json"
        bad_file.write_text('{"wrong_key": []}', encoding="utf-8")

        result = load_feedback(bad_file)
        assert "entries" in result
        assert "page_scores" in result

    def test_valid_structure_returned_as_is(self, tmp_path):
        """A valid feedback file's entries list is preserved and core fields are intact.

        Cycle 2 item 24: `load_feedback` now backfills MISSING count keys
        (`useful`/`wrong`/`incomplete`) once at load, so the page_scores dict
        may gain those keys. `trust` is preserved exactly. Legacy assertion
        updated to reflect the one-shot migration contract.
        """
        import json

        from kb.feedback.store import load_feedback

        good_file = tmp_path / "feedback.json"
        good_data = {"entries": [], "page_scores": {"concepts/rag": {"trust": 0.7}}}
        good_file.write_text(json.dumps(good_data), encoding="utf-8")

        result = load_feedback(good_file)
        assert result["entries"] == good_data["entries"]
        # trust preserved verbatim
        assert result["page_scores"]["concepts/rag"]["trust"] == 0.7
        # count keys backfilled (cycle 2 migration)
        for key in ("useful", "wrong", "incomplete"):
            assert result["page_scores"]["concepts/rag"][key] == 0


class TestRefinePageHorizontalRule:
    """review/refiner.py refine_page: content starting with '---' (hr) is allowed."""

    def test_horizontal_rule_content_not_rejected(self, tmp_wiki, create_wiki_page):
        """Content starting with '---\\n' (horizontal rule) must not return error."""
        from kb.review.refiner import refine_page

        create_wiki_page(
            page_id="concepts/hr-test",
            title="HR Test",
            content="Some content.",
            wiki_dir=tmp_wiki,
        )
        result = refine_page(
            "concepts/hr-test",
            updated_content="---\n\nBelow the rule.\n",
            wiki_dir=tmp_wiki,
        )
        assert "error" not in result, f"Horizontal rule incorrectly rejected: {result}"

    def test_frontmatter_block_content_still_rejected(self, tmp_wiki, create_wiki_page):
        """Content that is a full frontmatter block (---\\nkey: val\\n---) must be rejected."""
        from kb.review.refiner import refine_page

        create_wiki_page(
            page_id="concepts/fm-test",
            title="FM Test",
            content="Some content.",
            wiki_dir=tmp_wiki,
        )
        result = refine_page(
            "concepts/fm-test",
            updated_content="---\ntitle: Injected\n---\nContent\n",
            wiki_dir=tmp_wiki,
        )
        assert "error" in result, "Frontmatter block content must be rejected"


# ── Task 11: MCP MEDIUM/LOW ──────────────────────────────────────────────────


class TestFormatIngestResultGetSafety:
    """mcp/app.py _format_ingest_result: uses .get() for result dict keys."""

    def test_partial_result_does_not_raise(self):
        """_format_ingest_result must not raise KeyError on a partial result dict."""
        from kb.mcp.app import _format_ingest_result

        partial = {}  # Missing pages_created, pages_updated
        result = _format_ingest_result("raw/articles/test.md", "article", "abc123", partial)
        assert isinstance(result, str)


class TestListSourcesStatFailure:
    """mcp/browse.py kb_list_sources: per-file stat failure is skipped."""

    def test_broken_symlink_does_not_abort_listing(self, tmp_path, monkeypatch):
        """A stat() failure on one file must not abort the entire listing."""
        from pathlib import Path

        from kb import config as kb_config

        # Point RAW_DIR to tmp
        raw_dir = tmp_path / "raw"
        articles = raw_dir / "articles"
        articles.mkdir(parents=True)
        (articles / "good.md").write_text("content", encoding="utf-8")

        monkeypatch.setattr(kb_config, "RAW_DIR", raw_dir)

        original_stat = Path.stat

        def failing_stat(self, **kw):
            if self.name == "good.md":
                raise OSError("stat failed")
            return original_stat(self, **kw)

        monkeypatch.setattr(Path, "stat", failing_stat)

        from kb.mcp.browse import kb_list_sources

        result = kb_list_sources()
        # Must return a string, not raise
        assert isinstance(result, str)


# ── Task 12: raw_content rename ──────────────────────────────────────────────


class TestContentLowerFieldName:
    """utils/pages.py load_all_pages: field is named 'content_lower', not 'raw_content'."""

    def test_content_lower_key_present(self, tmp_wiki, create_wiki_page):
        """load_all_pages must return 'content_lower' key (not 'raw_content')."""
        from kb.utils.pages import load_all_pages

        create_wiki_page(
            page_id="concepts/rename-test",
            title="Rename Test",
            content="Hello World",
            wiki_dir=tmp_wiki,
        )
        pages = load_all_pages(tmp_wiki)
        assert len(pages) == 1
        assert "content_lower" in pages[0], "'content_lower' key missing"
        assert "raw_content" not in pages[0], "'raw_content' key must not be present"
        assert pages[0]["content_lower"] == "hello world"
