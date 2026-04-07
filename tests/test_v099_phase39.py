"""Tests for Phase 3.9 features (v0.9.9)."""

import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kb.config import PAGERANK_SEARCH_WEIGHT

# ── Task 1: Environment-configurable model tiers ───────────────


class TestEnvConfigurableModelTiers:
    """Test that model tiers can be overridden via environment variables."""

    def test_default_tiers_unchanged(self):
        """Default tiers remain when no env vars set."""
        # Reimport to get fresh state
        from kb.config import MODEL_TIERS

        assert MODEL_TIERS["scan"] == "claude-haiku-4-5-20251001"
        assert MODEL_TIERS["write"] == "claude-sonnet-4-6"
        assert MODEL_TIERS["orchestrate"] == "claude-opus-4-6"

    def test_env_override_scan_model(self, monkeypatch):
        """CLAUDE_SCAN_MODEL env var overrides scan tier."""
        monkeypatch.setenv("CLAUDE_SCAN_MODEL", "custom-haiku-model")
        # Need to reimport the module to pick up env var
        import importlib

        import kb.config
        importlib.reload(kb.config)
        try:
            assert kb.config.MODEL_TIERS["scan"] == "custom-haiku-model"
        finally:
            # Restore defaults
            monkeypatch.delenv("CLAUDE_SCAN_MODEL", raising=False)
            importlib.reload(kb.config)

    def test_env_override_write_model(self, monkeypatch):
        """CLAUDE_WRITE_MODEL env var overrides write tier."""
        monkeypatch.setenv("CLAUDE_WRITE_MODEL", "custom-sonnet-model")
        import importlib

        import kb.config
        importlib.reload(kb.config)
        try:
            assert kb.config.MODEL_TIERS["write"] == "custom-sonnet-model"
        finally:
            monkeypatch.delenv("CLAUDE_WRITE_MODEL", raising=False)
            importlib.reload(kb.config)

    def test_env_override_orchestrate_model(self, monkeypatch):
        """CLAUDE_ORCHESTRATE_MODEL env var overrides orchestrate tier."""
        monkeypatch.setenv("CLAUDE_ORCHESTRATE_MODEL", "custom-opus-model")
        import importlib

        import kb.config
        importlib.reload(kb.config)
        try:
            assert kb.config.MODEL_TIERS["orchestrate"] == "custom-opus-model"
        finally:
            monkeypatch.delenv("CLAUDE_ORCHESTRATE_MODEL", raising=False)
            importlib.reload(kb.config)

    def test_partial_override_preserves_others(self, monkeypatch):
        """Setting one env var doesn't affect other tiers."""
        monkeypatch.setenv("CLAUDE_SCAN_MODEL", "custom-scan")
        import importlib

        import kb.config
        importlib.reload(kb.config)
        try:
            assert kb.config.MODEL_TIERS["scan"] == "custom-scan"
            assert kb.config.MODEL_TIERS["write"] == "claude-sonnet-4-6"
            assert kb.config.MODEL_TIERS["orchestrate"] == "claude-opus-4-6"
        finally:
            monkeypatch.delenv("CLAUDE_SCAN_MODEL", raising=False)
            importlib.reload(kb.config)


# ── Task 2: PageRank-blended search ranking ───────────────────


def _make_wiki_page(wiki_dir, subdir, slug, title, content, source_ref="raw/articles/test.md"):
    """Helper to create a wiki page with proper frontmatter."""
    today = date.today().isoformat()
    page_dir = wiki_dir / subdir
    page_dir.mkdir(parents=True, exist_ok=True)
    page_path = page_dir / f"{slug}.md"
    text = (
        f'---\ntitle: "{title}"\nsource:\n  - "{source_ref}"\n'
        f"created: {today}\nupdated: {today}\ntype: concept\nconfidence: stated\n---\n\n"
        f"{content}\n"
    )
    page_path.write_text(text, encoding="utf-8")
    return page_path


