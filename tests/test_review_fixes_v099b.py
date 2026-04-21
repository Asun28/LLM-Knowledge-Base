"""Tests for v0.9.9 review fixes — code review follow-up.

Covers 4 issues from code review:
1. inject_wikilinks integrated into ingest_source() for new pages
2. Duplicate detection message surfaced in MCP output (_format_ingest_result)
3. affected_pages surfaced in MCP output (_format_ingest_result)
4. ingest_source docstring updated with all new params/keys
"""

from unittest.mock import patch

# ── Issue 1: inject_wikilinks called from ingest ──────────────────────────────


class TestInjectWikilinksCalledOnIngest:
    """inject_wikilinks is called for each new page created during ingest."""

    @patch("kb.ingest.pipeline.extract_from_source")
    def test_inject_wikilinks_called_for_each_new_page(self, mock_extract, tmp_path):
        """inject_wikilinks is called for every new page created during ingest."""
        mock_extract.return_value = {
            "title": "Neural Networks",
            "core_argument": "Deep learning is powerful.",
            "key_claims": [],
            "entities_mentioned": ["Geoffrey Hinton"],
            "concepts_mentioned": ["Backpropagation"],
        }

        raw_dir = tmp_path / "raw"
        (raw_dir / "articles").mkdir(parents=True)
        wiki_dir = tmp_path / "wiki"
        for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
            (wiki_dir / subdir).mkdir(parents=True)
        (wiki_dir / "index.md").write_text(
            "---\ntitle: Wiki Index\nupdated: 2026-01-01\n---\n\n# Index\n"
        )
        (wiki_dir / "_sources.md").write_text(
            "---\ntitle: Source Mapping\nupdated: 2026-01-01\n---\n\n# Sources\n"
        )
        (wiki_dir / "log.md").write_text("# Log\n\n")

        source = raw_dir / "articles" / "neural-networks.md"
        source.write_text("# Neural Networks\n\nAbout deep learning and backpropagation.")

        # Cycle 19 AC6 — pipeline switched from per-title `inject_wikilinks`
        # to a single `inject_wikilinks_batch` call. Update mock target.
        batch_calls: list[list[tuple[str, str]]] = []

        def mock_batch(new_pages, wiki_dir=None, *, pages=None):
            batch_calls.append(list(new_pages))
            return {}

        from kb.ingest.pipeline import ingest_source

        with (
            patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
            patch("kb.utils.paths.RAW_DIR", raw_dir),
            patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
            patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
            patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
            patch("kb.compile.linker.inject_wikilinks_batch", side_effect=mock_batch),
        ):
            ingest_source(source, source_type="article")

        # Cycle 19 AC6 — inject_wikilinks_batch is called exactly once per ingest
        # (replacing the legacy per-title loop).
        assert len(batch_calls) == 1, (
            f"inject_wikilinks_batch should be called exactly once; got {len(batch_calls)}"
        )

        # The single batch call must include all new pages (summary + entity + concept).
        call_page_ids = [pid for _, pid in batch_calls[0]]
        assert any("summaries/" in pid for pid in call_page_ids)
        assert any("entities/" in pid for pid in call_page_ids)
        assert any("concepts/" in pid for pid in call_page_ids)

    @patch("kb.ingest.pipeline.extract_from_source")
    def test_inject_wikilinks_updates_existing_page(self, mock_extract, tmp_path):
        """inject_wikilinks rewrites an existing page that mentions the new title."""
        mock_extract.return_value = {
            "title": "Attention Mechanism",
            "core_argument": "Attention is all you need.",
            "key_claims": [],
            "entities_mentioned": [],
            "concepts_mentioned": [],
        }

        raw_dir = tmp_path / "raw"
        (raw_dir / "articles").mkdir(parents=True)
        wiki_dir = tmp_path / "wiki"
        for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
            (wiki_dir / subdir).mkdir(parents=True)
        (wiki_dir / "index.md").write_text(
            "---\ntitle: Wiki Index\nupdated: 2026-01-01\n---\n\n# Index\n"
        )
        (wiki_dir / "_sources.md").write_text(
            "---\ntitle: Source Mapping\nupdated: 2026-01-01\n---\n\n# Sources\n"
        )
        (wiki_dir / "log.md").write_text("# Log\n\n")

        # Pre-existing page that mentions "Attention Mechanism" in plain text
        existing_page = wiki_dir / "concepts" / "transformer.md"
        existing_page.write_text(
            '---\ntitle: "Transformer"\nsource:\n  - "raw/articles/transformer.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
            "The Transformer uses Attention Mechanism as its core building block.\n"
        )

        source = raw_dir / "articles" / "attention.md"
        source.write_text("# Attention Mechanism\n\nAttention is all you need.")

        from kb.ingest.pipeline import ingest_source

        with (
            patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
            patch("kb.utils.paths.RAW_DIR", raw_dir),
            patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
            patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
            patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
            patch("kb.compile.linker.WIKI_DIR", wiki_dir),
        ):
            ingest_source(source, source_type="article")

        # The existing page should now contain a wikilink to the new summary
        updated_content = existing_page.read_text(encoding="utf-8")
        assert "[[" in updated_content, (
            "Expected wikilink injection in existing page, but none found"
        )
        assert "Attention Mechanism" in updated_content

    @patch("kb.ingest.pipeline.extract_from_source")
    def test_inject_wikilinks_result_in_ingest_return(self, mock_extract, tmp_path):
        """ingest_source result includes wikilinks_injected count."""
        mock_extract.return_value = {
            "title": "Gradient Descent",
            "core_argument": "Minimize loss.",
            "key_claims": [],
            "entities_mentioned": [],
            "concepts_mentioned": [],
        }

        raw_dir = tmp_path / "raw"
        (raw_dir / "articles").mkdir(parents=True)
        wiki_dir = tmp_path / "wiki"
        for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
            (wiki_dir / subdir).mkdir(parents=True)
        (wiki_dir / "index.md").write_text(
            "---\ntitle: Wiki Index\nupdated: 2026-01-01\n---\n\n# Index\n"
        )
        (wiki_dir / "_sources.md").write_text(
            "---\ntitle: Source Mapping\nupdated: 2026-01-01\n---\n\n# Sources\n"
        )
        (wiki_dir / "log.md").write_text("# Log\n\n")

        source = raw_dir / "articles" / "gradient-descent.md"
        source.write_text("# Gradient Descent\n\nHow to minimize loss functions.")

        from kb.ingest.pipeline import ingest_source

        with (
            patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
            patch("kb.utils.paths.RAW_DIR", raw_dir),
            patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
            patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
            patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
            patch("kb.compile.linker.inject_wikilinks", return_value=["concepts/foo"]),
        ):
            result = ingest_source(source, source_type="article")

        # Result should include wikilinks_injected
        assert "wikilinks_injected" in result


