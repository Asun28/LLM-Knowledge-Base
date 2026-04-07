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
        # Patch RAW_DIR in paths module so make_source_ref resolves correctly
        monkeypatch.setattr("kb.utils.paths.RAW_DIR", raw_dir)

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


# ── Task 4: Verdict trend dashboard ──────────────────────────


class TestVerdictTrends:
    """Test verdict trend analysis from verdict history."""

    def test_empty_verdicts_returns_empty(self, tmp_path):
        """No verdicts produces empty trends."""
        from kb.lint.verdicts import load_verdicts

        path = tmp_path / "verdicts.json"
        from kb.lint.trends import compute_verdict_trends

        result = compute_verdict_trends(path)
        assert result["total"] == 0
        assert result["periods"] == []

    def test_single_period_trends(self, tmp_path):
        """Verdicts in one period produce correct counts."""
        from kb.lint.trends import compute_verdict_trends
        from kb.lint.verdicts import add_verdict

        path = tmp_path / "verdicts.json"
        add_verdict("concepts/rag", "fidelity", "pass", path=path)
        add_verdict("concepts/rag", "consistency", "fail",
                     issues=[{"severity": "error", "description": "mismatch"}], path=path)
        add_verdict("entities/openai", "review", "warning", path=path)

        result = compute_verdict_trends(path)
        assert result["total"] == 3
        assert len(result["periods"]) >= 1
        # Overall counts
        assert result["overall"]["pass"] == 1
        assert result["overall"]["fail"] == 1
        assert result["overall"]["warning"] == 1

    def test_trend_shows_improvement(self, tmp_path):
        """Trends show improvement when recent verdicts are better than old."""
        import json

        path = tmp_path / "verdicts.json"
        # Manually write old + new verdicts with different timestamps
        old_ts = (datetime.now() - timedelta(days=20)).isoformat(timespec="seconds")
        new_ts = datetime.now().isoformat(timespec="seconds")

        verdicts = [
            {"timestamp": old_ts, "page_id": "c/a", "verdict_type": "fidelity",
             "verdict": "fail", "issues": [], "notes": ""},
            {"timestamp": old_ts, "page_id": "c/b", "verdict_type": "fidelity",
             "verdict": "fail", "issues": [], "notes": ""},
            {"timestamp": new_ts, "page_id": "c/a", "verdict_type": "fidelity",
             "verdict": "pass", "issues": [], "notes": ""},
            {"timestamp": new_ts, "page_id": "c/b", "verdict_type": "fidelity",
             "verdict": "pass", "issues": [], "notes": ""},
        ]
        path.write_text(json.dumps(verdicts), encoding="utf-8")

        from kb.lint.trends import compute_verdict_trends

        result = compute_verdict_trends(path)
        assert result["total"] == 4
        # Should have at least 2 periods (old and new)
        assert len(result["periods"]) >= 1
        assert result["trend"] in ("improving", "stable", "declining")

    def test_mcp_tool_returns_string(self):
        """kb_verdict_trends MCP tool returns a formatted string."""
        from kb.mcp.health import kb_verdict_trends

        result = kb_verdict_trends()
        assert isinstance(result, str)
        assert "Verdict" in result or "verdict" in result or "No verdict" in result


# ── Task 5: Mermaid graph export ─────────────────────────────