class TestPageRankBlendedSearch:
    """Test that search results blend BM25 scores with PageRank."""

    def test_pagerank_config_exists(self):
        """PAGERANK_SEARCH_WEIGHT config constant exists."""
        assert isinstance(PAGERANK_SEARCH_WEIGHT, (int, float))
        assert PAGERANK_SEARCH_WEIGHT >= 0

    def test_search_returns_scores_with_pagerank(self, tmp_path):
        """search_pages returns results with blended scores when graph exists."""
        wiki_dir = tmp_path / "wiki"
        # Create pages that link to each other (hub page gets high PageRank)
        hub = _make_wiki_page(
            wiki_dir, "concepts", "hub-topic",
            "Hub Topic", "Hub topic is central. See [[concepts/spoke-a]] and [[concepts/spoke-b]]."
        )
        spoke_a = _make_wiki_page(
            wiki_dir, "concepts", "spoke-a",
            "Spoke A", "Spoke A discusses hub topic. See [[concepts/hub-topic]]."
        )
        spoke_b = _make_wiki_page(
            wiki_dir, "concepts", "spoke-b",
            "Spoke B", "Spoke B discusses hub topic. See [[concepts/hub-topic]]."
        )

        from kb.query.engine import search_pages
        results = search_pages("hub topic", wiki_dir=wiki_dir)
        assert len(results) > 0
        # hub-topic should be boosted by PageRank (more inlinks)
        top_result = results[0]
        assert top_result["id"] == "concepts/hub-topic"

    def test_search_works_with_zero_weight(self, tmp_path):
        """Search works correctly when PageRank weight is zero (pure BM25)."""
        wiki_dir = tmp_path / "wiki"
        _make_wiki_page(
            wiki_dir, "concepts", "alpha",
            "Alpha Topic", "Alpha topic content for search."
        )

        with patch("kb.query.engine.PAGERANK_SEARCH_WEIGHT", 0.0):
            from kb.query.engine import search_pages
            results = search_pages("alpha topic", wiki_dir=wiki_dir)
            assert len(results) > 0

    def test_search_single_page_no_graph(self, tmp_path):
        """Search works with a single page (no meaningful graph)."""
        wiki_dir = tmp_path / "wiki"
        _make_wiki_page(
            wiki_dir, "concepts", "lonely",
            "Lonely Page", "A lonely page about searching."
        )

        from kb.query.engine import search_pages
        results = search_pages("lonely page", wiki_dir=wiki_dir)
        assert len(results) == 1
        assert results[0]["score"] > 0

    def test_pagerank_boosts_well_linked_page(self, tmp_path):
        """A well-linked page gets boosted above a poorly-linked one with similar BM25."""
        wiki_dir = tmp_path / "wiki"
        # Create a hub that many pages link to
        _make_wiki_page(
            wiki_dir, "concepts", "popular",
            "Machine Learning", "Machine learning is a popular topic."
        )
        # Create several pages linking to popular
        for i in range(5):
            _make_wiki_page(
                wiki_dir, "concepts", f"fan-{i}",
                f"Fan {i}", f"Fan {i} discusses machine learning. See [[concepts/popular]].",
                source_ref=f"raw/articles/fan-{i}.md",
            )
        # Create an isolated page with similar content
        _make_wiki_page(
            wiki_dir, "concepts", "isolated",
            "Machine Learning Isolated", "Machine learning is a popular topic.",
            source_ref="raw/articles/isolated.md",
        )

        from kb.query.engine import search_pages
        results = search_pages("machine learning", wiki_dir=wiki_dir)

        # popular should appear above isolated due to PageRank boost
        ids = [r["id"] for r in results]
        popular_idx = ids.index("concepts/popular")
        isolated_idx = ids.index("concepts/isolated")
        assert popular_idx < isolated_idx, "Well-linked page should rank higher"


# ── Task 3: Duplicate detection in ingest ─────────────────────