# ── Issue 2: Duplicate detection message in MCP output ───────────────────────


class TestDuplicateDetectionMCPOutput:
    """_format_ingest_result communicates duplicates clearly."""

    def test_duplicate_result_shows_clear_message(self):
        """When result has duplicate=True, output explains why no pages were created."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": [],
            "pages_updated": [],
            "pages_skipped": [],
            "duplicate": True,
        }
        output = _format_ingest_result("raw/articles/copy.md", "article", "abc123def456", result)

        assert "Duplicate" in output or "duplicate" in output
        # Should NOT just say "Pages created (0):" with no explanation
        assert "abc123def456" in output  # hash should be visible

    def test_duplicate_result_does_not_say_zero_pages_only(self):
        """Duplicate output should explain the situation, not just show 0 pages."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": [],
            "pages_updated": [],
            "pages_skipped": [],
            "duplicate": True,
        }
        output = _format_ingest_result("raw/articles/copy.md", "article", "deadbeef", result)

        # Must contain some indication this was intentionally skipped
        full_output = output.lower()
        assert (
            "duplicate" in full_output
            or "already ingested" in full_output
            or "identical" in full_output
        )

    def test_non_duplicate_result_unchanged(self):
        """Normal (non-duplicate) results still show pages created/updated."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": ["summaries/foo", "entities/bar"],
            "pages_updated": ["concepts/baz"],
            "pages_skipped": [],
        }
        output = _format_ingest_result("raw/articles/foo.md", "article", "hash123", result)

        assert "Pages created (2):" in output
        assert "summaries/foo" in output
        assert "Pages updated (1):" in output


# ── Issue 3: affected_pages in MCP output ────────────────────────────────────


class TestAffectedPagesMCPOutput:
    """_format_ingest_result surfaces affected_pages when non-empty."""

    def test_affected_pages_shown_in_output(self):
        """When affected_pages is non-empty (flat list), it appears in the formatted output."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": ["summaries/new-topic"],
            "pages_updated": [],
            "pages_skipped": [],
            "affected_pages": [
                "concepts/related-topic",
                "entities/some-entity",
                "summaries/old-summary",
            ],
        }
        output = _format_ingest_result("raw/articles/new.md", "article", "hash456", result)

        assert "affected" in output.lower() or "Affected" in output
        assert "concepts/related-topic" in output
        assert "entities/some-entity" in output
        assert "summaries/old-summary" in output

    def test_empty_affected_pages_not_shown(self):
        """When affected_pages is empty list, no affected section appears."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": ["summaries/new-topic"],
            "pages_updated": [],
            "pages_skipped": [],
            "affected_pages": [],
        }
        output = _format_ingest_result("raw/articles/new.md", "article", "hash789", result)

        # Should not add noise for empty affected_pages
        assert "Affected pages" not in output

    def test_missing_affected_pages_key_no_error(self):
        """Results without affected_pages key don't crash."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": ["summaries/foo"],
            "pages_updated": [],
            "pages_skipped": [],
            # no affected_pages key
        }
        output = _format_ingest_result("raw/articles/foo.md", "article", "hashxxx", result)
        assert "Pages created (1):" in output

    def test_affected_pages_backlinks_and_shared_shown_separately(self):
        """Flat affected_pages list shows all pages in output."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": ["summaries/alpha"],
            "pages_updated": [],
            "pages_skipped": [],
            "affected_pages": ["concepts/beta", "summaries/gamma"],
        }
        output = _format_ingest_result("raw/articles/alpha.md", "article", "hash000", result)

        assert "concepts/beta" in output
        assert "summaries/gamma" in output


# ── Issue 4: ingest_source docstring ─────────────────────────────────────────


class TestIngestSourceDocstring:
    """ingest_source has accurate docstring covering all params and return keys."""

    def test_docstring_mentions_defer_small(self):
        """ingest_source docstring documents the defer_small parameter."""
        from kb.ingest.pipeline import ingest_source

        doc = ingest_source.__doc__ or ""
        assert "defer_small" in doc

    def test_docstring_mentions_pages_skipped(self):
        """ingest_source docstring mentions pages_skipped in Returns."""
        from kb.ingest.pipeline import ingest_source

        doc = ingest_source.__doc__ or ""
        assert "pages_skipped" in doc

    def test_docstring_mentions_affected_pages(self):
        """ingest_source docstring mentions affected_pages in Returns."""
        from kb.ingest.pipeline import ingest_source

        doc = ingest_source.__doc__ or ""
        assert "affected_pages" in doc

    def test_docstring_mentions_duplicate(self):
        """ingest_source docstring mentions duplicate key in Returns."""
        from kb.ingest.pipeline import ingest_source

        doc = ingest_source.__doc__ or ""
        assert "duplicate" in doc


# ── Post-review fixes: flat list affected_pages + wikilinks_injected ─────────


class TestAffectedPagesFlatList:
    """_format_ingest_result handles flat list[str] from pipeline (actual return type)."""

    def test_flat_list_affected_pages_shown_in_output(self):
        """affected_pages as flat list (from _find_affected_pages) is displayed."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": ["summaries/new-topic"],
            "pages_updated": [],
            "pages_skipped": [],
            "affected_pages": ["concepts/related", "entities/person-a"],
        }
        output = _format_ingest_result("raw/articles/x.md", "article", "h1", result)

        assert "Affected pages" in output
        assert "concepts/related" in output
        assert "entities/person-a" in output

    def test_empty_flat_list_not_shown(self):
        """Empty flat list produces no affected pages section."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": ["summaries/foo"],
            "pages_updated": [],
            "pages_skipped": [],
            "affected_pages": [],
        }
        output = _format_ingest_result("raw/articles/y.md", "article", "h2", result)
        assert "Affected pages" not in output

    def test_flat_list_count_shown_correctly(self):
        """Count in header matches the number of affected pages."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": [],
            "pages_updated": [],
            "pages_skipped": [],
            "affected_pages": ["a", "b", "c"],
        }
        output = _format_ingest_result("raw/articles/z.md", "article", "h3", result)
        assert "Affected pages (3)" in output