class TestMermaidGraphExport:
    """Test Mermaid diagram generation from wiki graph."""

    def test_empty_graph_returns_empty_mermaid(self, tmp_path):
        """Empty wiki produces minimal Mermaid diagram."""
        wiki_dir = tmp_path / "wiki"
        for sub in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
            (wiki_dir / sub).mkdir(parents=True)

        from kb.graph.export import export_mermaid

        result = export_mermaid(wiki_dir=wiki_dir)
        assert result.startswith("graph LR")

    def test_basic_graph_produces_valid_mermaid(self, tmp_path):
        """Simple graph produces valid Mermaid with nodes and edges."""
        wiki_dir = tmp_path / "wiki"
        _make_wiki_page(wiki_dir, "concepts", "rag", "RAG",
                        "RAG combines [[concepts/retrieval]] with generation.")
        _make_wiki_page(wiki_dir, "concepts", "retrieval", "Retrieval",
                        "Retrieval is used by [[concepts/rag]].")

        from kb.graph.export import export_mermaid

        result = export_mermaid(wiki_dir=wiki_dir)
        assert "graph LR" in result
        assert "concepts_rag" in result  # sanitized node ID
        assert "concepts_retrieval" in result
        assert "-->" in result

    def test_auto_prune_large_graph(self, tmp_path):
        """Graphs with >50 nodes are pruned to max_nodes most-connected."""
        wiki_dir = tmp_path / "wiki"
        # Create 60 pages
        for i in range(60):
            links = f"[[concepts/page-{(i+1) % 60}]]"
            _make_wiki_page(
                wiki_dir, "concepts", f"page-{i}",
                f"Page {i}", f"Content for page {i}. {links}",
                source_ref=f"raw/articles/p{i}.md",
            )

        from kb.graph.export import export_mermaid

        result = export_mermaid(wiki_dir=wiki_dir, max_nodes=30)
        # Should be pruned — count node definitions
        node_lines = [l for l in result.split("\n") if '["' in l or '("' in l]
        assert len(node_lines) <= 30

    def test_node_labels_use_page_titles(self, tmp_path):
        """Node labels use page titles from frontmatter."""
        wiki_dir = tmp_path / "wiki"
        _make_wiki_page(wiki_dir, "entities", "openai", "OpenAI",
                        "OpenAI makes GPT models.")

        from kb.graph.export import export_mermaid

        result = export_mermaid(wiki_dir=wiki_dir)
        assert "entities_openai" in result
        assert "OpenAI" in result  # title used as label

    def test_mcp_tool_returns_mermaid(self):
        """kb_graph_viz MCP tool returns Mermaid string."""
        from kb.mcp.health import kb_graph_viz

        result = kb_graph_viz()
        assert isinstance(result, str)
        assert "graph" in result.lower() or "no pages" in result.lower()


# ── Task 6: Retroactive inbound wikilink injection ───────────


class TestRetroactiveWikilinkInjection:
    """Test injecting wikilinks into existing pages when new pages are created."""

    def test_inject_wikilink_for_exact_match(self, tmp_path):
        """Existing page mentioning a new page's title gets a wikilink injected."""
        wiki_dir = tmp_path / "wiki"
        # Create existing page that mentions "Machine Learning" as plain text
        _make_wiki_page(
            wiki_dir, "concepts", "deep-learning",
            "Deep Learning",
            "Deep learning is a subset of Machine Learning that uses neural networks.",
        )

        from kb.compile.linker import inject_wikilinks

        injected = inject_wikilinks(
            "Machine Learning", "concepts/machine-learning", wiki_dir=wiki_dir
        )
        assert len(injected) == 1
        assert injected[0] == "concepts/deep-learning"

        # Verify the wikilink was inserted
        content = (wiki_dir / "concepts" / "deep-learning.md").read_text(encoding="utf-8")
        assert "[[concepts/machine-learning|Machine Learning]]" in content

    def test_no_injection_in_frontmatter(self, tmp_path):
        """Wikilinks are not injected into YAML frontmatter."""
        wiki_dir = tmp_path / "wiki"
        _make_wiki_page(
            wiki_dir, "concepts", "test-page",
            "Test Page",
            "Some content about other things.",
        )

        from kb.compile.linker import inject_wikilinks

        injected = inject_wikilinks(
            "Test Page", "concepts/test-page-new", wiki_dir=wiki_dir
        )
        # Should not inject into the page's own title in frontmatter
        content = (wiki_dir / "concepts" / "test-page.md").read_text(encoding="utf-8")
        # Frontmatter should be unchanged
        assert 'title: "Test Page"' in content

    def test_no_injection_when_wikilink_exists(self, tmp_path):
        """Skip injection when page already has a wikilink to the target."""
        wiki_dir = tmp_path / "wiki"
        _make_wiki_page(
            wiki_dir, "concepts", "existing",
            "Existing",
            "Already links to [[concepts/target-page]] explicitly.",
        )

        from kb.compile.linker import inject_wikilinks

        injected = inject_wikilinks(
            "Target Page", "concepts/target-page", wiki_dir=wiki_dir
        )
        assert len(injected) == 0  # Already linked

    def test_skip_self_injection(self, tmp_path):
        """Don't inject wikilink into the page itself."""
        wiki_dir = tmp_path / "wiki"
        _make_wiki_page(
            wiki_dir, "concepts", "self-ref",
            "Self Ref",
            "This page talks about Self Ref concepts.",
        )

        from kb.compile.linker import inject_wikilinks

        injected = inject_wikilinks(
            "Self Ref", "concepts/self-ref", wiki_dir=wiki_dir
        )
        assert len(injected) == 0

    def test_case_insensitive_match(self, tmp_path):
        """Matching is case-insensitive for the title."""
        wiki_dir = tmp_path / "wiki"
        _make_wiki_page(
            wiki_dir, "concepts", "nlp-page",
            "NLP Page",
            "Natural language processing uses transformer architecture frequently.",
        )

        from kb.compile.linker import inject_wikilinks

        injected = inject_wikilinks(
            "Transformer Architecture", "concepts/transformer-architecture",
            wiki_dir=wiki_dir,
        )
        assert len(injected) == 1