class TestDuplicateDetection:
    """Test hash-based duplicate detection in ingest pipeline."""

    def _setup_project(self, tmp_path):
        """Create minimal project structure for ingest tests."""
        wiki_dir = tmp_path / "wiki"
        for sub in ("summaries", "entities", "concepts", "comparisons", "synthesis"):
            (wiki_dir / sub).mkdir(parents=True)
        (wiki_dir / "index.md").write_text(
            "# Index\n\n## Summaries\n\n## Entities\n\n## Concepts\n\n"
            "## Comparisons\n\n## Synthesis\n", encoding="utf-8"
        )
        (wiki_dir / "_sources.md").write_text("# Source Mapping\n\n", encoding="utf-8")
        (wiki_dir / "log.md").write_text("# Log\n", encoding="utf-8")

        raw_dir = tmp_path / "raw"
        (raw_dir / "articles").mkdir(parents=True)

        data_dir = tmp_path / ".data"
        data_dir.mkdir(parents=True)

        return wiki_dir, raw_dir, data_dir

    def test_first_ingest_succeeds(self, tmp_path, monkeypatch):
        """First ingest of a source creates pages normally."""
        wiki_dir, raw_dir, data_dir = self._setup_project(tmp_path)
        monkeypatch.setattr("kb.config.WIKI_DIR", wiki_dir)
        monkeypatch.setattr("kb.config.RAW_DIR", raw_dir)
        monkeypatch.setattr("kb.config.WIKI_INDEX", wiki_dir / "index.md")
        monkeypatch.setattr("kb.config.WIKI_SOURCES", wiki_dir / "_sources.md")
        monkeypatch.setattr("kb.config.WIKI_LOG", wiki_dir / "log.md")
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_DIR", wiki_dir)
        monkeypatch.setattr("kb.ingest.pipeline.RAW_DIR", raw_dir)
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md")
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md")

        source = raw_dir / "articles" / "test-article.md"
        source.write_text("# Test Article\n\nSome content here.", encoding="utf-8")

        from kb.ingest.pipeline import ingest_source

        extraction = {
            "title": "Test Article",
            "entities_mentioned": ["TestEntity"],
            "concepts_mentioned": ["TestConcept"],
        }
        result = ingest_source(source, "article", extraction=extraction)
        assert len(result["pages_created"]) > 0
        assert result.get("duplicate") is not True

    def test_duplicate_detected_by_hash(self, tmp_path, monkeypatch):
        """Ingesting same content from different path is detected as duplicate."""
        wiki_dir, raw_dir, data_dir = self._setup_project(tmp_path)
        monkeypatch.setattr("kb.config.WIKI_DIR", wiki_dir)
        monkeypatch.setattr("kb.config.RAW_DIR", raw_dir)
        monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("kb.config.WIKI_INDEX", wiki_dir / "index.md")
        monkeypatch.setattr("kb.config.WIKI_SOURCES", wiki_dir / "_sources.md")
        monkeypatch.setattr("kb.config.WIKI_LOG", wiki_dir / "log.md")
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_DIR", wiki_dir)
        monkeypatch.setattr("kb.ingest.pipeline.RAW_DIR", raw_dir)
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md")
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md")
        monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", data_dir / "hashes.json")

        content = "# Duplicate Article\n\nThis is duplicate content."
        source1 = raw_dir / "articles" / "original.md"
        source1.write_text(content, encoding="utf-8")

        source2 = raw_dir / "articles" / "copy.md"
        source2.write_text(content, encoding="utf-8")

        from kb.ingest.pipeline import ingest_source

        extraction = {
            "title": "Duplicate Article",
            "entities_mentioned": [],
            "concepts_mentioned": [],
        }
        # First ingest — records hash in manifest
        result1 = ingest_source(source1, "article", extraction=extraction)
        assert len(result1["pages_created"]) > 0

        # Second ingest with same content — should detect duplicate
        result2 = ingest_source(source2, "article", extraction=extraction)
        assert result2.get("duplicate") is True

    def test_different_content_not_duplicate(self, tmp_path, monkeypatch):
        """Different content from different paths is not flagged as duplicate."""
        wiki_dir, raw_dir, data_dir = self._setup_project(tmp_path)
        monkeypatch.setattr("kb.config.WIKI_DIR", wiki_dir)
        monkeypatch.setattr("kb.config.RAW_DIR", raw_dir)
        monkeypatch.setattr("kb.config.WIKI_INDEX", wiki_dir / "index.md")
        monkeypatch.setattr("kb.config.WIKI_SOURCES", wiki_dir / "_sources.md")
        monkeypatch.setattr("kb.config.WIKI_LOG", wiki_dir / "log.md")
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_DIR", wiki_dir)
        monkeypatch.setattr("kb.ingest.pipeline.RAW_DIR", raw_dir)
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md")
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md")
        monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", data_dir / "hashes.json")

        source1 = raw_dir / "articles" / "article-a.md"
        source1.write_text("# Article A\n\nUnique content A.", encoding="utf-8")

        source2 = raw_dir / "articles" / "article-b.md"
        source2.write_text("# Article B\n\nUnique content B.", encoding="utf-8")

        from kb.ingest.pipeline import ingest_source

        ext1 = {"title": "Article A", "entities_mentioned": [], "concepts_mentioned": []}
        ext2 = {"title": "Article B", "entities_mentioned": [], "concepts_mentioned": []}

        result1 = ingest_source(source1, "article", extraction=ext1)
        result2 = ingest_source(source2, "article", extraction=ext2)
        assert result1.get("duplicate") is not True
        assert result2.get("duplicate") is not True
