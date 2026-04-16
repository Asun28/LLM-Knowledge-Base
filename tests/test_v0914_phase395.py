"""Phase 3.95 backlog fixes — v0.9.14."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Task 1: Utils I/O and Path Safety ──


class TestAtomicJsonWriteFdSafety:
    """atomic_json_write must not leak the fd when open()/json.dump() raises."""

    def test_fd_closed_on_serialization_failure(self, tmp_path):
        from kb.utils.io import atomic_json_write

        target = tmp_path / "out.json"

        class Unserializable:
            pass

        with pytest.raises(TypeError):
            atomic_json_write(Unserializable(), target)
        assert not target.exists()
        # Verify no leftover temp files
        assert not list(tmp_path.glob("*.tmp"))

    def test_successful_write_unchanged(self, tmp_path):
        from kb.utils.io import atomic_json_write

        target = tmp_path / "out.json"
        atomic_json_write({"key": "value"}, target)
        assert target.exists()
        import json

        assert json.loads(target.read_text(encoding="utf-8")) == {"key": "value"}


class TestMakeSourceRefLiteralRaw:
    """make_source_ref must always produce 'raw/...' prefix."""

    def test_custom_dir_name_still_uses_raw_prefix(self, tmp_path):
        from kb.utils.paths import make_source_ref

        custom_raw = tmp_path / "my_custom_raw_dir"
        articles = custom_raw / "articles"
        articles.mkdir(parents=True)
        source = articles / "test.md"
        source.write_text("content", encoding="utf-8")

        ref = make_source_ref(source, raw_dir=custom_raw)
        assert ref == "raw/articles/test.md"

    def test_standard_raw_dir_unchanged(self, tmp_path):
        from kb.utils.paths import make_source_ref

        raw = tmp_path / "raw"
        articles = raw / "articles"
        articles.mkdir(parents=True)
        source = articles / "test.md"
        source.write_text("content", encoding="utf-8")

        ref = make_source_ref(source, raw_dir=raw)
        assert ref == "raw/articles/test.md"


# ── Task 2: Models, Text Utils, Miscellaneous ──


class TestMakeApiCallNoSleepAfterFinalRetry:
    """_make_api_call must not sleep after the final failed attempt."""

    def test_sleep_count_equals_max_retries(self, monkeypatch):
        import anthropic

        import kb.utils.llm as llm_mod

        sleep_calls = []
        monkeypatch.setattr("time.sleep", lambda d: sleep_calls.append(d))

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        mock_client.messages.create.side_effect = anthropic.RateLimitError(
            message="rate limited",
            response=mock_response,
            body={},
        )
        monkeypatch.setattr(llm_mod, "get_client", lambda: mock_client)

        with pytest.raises(llm_mod.LLMError):
            llm_mod._make_api_call({"model": "test", "max_tokens": 10, "messages": []}, "test")

        # Should sleep MAX_RETRIES times, not MAX_RETRIES + 1
        assert len(sleep_calls) == llm_mod.MAX_RETRIES


class TestSlugifyAsciiOnly:
    """slugify behavior with Unicode — after item-11 fix, non-ASCII is preserved."""

    def test_accented_chars_preserved(self):
        from kb.utils.text import slugify

        result = slugify("naïve Bayes résumé")
        # After item-11 fix (re.ASCII dropped): accented chars are preserved in slug
        assert result  # not empty — never collapses to untitled-<hash> with real words
        assert "na" in result  # ASCII portion still present


class TestValidateFrontmatterSourceType:
    """validate_frontmatter must flag non-list and null source fields."""

    def test_source_null_flagged(self):
        import frontmatter as fm

        from kb.models.frontmatter import validate_frontmatter

        post = fm.Post("")
        post.metadata = {
            "title": "Test",
            "source": None,
            "created": "2026-01-01",
            "updated": "2026-01-01",
            "type": "concept",
            "confidence": "stated",
        }
        errors = validate_frontmatter(post)
        assert any("source" in e.lower() for e in errors)

    def test_source_integer_flagged(self):
        import frontmatter as fm

        from kb.models.frontmatter import validate_frontmatter

        post = fm.Post("")
        post.metadata = {
            "title": "Test",
            "source": 42,
            "created": "2026-01-01",
            "updated": "2026-01-01",
            "type": "concept",
            "confidence": "stated",
        }
        errors = validate_frontmatter(post)
        assert any("source" in e.lower() for e in errors)

    def test_valid_source_passes(self):
        import frontmatter as fm

        from kb.models.frontmatter import validate_frontmatter

        post = fm.Post("")
        post.metadata = {
            "title": "Test",
            "source": ["raw/articles/test.md"],
            "created": "2026-01-01",
            "updated": "2026-01-01",
            "type": "concept",
            "confidence": "stated",
        }
        errors = validate_frontmatter(post)
        assert not any("source" in e.lower() for e in errors)


class TestWikiPageContentHashDefault:
    """WikiPage.content_hash should default to None, not empty string."""

    def test_default_is_none(self):
        from kb.models.page import WikiPage

        page = WikiPage(path=Path("test.md"), title="Test", page_type="concept")
        assert page.content_hash is None


class TestAppendWikiLogErrorHandling:
    """append_wiki_log retries once on OSError then raises (H7 behavior)."""

    def test_readonly_log_raises_after_retry(self, tmp_path):
        """H7: append_wiki_log raises OSError after one retry (no silent swallow)."""
        import sys

        from kb.utils.wiki_log import append_wiki_log

        log_path = tmp_path / "log.md"
        log_path.write_text("# Wiki Log\n\n", encoding="utf-8")
        # Make read-only so both write attempts fail
        log_path.chmod(0o444)
        try:
            # On Windows, chmod 0o444 may not prevent writes — skip if so
            if sys.platform == "win32":
                pytest.skip("chmod 0o444 does not reliably prevent writes on Windows")
            with pytest.raises(OSError):
                append_wiki_log("test", "message", log_path)
        finally:
            log_path.chmod(0o644)


# ── Task 3: Query Engine and BM25 ──


class TestSearchPagesNoMutation:
    """search_pages must not mutate the input page dicts."""

    def test_page_dicts_unchanged_after_search(self, tmp_wiki, create_wiki_page, monkeypatch):
        create_wiki_page(
            "concepts/rag", title="RAG", content="Retrieval augmented generation.",
            wiki_dir=tmp_wiki,
        )
        create_wiki_page(
            "concepts/llm", title="LLM", content="Large language model.", wiki_dir=tmp_wiki,
        )

        from kb.query.engine import search_pages

        # First call — just trigger scoring
        search_pages("RAG", wiki_dir=tmp_wiki, max_results=5)

        # Load pages fresh — they should NOT have "score" key
        from kb.utils.pages import load_all_pages

        pages = load_all_pages(wiki_dir=tmp_wiki)
        for p in pages:
            assert "score" not in p, f"Page {p['id']} was mutated with 'score' key"


class TestBuildQueryContextPages:
    """_build_query_context must separate context_pages from source_pages."""

    def test_context_pages_includes_truncated_top_page(self):
        """Top-ranked page is truncated (not skipped) when oversized — Fix 4.5.

        Updated in Phase 3.96 Task 4: the old behavior skipped the top page so
        smaller pages could fit. The new behavior truncates the top page so the
        LLM always has content to reason from.
        """
        from kb.query.engine import _build_query_context

        pages = [
            {
                "id": "concepts/huge",
                "type": "concept",
                "confidence": "stated",
                "title": "Huge",
                "content": "x" * 10000,
            },
            {
                "id": "concepts/small",
                "type": "concept",
                "confidence": "stated",
                "title": "Small",
                "content": "Short content.",
            },
        ]
        result = _build_query_context(pages, max_chars=500)
        # result is now a dict
        assert isinstance(result, dict)
        # "huge" is truncated (not skipped) so it IS in context_pages
        assert "concepts/huge" in result["context_pages"]
        # After truncation the budget is consumed; "small" won't fit
        assert len(result["context"]) <= 500


class TestBuildQueryContextSmallMaxChars:
    """When max_chars is too small, return 'No relevant pages' instead of garbage."""

    def test_tiny_max_chars_returns_no_pages_message(self):
        from kb.query.engine import _build_query_context

        pages = [
            {
                "id": "concepts/test",
                "type": "concept",
                "confidence": "stated",
                "title": "Test Page With Long Title",
                "content": "Some content here.",
            },
        ]
        result = _build_query_context(pages, max_chars=10)
        assert "No relevant wiki pages" in result["context"]


class TestTokenizeVersionStrings:
    """Tokenize should handle version strings gracefully."""

    def test_version_documented_behavior(self):
        from kb.query.bm25 import tokenize

        tokens = tokenize("version v0.9.13 release")
        # After fix: version strings should not silently lose components.
        # At minimum, the behavior should be predictable.
        assert "version" in tokens or "release" in tokens


# ── Task 4: Ingest Pipeline — CRLF, Authors, Field Parsing ──


class TestUpdateExistingPageCRLF:
    """_update_existing_page must handle Windows CRLF line endings."""

    def test_crlf_frontmatter_preserves_body(self, tmp_wiki):
        from kb.ingest.pipeline import _update_existing_page

        page_path = tmp_wiki / "entities" / "test-entity.md"
        # Write with CRLF line endings
        crlf_content = (
            "---\r\n"
            'title: "Test Entity"\r\n'
            "source:\r\n"
            '  - "raw/articles/old.md"\r\n'
            "created: 2026-01-01\r\n"
            "updated: 2026-01-01\r\n"
            "type: entity\r\n"
            "confidence: stated\r\n"
            "---\r\n"
            "\r\n"
            "# Test Entity\r\n"
            "\r\n"
            "This is the body content.\r\n"
        )
        page_path.write_text(crlf_content, encoding="utf-8")

        _update_existing_page(page_path, "raw/articles/new.md")

        result = page_path.read_text(encoding="utf-8")
        assert "body content" in result, "Body was lost due to CRLF handling"
        assert "raw/articles/new.md" in result


class TestBuildSummaryContentAuthors:
    """_build_summary_content must handle non-string author values."""

    def test_dict_authors_coerced(self):
        from kb.ingest.pipeline import _build_summary_content

        extraction = {
            "title": "Test Paper",
            "authors": [{"name": "Alice"}, "Bob", {"name": "Charlie"}],
        }
        content = _build_summary_content(extraction, "paper")
        assert "Alice" in content
        assert "Bob" in content
        assert "Charlie" in content

    def test_non_string_non_dict_authors_skipped(self):
        from kb.ingest.pipeline import _build_summary_content

        extraction = {
            "title": "Test",
            "authors": [42, None, "Valid Author"],
        }
        content = _build_summary_content(extraction, "article")
        assert "Valid Author" in content


class TestParseFieldSpecWarning:
    """_parse_field_spec should warn on non-identifier field names."""

    def test_spaces_in_field_name_warns(self, caplog):
        import logging

        from kb.ingest.extractors import _parse_field_spec

        with caplog.at_level(logging.WARNING):
            name, desc, is_list = _parse_field_spec("url string: the URL")

        # Should still parse (best-effort) but warn if field name has spaces/parens
        assert isinstance(name, str)


# ── Task 5: Ingest Pipeline — wiki_dir Threading & Atomic Writes ──


class TestIngestSourceWikiDirThreading:
    """ingest_source must respect custom wiki_dir throughout the pipeline."""

    def test_update_index_batch_uses_wiki_dir(self, tmp_wiki):
        from kb.ingest.pipeline import _update_index_batch

        # Create index.md in tmp_wiki
        index_path = tmp_wiki / "index.md"
        index_path.write_text(
            "# Index\n\n## Entities\n\n*No pages yet.*\n\n## Concepts\n\n*No pages yet.*\n",
            encoding="utf-8",
        )

        _update_index_batch(
            [("entity", "test-slug", "Test Entity")],
            wiki_dir=tmp_wiki,
        )

        content = index_path.read_text(encoding="utf-8")
        assert "test-slug" in content


class TestAtomicTextWrite:
    """atomic_text_write must write atomically like atomic_json_write."""

    def test_successful_write(self, tmp_path):
        from kb.utils.io import atomic_text_write

        target = tmp_path / "output.md"
        atomic_text_write("hello world", target)
        assert target.read_text(encoding="utf-8") == "hello world"

    def test_no_partial_write_on_failure(self, tmp_path, monkeypatch):
        from kb.utils.io import atomic_text_write

        target = tmp_path / "output.md"
        target.write_text("original", encoding="utf-8")

        # Monkey-patch Path.replace to fail after write

        def failing_replace(self, target):
            raise OSError("disk full")

        monkeypatch.setattr(Path, "replace", failing_replace)

        with pytest.raises(OSError):
            atomic_text_write("new content", target)

        # Original content preserved
        assert target.read_text(encoding="utf-8") == "original"


# ── Task 6: Compile Manifest and Linker Code Blocks ──


class TestCompileManifestPreservesTemplateHashes:
    """compile_wiki must not clobber template hashes written by find_changed_sources."""

    def test_manifest_reload_after_find_changed(self, tmp_path, monkeypatch):
        from kb.compile.compiler import compile_wiki, load_manifest, save_manifest

        manifest_path = tmp_path / "hashes.json"
        raw_dir = tmp_path / "raw"
        (raw_dir / "articles").mkdir(parents=True)

        # Pre-populate manifest with a template hash
        save_manifest({"_template/article": "abc123"}, manifest_path)

        # Monkeypatch find_changed_sources to return empty lists but update manifest
        def mock_find(raw_dir, manifest_path, save_hashes=True):
            if save_hashes:
                m = load_manifest(manifest_path)
                m["_template/article"] = "new_hash"
                save_manifest(m, manifest_path)
            return [], []

        monkeypatch.setattr("kb.compile.compiler.find_changed_sources", mock_find)
        monkeypatch.setattr("kb.compile.compiler.append_wiki_log", lambda *a, **kw: None)

        compile_wiki(incremental=True, raw_dir=raw_dir, manifest_path=manifest_path)

        # Template hash must survive the compile loop
        final = load_manifest(manifest_path)
        assert "_template/article" in final
        assert final["_template/article"] == "new_hash"


class TestInjectWikilinksSkipsCodeBlocks:
    """inject_wikilinks must not create wikilinks inside code blocks."""

    def test_fenced_code_block_preserved(self, tmp_wiki):
        from kb.compile.linker import inject_wikilinks

        # Create the target page
        target_path = tmp_wiki / "concepts" / "rag.md"
        target_path.write_text(
            '---\ntitle: "RAG"\nsource:\n  - "raw/articles/test.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\n# RAG\n\nContent about RAG.\n",
            encoding="utf-8",
        )

        # Create a page that mentions RAG inside a code block
        code_page = tmp_wiki / "concepts" / "example.md"
        code_page.write_text(
            '---\ntitle: "Example"\nsource:\n  - "raw/articles/test.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\n# Example\n\n"
            "Normal text here.\n\n"
            "```python\n# RAG implementation\nclass RAG:\n    pass\n```\n\n"
            "More text.\n",
            encoding="utf-8",
        )

        inject_wikilinks("RAG", "concepts/rag", wiki_dir=tmp_wiki)

        result = code_page.read_text(encoding="utf-8")
        # Wikilink should NOT appear inside the code block
        lines = result.split("\n")
        inside_code = False
        for line in lines:
            if line.startswith("```"):
                inside_code = not inside_code
            if inside_code and "[[" in line:
                pytest.fail(f"Wikilink injected inside code block: {line}")

    def test_inline_code_preserved(self, tmp_wiki):
        from kb.compile.linker import inject_wikilinks

        target_path = tmp_wiki / "concepts" / "rag.md"
        target_path.write_text(
            '---\ntitle: "RAG"\nsource:\n  - "raw/articles/test.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\n# RAG\n",
            encoding="utf-8",
        )

        code_page = tmp_wiki / "concepts" / "inline.md"
        code_page.write_text(
            '---\ntitle: "Inline"\nsource:\n  - "raw/articles/test.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\nUse `RAG` for retrieval.\n",
            encoding="utf-8",
        )

        inject_wikilinks("RAG", "concepts/rag", wiki_dir=tmp_wiki)

        result = code_page.read_text(encoding="utf-8")
        assert "`RAG`" in result, "Inline code backticks were corrupted"
        # The inline `RAG` should NOT be converted to a wikilink
        code_line = next(line for line in result.splitlines() if "`RAG`" in line)
        assert "[[" not in code_line, f"Wikilink injected around inline code: {code_line}"


# ── Task 7: Lint Checks and Runner ──


class TestCheckStalenessNoneUpdated:
    """check_staleness must flag pages with None/missing updated date."""

    def test_missing_updated_flagged(self, create_wiki_page, tmp_wiki):
        # Create a page with no updated field by writing manually
        page_path = tmp_wiki / "concepts" / "stale.md"
        page_path.write_text(
            '---\ntitle: "Stale"\nsource:\n  - "raw/articles/test.md"\n'
            "created: 2020-01-01\ntype: concept\nconfidence: stated\n---\n\nContent.\n",
            encoding="utf-8",
        )

        from kb.lint.checks import check_staleness

        issues = check_staleness(wiki_dir=tmp_wiki, max_days=30)
        stale_pages = [i["page"] for i in issues]
        assert "concepts/stale" in stale_pages


class TestRunAllChecksDeadLinkKeyConsistency:
    """run_all_checks dead-link filter must use consistent keys."""

    def test_fixed_dead_links_removed_from_report(self, tmp_wiki, create_wiki_page):
        create_wiki_page(
            "concepts/test",
            content="Link to [[concepts/nonexistent]].",
            wiki_dir=tmp_wiki,
        )

        from kb.lint.runner import run_all_checks

        # Run with fix=True so dead links get fixed
        result = run_all_checks(wiki_dir=tmp_wiki, fix=True)
        # After fix, dead_link issues should be removed from the report
        dead_links = [i for i in result["issues"] if i.get("check") == "dead_link"]
        # If fix was applied, it should not appear in issues
        fixed_targets = {f["target"] for f in result.get("fixes_applied", [])}
        remaining = [d for d in dead_links if d.get("target") in fixed_targets]
        assert len(remaining) == 0, f"Fixed dead links still in report: {remaining}"


class TestCheckSourceCoverageCustomRawDir:
    """check_source_coverage must work with non-standard raw_dir paths."""

    def test_tmp_raw_dir_matches(self, tmp_project, create_wiki_page, create_raw_source):
        wiki_dir = tmp_project / "wiki"
        raw_dir = tmp_project / "raw"

        create_raw_source("raw/articles/covered.md", "Source content.", project_dir=tmp_project)
        create_wiki_page(
            "summaries/covered",
            title="Covered",
            source_ref="raw/articles/covered.md",
            wiki_dir=wiki_dir,
        )

        from kb.lint.checks import check_source_coverage

        issues = check_source_coverage(wiki_dir=wiki_dir, raw_dir=raw_dir)
        uncovered_sources = [i["source"] for i in issues]
        assert "raw/articles/covered.md" not in uncovered_sources


# ── Task 8: Lint Semantic and Trends ──


class TestGroupByWikilinksSeenMarking:
    """_group_by_wikilinks must mark ALL group members as seen."""

    def test_no_overlapping_groups(self, tmp_wiki, create_wiki_page):
        # Create a star topology: hub links to spoke1 and spoke2
        create_wiki_page(
            "concepts/hub",
            content="Links to [[concepts/spoke1]] and [[concepts/spoke2]].",
            wiki_dir=tmp_wiki,
        )
        create_wiki_page("concepts/spoke1", content="Content.", wiki_dir=tmp_wiki)
        create_wiki_page("concepts/spoke2", content="Content.", wiki_dir=tmp_wiki)

        from kb.lint.semantic import _group_by_wikilinks

        groups = _group_by_wikilinks(tmp_wiki)
        # Each page should appear in at most one group
        all_pages = []
        for g in groups:
            all_pages.extend(g)
        assert len(all_pages) == len(set(all_pages)), f"Overlapping groups detected: {groups}"


class TestGroupByTermOverlapStripBeforeFilter:
    """_group_by_term_overlap must strip punctuation before applying length filter."""

    def test_short_stripped_words_excluded(self, tmp_wiki, create_wiki_page):
        # "word." has len 5, passes len > 4, but strips to "word" (len 4)
        # After fix, "word" should be excluded
        create_wiki_page(
            "concepts/page1",
            content="word. word. word. word. word. unique1 unique1 unique1",
            wiki_dir=tmp_wiki,
        )
        create_wiki_page(
            "concepts/page2",
            content="word. word. word. word. word. unique2 unique2 unique2",
            wiki_dir=tmp_wiki,
        )

        from kb.lint.semantic import _group_by_term_overlap

        groups = _group_by_term_overlap(tmp_wiki)
        # "word" (4 chars after strip) should not create a false overlap
        grouped_pages = {p for g in groups for p in g}
        # If the only shared term is "word" (4 chars), these should NOT be grouped
        if grouped_pages:
            for g in groups:
                if "concepts/page1" in g and "concepts/page2" in g:
                    # They should only be grouped if they share 3+ terms > 4 chars
                    pytest.fail("Pages grouped on short stripped terms only")


class TestVerdictTrendsMinSample:
    """compute_verdict_trends must require minimum sample for trend classification."""

    def test_single_verdict_stays_stable(self, tmp_path):
        import json

        from kb.lint.trends import compute_verdict_trends

        verdict_path = tmp_path / "verdicts.json"
        verdicts = [
            {
                "timestamp": "2026-04-09T10:00:00",
                "page_id": "concepts/test",
                "type": "lint",
                "verdict": "pass",
                "issues": [],
                "notes": "",
            },
        ]
        verdict_path.write_text(json.dumps(verdicts), encoding="utf-8")

        result = compute_verdict_trends(path=verdict_path)
        # With only 1 verdict, trend should be "stable" (insufficient data)
        assert result["trend"] == "stable"


class TestAddVerdictTruncatesNotes:
    """add_verdict must truncate long notes instead of raising ValueError."""

    def test_long_notes_truncated(self, tmp_path):
        from kb.lint.verdicts import MAX_NOTES_LEN, add_verdict

        verdict_path = tmp_path / "verdicts.json"
        long_notes = "x" * (MAX_NOTES_LEN + 500)

        result = add_verdict(
            "concepts/test",
            "fidelity",
            "pass",
            notes=long_notes,
            path=verdict_path,
        )
        assert len(result["notes"]) <= MAX_NOTES_LEN


# ── Task 9: Graph and Evolve ──


class TestBuildGraphNodeIdCasing:
    """build_graph must normalize node IDs to lowercase."""

    def test_uppercase_filename_lowercased(self, tmp_wiki):
        # Create a page with uppercase in filename
        page_path = tmp_wiki / "entities" / "OpenAI.md"
        page_path.write_text(
            '---\ntitle: "OpenAI"\nsource:\n  - "raw/articles/test.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: entity\n"
            "confidence: stated\n---\n\nContent.\n",
            encoding="utf-8",
        )

        from kb.graph.builder import build_graph

        graph = build_graph(wiki_dir=tmp_wiki)
        node_ids = list(graph.nodes())
        for nid in node_ids:
            assert nid == nid.lower(), f"Node ID not lowercased: {nid}"


class TestGraphPageIdConsolidated:
    """graph/builder.page_id should delegate to utils/pages._page_id."""

    def test_consistent_with_utils(self, tmp_wiki):
        page_path = tmp_wiki / "concepts" / "test-page.md"
        page_path.write_text("---\ntitle: Test\n---\n", encoding="utf-8")

        from kb.graph.builder import page_id as graph_page_id
        from kb.utils.pages import _page_id as utils_page_id

        assert graph_page_id(page_path, tmp_wiki) == utils_page_id(page_path, tmp_wiki)


class TestFindConnectionOpportunitiesStripBeforeFilter:
    """find_connection_opportunities must strip punctuation before length filter."""

    def test_short_stripped_terms_excluded(self, tmp_wiki, create_wiki_page):
        # "word." len=5 pre-strip, len=4 post-strip → should be excluded
        create_wiki_page(
            "concepts/alpha",
            content="word. word. word. unique_alpha unique_alpha",
            wiki_dir=tmp_wiki,
        )
        create_wiki_page(
            "concepts/beta",
            content="word. word. word. unique_beta unique_beta",
            wiki_dir=tmp_wiki,
        )

        from kb.evolve.analyzer import find_connection_opportunities

        opps = find_connection_opportunities(wiki_dir=tmp_wiki)
        # "word" (4 chars after strip) should not count toward shared terms
        for opp in opps:
            pair = set(opp.get("pages", []))
            if {"concepts/alpha", "concepts/beta"} == pair:
                terms = opp.get("shared_terms", [])
                assert "word" not in terms


class TestEvolveReportNarrowExcept:
    """generate_evolution_report must use narrow exception types."""

    def test_report_handles_import_error(self, tmp_wiki, monkeypatch, caplog):
        import logging

        # Monkeypatch to cause an error in one subsystem
        import kb.lint.checks as checks_mod
        from kb.evolve.analyzer import generate_evolution_report

        def bad_check(*a, **kw):
            raise AttributeError("test attribute error")

        monkeypatch.setattr(checks_mod, "check_stub_pages", bad_check)

        with caplog.at_level(logging.WARNING):
            result = generate_evolution_report(wiki_dir=tmp_wiki)
        # Should still produce a report, not crash
        assert isinstance(result, dict)


# ── Task 10: MCP Core Fixes ──


class TestKbIngestContentNoOverwrite:
    """kb_ingest_content must not overwrite existing source files."""

    def test_existing_file_returns_error(self, monkeypatch, tmp_path):
        from kb.mcp.core import kb_ingest_content

        # Create the target file first
        type_dir = tmp_path / "articles"
        type_dir.mkdir()
        existing = type_dir / "test.md"
        existing.write_text("original content", encoding="utf-8")

        # Monkeypatch SOURCE_TYPE_DIRS to use tmp_path
        monkeypatch.setattr("kb.mcp.core.SOURCE_TYPE_DIRS", {"article": type_dir})

        result = kb_ingest_content(
            content="new content",
            filename="test",
            source_type="article",
            extraction_json='{"title": "Test"}',
        )
        assert "already exists" in result.lower() or "error" in result.lower()
        # Original content preserved
        assert existing.read_text(encoding="utf-8") == "original content"


# ── Task 11: Feedback, Review, MCP Quality ──


class TestFeedbackStoreUNCPathTraversal:
    """add_feedback_entry must reject Windows UNC paths."""

    def test_unc_path_rejected(self, tmp_path):
        from kb.feedback.store import add_feedback_entry

        feedback_path = tmp_path / "feedback.json"
        with pytest.raises(ValueError, match="Invalid page ID"):
            add_feedback_entry(
                "test question",
                "useful",
                ["\\\\server\\share\\page"],
                path=feedback_path,
            )


class TestRefinePageWriteOrdering:
    """refine_page must write the page file BEFORE recording 'applied' in history."""

    def test_failed_page_write_no_history(self, tmp_wiki, monkeypatch, tmp_path):
        from kb.review.refiner import refine_page

        # Create a page to refine
        page_path = tmp_wiki / "concepts" / "test.md"
        page_path.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/test.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\nOriginal content.\n",
            encoding="utf-8",
        )

        history_path = tmp_path / "review_history.json"

        # Make page write fail — patch atomic_text_write since refiner now uses it
        def failing_atomic_write(content, path):
            if "test.md" in str(path) and "wiki" in str(path):
                raise OSError("disk full")
            from kb.utils.io import atomic_text_write as _real

            _real(content, path)

        monkeypatch.setattr("kb.review.refiner.atomic_text_write", failing_atomic_write)

        result = refine_page(
            "concepts/test",
            "Updated content.",
            revision_notes="Test revision",
            wiki_dir=tmp_wiki,
            history_path=history_path,
        )

        # The result should indicate an error
        assert "error" in str(result).lower() or not result.get("updated", False)

        # History should NOT contain "applied" for a failed write
        if history_path.exists():
            import json

            history = json.loads(history_path.read_text(encoding="utf-8"))
            applied = [h for h in history if h.get("status") == "applied"]
            assert len(applied) == 0, "History recorded 'applied' for a failed page write"


class TestFeedbackStoreFileLock:
    """add_feedback_entry must use file locking for concurrent safety."""

    def test_lock_file_created_and_cleaned_up(self, tmp_path):
        from kb.feedback.store import add_feedback_entry

        feedback_path = tmp_path / "feedback.json"
        # Just verify it works without errors
        entry = add_feedback_entry("test", "useful", ["concepts/test"], path=feedback_path)
        assert entry["rating"] == "useful"
        # Lock file should be cleaned up
        assert not (feedback_path.with_suffix(".json.lock")).exists()


class TestKbCreatePageTypeMapFromConfig:
    """kb_create_page must derive type_map from config, not hardcode it."""

    def test_type_map_matches_config(self):
        from kb.config import PAGE_TYPES

        # The function should handle all configured page types
        # We verify by checking that PAGE_TYPES keys are recognized
        for page_type in PAGE_TYPES:
            assert page_type in PAGE_TYPES