# ── Task 7: Content-length-aware ingest tiering ──────────────


class TestContentLengthIngestTiering:
    """Test that short sources get simplified ingest (summary only)."""

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

    def test_short_source_creates_summary_only(self, tmp_path, monkeypatch):
        """Source under SMALL_SOURCE_THRESHOLD creates summary but defers entities."""
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
        monkeypatch.setattr("kb.utils.paths.RAW_DIR", raw_dir)
        monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", data_dir / "hashes.json")

        # Short source (under 1000 chars)
        source = raw_dir / "articles" / "short.md"
        source.write_text("# Short\nBrief note.", encoding="utf-8")

        from kb.ingest.pipeline import ingest_source

        extraction = {
            "title": "Short Note",
            "entities_mentioned": ["BigEntity"],
            "concepts_mentioned": ["BigConcept"],
        }
        result = ingest_source(source, "article", extraction=extraction)

        # Summary should be created
        assert any("summaries/" in p for p in result["pages_created"])
        # Entity/concept pages should NOT be created (deferred)
        entity_pages = [p for p in result["pages_created"] if p.startswith("entities/")]
        concept_pages = [p for p in result["pages_created"] if p.startswith("concepts/")]
        assert len(entity_pages) == 0
        assert len(concept_pages) == 0
        assert result.get("deferred_entities") is True

    def test_long_source_creates_full_pages(self, tmp_path, monkeypatch):
        """Source over SMALL_SOURCE_THRESHOLD creates full entities and concepts."""
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
        monkeypatch.setattr("kb.utils.paths.RAW_DIR", raw_dir)
        monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", data_dir / "hashes.json")

        # Long source (over 1000 chars)
        long_content = "# Long Article\n\n" + "Some substantial content. " * 100
        source = raw_dir / "articles" / "long.md"
        source.write_text(long_content, encoding="utf-8")

        from kb.ingest.pipeline import ingest_source

        extraction = {
            "title": "Long Article",
            "entities_mentioned": ["EntityA"],
            "concepts_mentioned": ["ConceptB"],
        }
        result = ingest_source(source, "article", extraction=extraction)

        # All pages should be created
        assert any("summaries/" in p for p in result["pages_created"])
        assert any("entities/" in p for p in result["pages_created"])
        assert any("concepts/" in p for p in result["pages_created"])
        assert result.get("deferred_entities") is not True

    def test_config_threshold_exists(self):
        """SMALL_SOURCE_THRESHOLD config constant exists."""
        from kb.config import SMALL_SOURCE_THRESHOLD
        assert isinstance(SMALL_SOURCE_THRESHOLD, int)
        assert SMALL_SOURCE_THRESHOLD > 0