class TestWikilinksInjectedMCPOutput:
    """_format_ingest_result surfaces wikilinks_injected when non-empty."""

    def test_wikilinks_injected_shown_in_output(self):
        """When wikilinks_injected is non-empty, it appears in the formatted output."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": ["summaries/foo"],
            "pages_updated": [],
            "pages_skipped": [],
            "wikilinks_injected": ["concepts/bar", "entities/baz"],
        }
        output = _format_ingest_result("raw/articles/foo.md", "article", "h4", result)

        assert "Wikilinks injected" in output
        assert "concepts/bar" in output
        assert "entities/baz" in output

    def test_empty_wikilinks_injected_not_shown(self):
        """Empty wikilinks_injected list produces no wikilinks section."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": ["summaries/foo"],
            "pages_updated": [],
            "pages_skipped": [],
            "wikilinks_injected": [],
        }
        output = _format_ingest_result("raw/articles/foo.md", "article", "h5", result)
        assert "Wikilinks injected" not in output

    def test_missing_wikilinks_injected_key_no_error(self):
        """Results without wikilinks_injected key don't crash."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": ["summaries/foo"],
            "pages_updated": [],
            "pages_skipped": [],
        }
        output = _format_ingest_result("raw/articles/foo.md", "article", "h6", result)
        assert "Pages created (1):" in output

    def test_wikilinks_injected_count_shown(self):
        """Count of injected wikilinks is shown in the header."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": [],
            "pages_updated": [],
            "pages_skipped": [],
            "wikilinks_injected": ["a", "b"],
        }
        output = _format_ingest_result("raw/articles/foo.md", "article", "h7", result)
        assert "Wikilinks injected (2)" in output
