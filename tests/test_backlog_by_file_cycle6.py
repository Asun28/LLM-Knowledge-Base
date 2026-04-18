"""Regression tests for backlog-by-file cycle 6 fixes (AC1-AC15).

Cycle 6 ships 15 fixes across 14 files. Each test exercises the production
code path — not the signature — per `feedback_test_behavior_over_signature`
and `feedback_inspect_source_tests` memories.

Numbering follows
`docs/superpowers/decisions/2026-04-18-cycle6-requirements.md`.
"""

from __future__ import annotations

import logging
import sqlite3

import pytest

# ---------------------------------------------------------------------------
# AC1 — mcp/core.py kb_ingest_content accepts use_api
# ---------------------------------------------------------------------------


class TestKbIngestContentUseApi:
    """AC1 — ``kb_ingest_content(use_api=True)`` skips the extraction_json
    requirement and falls through to ``ingest_source``'s LLM extraction path.
    """

    def test_use_api_true_skips_extraction_json_validation(self, tmp_path, monkeypatch):
        from kb.mcp import core as mcp_core

        calls: list = []

        def _fake_ingest_source(path, source_type=None, extraction=None, **kwargs):
            calls.append({"path": path, "source_type": source_type, "extraction": extraction})
            return {
                "source_type": source_type or "article",
                "content_hash": "abc123",
                "pages_created": [],
                "pages_updated": [],
                "pages_skipped": [],
                "affected_pages": [],
                "wikilinks_injected": [],
            }

        # Redirect SOURCE_TYPE_DIRS so we don't write into the real raw/.
        fake_dir = tmp_path / "articles"
        monkeypatch.setattr(mcp_core, "SOURCE_TYPE_DIRS", {"article": fake_dir})
        monkeypatch.setattr(mcp_core, "ingest_source", _fake_ingest_source)

        result = mcp_core.kb_ingest_content(
            content="body",
            filename="my-article",
            source_type="article",
            extraction_json="",  # intentionally empty — use_api=True path
            use_api=True,
        )
        assert "Error" not in result, f"use_api=True should not require extraction_json: {result}"
        assert calls, "ingest_source was never called"
        # Critical: extraction kwarg was NOT passed → LLM extraction path triggered.
        assert calls[0]["extraction"] is None

    def test_use_api_false_still_validates_extraction_json(self, tmp_path, monkeypatch):
        from kb.mcp import core as mcp_core

        fake_dir = tmp_path / "articles"
        monkeypatch.setattr(mcp_core, "SOURCE_TYPE_DIRS", {"article": fake_dir})

        result = mcp_core.kb_ingest_content(
            content="body",
            filename="my-article2",
            source_type="article",
            extraction_json="",  # invalid → should error because use_api=False
            use_api=False,
        )
        assert result.startswith("Error:"), (
            "use_api=False must still reject missing extraction_json per AC1"
        )


# ---------------------------------------------------------------------------
# AC2 — mcp/health.py threads wiki_dir through 3 tools
# ---------------------------------------------------------------------------


class TestMcpHealthToolsThreadWikiDir:
    """AC2 — kb_detect_drift / kb_evolve / kb_graph_viz accept ``wiki_dir``."""

    def test_kb_detect_drift_passes_wiki_dir(self, tmp_path, monkeypatch):
        from kb.mcp import app as mcp_app
        from kb.mcp import health

        received: dict = {}

        def _fake(wiki_dir=None, **_):
            received["wiki_dir"] = wiki_dir
            return {
                "summary": "ok",
                "changed_sources": [],
                "affected_pages": [],
                "deleted_sources": [],
                "deleted_affected_pages": [],
            }

        monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(mcp_app, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(health, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("kb.compile.compiler.detect_source_drift", _fake)
        health.kb_detect_drift(wiki_dir=str(tmp_path))
        assert received["wiki_dir"] == tmp_path

    def test_kb_evolve_passes_wiki_dir(self, tmp_project, monkeypatch):
        from kb.mcp import app as mcp_app
        from kb.mcp import health

        received: dict = {}
        wiki_dir = tmp_project / "wiki"

        def _fake(wiki_dir=None):
            received["wiki_dir"] = wiki_dir
            return {"suggestions": []}

        monkeypatch.setattr(mcp_app, "PROJECT_ROOT", tmp_project)
        monkeypatch.setattr("kb.evolve.analyzer.generate_evolution_report", _fake)
        monkeypatch.setattr("kb.evolve.analyzer.format_evolution_report", lambda r: "report")
        health.kb_evolve(wiki_dir=str(wiki_dir))
        assert received["wiki_dir"] == wiki_dir

    def test_kb_graph_viz_passes_wiki_dir(self, tmp_path, monkeypatch):
        from kb.mcp import app as mcp_app
        from kb.mcp import health

        received: dict = {}

        def _fake(graph=None, wiki_dir=None, max_nodes=30):
            received["wiki_dir"] = wiki_dir
            return "graph LR\n"

        monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(mcp_app, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(health, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(health, "export_mermaid", _fake)
        health.kb_graph_viz(max_nodes=10, wiki_dir=str(tmp_path))
        assert received["wiki_dir"] == tmp_path


# ---------------------------------------------------------------------------
# AC3 — rewriter rejects LLM preamble leaks
# ---------------------------------------------------------------------------


class TestRewriteQueryRejectsPreambleLeak:
    """AC3 — rewrites like "Sure! Here's the rewrite: X" fall back to original."""

    @pytest.mark.parametrize(
        "leaked",
        [
            "Sure! Here's the rewrite: What is RAG?",
            "Certainly, here is the rewritten question: Explain attention",
            "The standalone question is: What is context?",
            "Rewritten query: How does GPT work?",
            "Here is the rewrite: What is LoRA?",
        ],
    )
    def test_preamble_leak_reverts_to_original(self, monkeypatch, caplog, leaked):
        from kb.query import rewriter

        monkeypatch.setattr(rewriter, "call_llm", lambda *a, **k: leaked)
        with caplog.at_level(logging.WARNING, logger="kb.query.rewriter"):
            out = rewriter.rewrite_query(
                "what about it?",
                conversation_context="Q: What is RAG? A: Retrieval augmented generation.",
            )
        assert out == "what about it?", f"leak {leaked!r} escaped rewriter"
        assert any("preamble-leak" in r.getMessage() for r in caplog.records), (
            "expected WARNING log on leak rejection"
        )

    def test_legitimate_rewrite_passes_through(self, monkeypatch):
        from kb.query import rewriter

        monkeypatch.setattr(rewriter, "call_llm", lambda *a, **k: "What is RAG exactly?")
        out = rewriter.rewrite_query(
            "what is it?",
            conversation_context="Q: Tell me about RAG. A: Retrieval augmented generation.",
        )
        assert out == "What is RAG exactly?"


# ---------------------------------------------------------------------------
# AC4 — PageRank cache keyed on (wiki_dir, mtime_ns, page_count)
# ---------------------------------------------------------------------------


class TestPageRankCache:
    """AC4 — ``_compute_pagerank_scores`` cached by (wiki_dir, mtime_ns, count)."""

    def test_cache_hit_on_identical_wiki_state(self, tmp_wiki, create_wiki_page, monkeypatch):
        from kb.query import engine

        # Populate a tiny wiki so build_graph has something to chew on.
        create_wiki_page(
            page_id="concepts/rag",
            title="RAG",
            content="See [[entities/openai]]",
            wiki_dir=tmp_wiki,
        )
        create_wiki_page(
            page_id="entities/openai",
            title="OpenAI",
            content="AI company",
            wiki_dir=tmp_wiki,
        )

        # Clear cache from any prior test.
        with engine._PAGERANK_CACHE_LOCK:
            engine._PAGERANK_CACHE.clear()

        call_count = {"n": 0}
        real_build_graph = engine.build_graph

        def _spy(*args, **kwargs):
            call_count["n"] += 1
            return real_build_graph(*args, **kwargs)

        monkeypatch.setattr(engine, "build_graph", _spy)

        engine._compute_pagerank_scores(tmp_wiki)
        engine._compute_pagerank_scores(tmp_wiki)
        assert call_count["n"] == 1, "second call should hit the cache"

    def test_cache_invalidates_on_page_count_change(self, tmp_wiki, create_wiki_page, monkeypatch):
        from kb.query import engine

        create_wiki_page(
            page_id="concepts/a",
            title="A",
            content="See [[entities/x]]",
            wiki_dir=tmp_wiki,
        )
        create_wiki_page(
            page_id="entities/x",
            title="X",
            content="Entity X",
            wiki_dir=tmp_wiki,
        )
        with engine._PAGERANK_CACHE_LOCK:
            engine._PAGERANK_CACHE.clear()

        call_count = {"n": 0}
        real_build_graph = engine.build_graph

        def _spy(*args, **kwargs):
            call_count["n"] += 1
            return real_build_graph(*args, **kwargs)

        monkeypatch.setattr(engine, "build_graph", _spy)

        engine._compute_pagerank_scores(tmp_wiki)
        # Add a new page → page_count key component changes.
        create_wiki_page(
            page_id="concepts/b",
            title="B",
            content="See [[entities/x]]",
            wiki_dir=tmp_wiki,
        )
        engine._compute_pagerank_scores(tmp_wiki)
        assert call_count["n"] == 2, "adding a page should invalidate the cache"


# ---------------------------------------------------------------------------
# AC5 — VectorIndex reuses sqlite3 connection; disabled on ext-load failure
# ---------------------------------------------------------------------------


class TestVectorIndexReusesConnection:
    """AC5 — extension load in __init__ / ensure_conn; single persistent conn."""

    def test_ensure_conn_reuses_connection_across_queries(self, tmp_path, monkeypatch):
        from kb.query import embeddings

        # Build a tiny empty DB so _ensure_conn finds a file.
        db_path = tmp_path / "vec.db"
        conn = sqlite3.connect(str(db_path))
        conn.close()

        # Stub sqlite_vec.load to a no-op so the test doesn't require the extension.
        class _StubVec:
            @staticmethod
            def load(_conn):
                return None

            @staticmethod
            def serialize_float32(_vec):  # pragma: no cover — unused here
                return b""

        monkeypatch.setitem(__import__("sys").modules, "sqlite_vec", _StubVec)

        idx = embeddings.VectorIndex(db_path)
        # First query triggers lazy load.
        idx.query([0.0, 0.0, 0.0])
        first_conn = idx._conn
        idx.query([0.0, 0.0, 0.0])
        assert idx._conn is first_conn, "VectorIndex should reuse the same sqlite3 connection"

    def test_extension_load_failure_disables_index(self, tmp_path, monkeypatch, caplog):
        from kb.query import embeddings

        db_path = tmp_path / "vec.db"
        sqlite3.connect(str(db_path)).close()

        class _FailingVec:
            @staticmethod
            def load(_conn):
                raise RuntimeError("sqlite_vec load failure")

        monkeypatch.setitem(__import__("sys").modules, "sqlite_vec", _FailingVec)

        idx = embeddings.VectorIndex(db_path)
        with caplog.at_level(logging.WARNING, logger="kb.query.embeddings"):
            r1 = idx.query([0.0, 0.0, 0.0])
            r2 = idx.query([0.0, 0.0, 0.0])
        assert r1 == [] and r2 == []
        assert idx._disabled is True
        warns = [r for r in caplog.records if "sqlite_vec extension load failed" in r.getMessage()]
        assert len(warns) == 1, f"expected exactly one WARNING, got {len(warns)}"


# ---------------------------------------------------------------------------
# AC6 — engine.py passes pre-loaded pages to build_graph
# ---------------------------------------------------------------------------


class TestPageRankPassesPreloadedPages:
    """AC6 — _compute_pagerank_scores forwards preloaded_pages into build_graph."""

    def test_build_graph_receives_pages_kwarg(self, tmp_wiki, create_wiki_page, monkeypatch):
        from kb.query import engine

        create_wiki_page(page_id="concepts/a", title="A", content="Body", wiki_dir=tmp_wiki)
        with engine._PAGERANK_CACHE_LOCK:
            engine._PAGERANK_CACHE.clear()

        received: dict = {}

        def _spy(wiki_dir=None, pages=None):
            received["pages"] = pages
            import networkx as nx

            return nx.DiGraph()

        monkeypatch.setattr(engine, "build_graph", _spy)
        sentinel = [{"id": "concepts/a", "content": "Body"}]
        engine._compute_pagerank_scores(tmp_wiki, preloaded_pages=sentinel)
        assert received["pages"] is sentinel, "preloaded_pages must be threaded to build_graph"


# ---------------------------------------------------------------------------
# AC7 — _update_existing_page normalizes CRLF
# ---------------------------------------------------------------------------


class TestUpdateExistingPageCRLF:
    """AC7 — CRLF frontmatter no longer bypasses _SOURCE_BLOCK_RE."""

    def test_crlf_frontmatter_matches_source_block(self, tmp_path):
        from kb.ingest import pipeline

        page = tmp_path / "page.md"
        # Note: Windows CRLF throughout frontmatter.
        page.write_bytes(
            b"---\r\n"
            b'title: "Test"\r\n'
            b"source:\r\n"
            b'  - "raw/articles/one.md"\r\n'
            b"updated: 2026-04-01\r\n"
            b"---\r\n\r\n"
            b"# Body\r\n\r\n"
            b"## References\r\n"
            b"- Mentioned in raw/articles/one.md\r\n"
        )
        pipeline._update_existing_page(page, "raw/articles/two.md")
        content = page.read_text(encoding="utf-8")
        # Two distinct source entries should appear in the frontmatter source
        # list, not a duplicated key block.
        source_count = content.count("source:")
        assert source_count == 1, f"expected single `source:` block, got {source_count}"
        assert "raw/articles/two.md" in content


# ---------------------------------------------------------------------------
# AC8 — cross-batch slug collision with entity precedence
# ---------------------------------------------------------------------------


class TestCrossBatchSlugCollision:
    """AC8 — entity and concept batches sharing a slug collapse entity-first."""

    def test_entity_wins_concept_skipped(self, tmp_wiki, caplog):
        from kb.ingest import pipeline

        shared: dict[str, str] = {}
        source_ref = "raw/articles/x.md"
        ent_result = pipeline._process_item_batch(
            items_raw=["RAG"],
            field_name="entities_mentioned",
            max_count=50,
            page_type="entity",
            source_ref=source_ref,
            extraction={"title": "X"},
            wiki_dir=tmp_wiki,
            shared_seen=shared,
        )
        with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
            con_result = pipeline._process_item_batch(
                items_raw=["RAG"],
                field_name="concepts_mentioned",
                max_count=50,
                page_type="concept",
                source_ref=source_ref,
                extraction={"title": "X"},
                wiki_dir=tmp_wiki,
                shared_seen=shared,
            )
        ent_created, ent_updated, ent_skipped, _, _ = ent_result
        con_created, con_updated, con_skipped, _, _ = con_result
        assert "entities/rag" in ent_created
        assert con_created == [] and con_updated == []
        assert any("cross-type" in s.lower() for s in con_skipped), con_skipped
        assert any("cross-type" in r.getMessage().lower() for r in caplog.records), (
            "expected WARNING log on cross-type collision"
        )


# ---------------------------------------------------------------------------
# AC9 — CLI KB_DEBUG=1 prints traceback
# ---------------------------------------------------------------------------


class TestCliKbDebugTraceback:
    """AC9 — behavioural test via Click CliRunner, not a getsource grep."""

    def test_kb_debug_env_prints_traceback(self):
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["ingest", "/__nonexistent_cycle6_test_path__.md"],
            env={"KB_DEBUG": "1"},
        )
        assert result.exit_code == 1
        # Both the user-facing line AND the full traceback must appear.
        assert "Error:" in result.output
        assert "Traceback" in result.output, (
            "KB_DEBUG=1 must surface full traceback (AC9). output=" + result.output[:500]
        )

    def test_no_debug_default_suppresses_traceback(self):
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        # Force KB_DEBUG off in case the test runner set it.
        result = runner.invoke(
            cli,
            ["ingest", "/__nonexistent_cycle6_test_path__.md"],
            env={"KB_DEBUG": "0"},
        )
        assert result.exit_code == 1
        assert "Error:" in result.output
        assert "Traceback" not in result.output


# ---------------------------------------------------------------------------
# AC10 — RRF fusion stores (score, meta) tuples
# ---------------------------------------------------------------------------


class TestRRFTupleStorage:
    """AC10 — structural refactor; existing behaviour preserved."""

    def test_duplicate_ids_accumulate_score_later_meta_wins(self):
        from kb.query.hybrid import rrf_fusion

        # Two lists with overlapping page id "concepts/a"; later list wins metadata.
        list_a = [{"id": "concepts/a", "title": "from-a"}]
        list_b = [{"id": "concepts/a", "title": "from-b"}]
        out = rrf_fusion([list_a, list_b])
        assert len(out) == 1
        assert out[0]["title"] == "from-b", "later list should win on metadata"
        # Score must be sum of the two RRF contributions (1/(60+0) + 1/(60+0)).
        assert out[0]["score"] == pytest.approx(2.0 / 60, rel=0.01)


# ---------------------------------------------------------------------------
# AC11 — dedup cross-type skip
# ---------------------------------------------------------------------------


class TestDedupCrossTypeSkip:
    """AC11 — Jaccard threshold doesn't prune across different page types."""

    def test_summary_and_entity_survive_high_similarity(self):
        from kb.query.dedup import _dedup_by_text_similarity

        body = (
            "retrieval augmented generation is a hybrid approach combining "
            "language models with external knowledge lookup"
        )
        results = [
            {"id": "summaries/rag-paper", "type": "summary", "content": body, "score": 10},
            {"id": "entities/rag", "type": "entity", "content": body, "score": 8},
        ]
        out = _dedup_by_text_similarity(results, threshold=0.5)
        assert len(out) == 2, "cross-type pair should not be pruned by similarity"

    def test_same_type_pair_still_pruned(self):
        from kb.query.dedup import _dedup_by_text_similarity

        body = "retrieval augmented generation external knowledge lookup approach"
        results = [
            {"id": "concepts/rag-a", "type": "concept", "content": body, "score": 10},
            {"id": "concepts/rag-b", "type": "concept", "content": body, "score": 8},
        ]
        out = _dedup_by_text_similarity(results, threshold=0.5)
        assert len(out) == 1, "same-type near-duplicate should still be pruned"


# ---------------------------------------------------------------------------
# AC12 — analyzer: break chain → _iter_connection_pairs helper
# ---------------------------------------------------------------------------


class TestConnectionPairsHelper:
    """AC12 — helper yields pairs up to the cap with ONE warning."""

    def test_iter_connection_pairs_caps_and_warns(self, caplog):
        from kb.evolve import analyzer

        # 5 pages sharing a term → 10 distinct pairs, inside MIN/MAX_PAGES_FOR_TERM
        # bounds (2..5). With cap=3 we should hit truncation after the 3rd pair.
        page_ids = [f"concepts/p{i}" for i in range(5)]
        term_index = {"sharedterm": page_ids}
        with caplog.at_level(logging.WARNING, logger="kb.evolve.analyzer"):
            pairs = list(analyzer._iter_connection_pairs(term_index, cap=3))
        distinct = {pair for pair, _ in pairs}
        assert len(distinct) <= 3
        assert any("connection analysis truncated" in r.getMessage() for r in caplog.records), (
            "expected single truncation WARNING; "
            f"records={[r.getMessage() for r in caplog.records]}"
        )


# ---------------------------------------------------------------------------
# AC13 — graph_stats include_centrality default False
# ---------------------------------------------------------------------------


class TestGraphStatsIncludeCentrality:
    """AC13 — betweenness_centrality skipped unless opted in."""

    def test_default_skips_betweenness(self, monkeypatch):
        import networkx as nx

        from kb.graph import builder

        call_count = {"n": 0}
        real_bc = nx.betweenness_centrality

        def _spy(*args, **kwargs):
            call_count["n"] += 1
            return real_bc(*args, **kwargs)

        monkeypatch.setattr(nx, "betweenness_centrality", _spy)
        g = nx.DiGraph()
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("a", "c")
        stats = builder.graph_stats(g)
        assert call_count["n"] == 0, "betweenness_centrality must not run by default"
        assert stats["bridge_nodes"] == []
        assert stats["bridge_nodes_status"] == "skipped"

    def test_opt_in_runs_betweenness(self, monkeypatch):
        import networkx as nx

        from kb.graph import builder

        g = nx.DiGraph()
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("a", "c")
        stats = builder.graph_stats(g, include_centrality=True)
        assert stats["bridge_nodes_status"] in {"ok", "degenerate"}


# ---------------------------------------------------------------------------
# AC14 — load_purpose is lru_cached; docstring documents cache_clear
# ---------------------------------------------------------------------------


class TestLoadPurposeCached:
    """AC14 — first read cached; mutation requires cache_clear()."""

    def test_cached_until_cache_clear(self, tmp_wiki):
        from kb.utils.pages import load_purpose

        load_purpose.cache_clear()
        purpose = tmp_wiki / "purpose.md"
        purpose.write_text("first", encoding="utf-8")
        assert load_purpose(tmp_wiki) == "first"

        purpose.write_text("second", encoding="utf-8")
        assert load_purpose(tmp_wiki) == "first", (
            "without cache_clear(), lru_cache must return the first value"
        )
        load_purpose.cache_clear()
        assert load_purpose(tmp_wiki) == "second"

    def test_docstring_documents_cache_clear_contract(self):
        from kb.utils.pages import load_purpose

        doc = load_purpose.__doc__ or ""
        assert "cache_clear" in doc, "AC14 condition: docstring must mention cache_clear() contract"


# ---------------------------------------------------------------------------
# AC15 — load_all_pages return_errors
# ---------------------------------------------------------------------------


class TestLoadAllPagesReturnErrors:
    """AC15 — default returns list; return_errors=True returns dict."""

    def test_default_returns_list(self, tmp_wiki, create_wiki_page):
        from kb.utils.pages import load_all_pages

        create_wiki_page(page_id="concepts/a", title="A", content="body", wiki_dir=tmp_wiki)
        out = load_all_pages(tmp_wiki)
        assert isinstance(out, list)
        assert any(p["id"] == "concepts/a" for p in out)

    def test_return_errors_reports_count(self, tmp_wiki, create_wiki_page):
        from kb.utils.pages import load_all_pages

        create_wiki_page(page_id="concepts/good", title="Good", content="body", wiki_dir=tmp_wiki)
        # Write an unparseable frontmatter to trigger a load error.
        bad = tmp_wiki / "concepts" / "bad.md"
        bad.write_text("---\n:: not-yaml :: \n---\nbody\n", encoding="utf-8")
        out = load_all_pages(tmp_wiki, return_errors=True)
        assert isinstance(out, dict)
        assert "pages" in out and "load_errors" in out
        assert out["load_errors"] >= 1


# ---------------------------------------------------------------------------
# PR #20 R1 Sonnet BLOCKER: behavioral connection-reuse regression
# (replaces the prior source-scan `grep sqlite3.connect` test)
# ---------------------------------------------------------------------------


class TestVectorIndexQueryDoesNotReconnect:
    """Behavioral regression for AC5 — ``query()`` must NOT open a new
    sqlite3 connection on every invocation. A per-call reconnect pattern
    would pass a source-grep test even after revert; this monkeypatches
    ``sqlite3.connect`` as a spy and asserts at most one call across N
    sequential ``query()`` invocations."""

    def test_sequential_queries_reuse_single_connection(self, tmp_path, monkeypatch):
        import sys

        from kb.query import embeddings

        db_path = tmp_path / "vec.db"
        sqlite3.connect(str(db_path)).close()

        class _StubVec:
            @staticmethod
            def load(_conn):
                return None

            @staticmethod
            def serialize_float32(_vec):
                return b""

        monkeypatch.setitem(sys.modules, "sqlite_vec", _StubVec)

        call_count = {"n": 0}
        real_connect = sqlite3.connect

        def _spy_connect(*args, **kwargs):
            call_count["n"] += 1
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(embeddings.sqlite3, "connect", _spy_connect)

        idx = embeddings.VectorIndex(db_path)
        idx.query([0.0, 0.0, 0.0])
        idx.query([0.0, 0.0, 0.0])
        idx.query([0.0, 0.0, 0.0])
        assert call_count["n"] <= 1, (
            f"query() reconnected {call_count['n']} times — must reuse _conn (AC5)"
        )


# ---------------------------------------------------------------------------
# PR #20 R1 Codex NEW-ISSUE: same-batch duplicate NOT cross-type
# ---------------------------------------------------------------------------


class TestSharedSeenSameBatchDuplicateNotCrossType:
    """R1 Codex NEW-ISSUE — ``entities=["RAG", "RAG"]`` with ``shared_seen``
    previously hit the cross-type branch because prev==item AND shared_seen
    was not None. After the (item, page_type) tuple fix, same-type + same-item
    must silently dedup with NO cross-type WARNING."""

    def test_same_name_in_same_batch_silent_dedup(self, tmp_wiki, caplog):
        from kb.ingest import pipeline

        shared: dict = {}
        with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
            result = pipeline._process_item_batch(
                items_raw=["RAG", "RAG"],
                field_name="entities_mentioned",
                max_count=50,
                page_type="entity",
                source_ref="raw/articles/x.md",
                extraction={"title": "X"},
                wiki_dir=tmp_wiki,
                shared_seen=shared,
            )
        created, _updated, skipped, _new_titles, _valid = result
        assert created == ["entities/rag"]
        assert not any("cross-type" in s.lower() for s in skipped), skipped
        assert not any("cross-type" in r.getMessage().lower() for r in caplog.records), (
            "same-batch duplicate wrongly classified as cross-type"
        )


# ---------------------------------------------------------------------------
# PR #20 R1 Sonnet M2: --verbose flag path (separate from KB_DEBUG env)
# ---------------------------------------------------------------------------


class TestVectorIndexCrossThreadQuery:
    """R2 Codex NEW-ISSUE — sqlite3 connections are thread-affine by default.
    The shared-connection AC5 model must set ``check_same_thread=False`` so
    a query() call from a worker thread doesn't raise ``ProgrammingError:
    SQLite objects created in a thread can only be used in that same thread.``"""

    def test_query_from_worker_thread_does_not_raise(self, tmp_path, monkeypatch):
        import sys
        import threading

        from kb.query import embeddings

        db_path = tmp_path / "vec.db"
        sqlite3.connect(str(db_path)).close()

        class _StubVec:
            @staticmethod
            def load(_conn):
                return None

            @staticmethod
            def serialize_float32(_vec):
                return b""

        monkeypatch.setitem(sys.modules, "sqlite_vec", _StubVec)

        idx = embeddings.VectorIndex(db_path)
        # Prime the connection on the main thread (triggers _ensure_conn).
        idx.query([0.0, 0.0, 0.0])

        errors: list[BaseException] = []

        def _run():
            try:
                idx.query([0.0, 0.0, 0.0])
            except BaseException as e:  # noqa: BLE001 — capturing all for assertion
                errors.append(e)

        t = threading.Thread(target=_run)
        t.start()
        t.join(timeout=5.0)
        assert not t.is_alive(), "worker thread did not complete"
        assert not errors, (
            f"cross-thread query raised {errors[0]!r}; check_same_thread=False missing"
        )


class TestCliVerboseFlagPrintsTraceback:
    """R1 Sonnet M2 — behavioral test for the ``--verbose`` Click-flag path.
    Both env-var and flag triggers must surface tracebacks; prior test
    covered only the env-var branch."""

    def test_verbose_flag_prints_traceback(self):
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--verbose", "ingest", "/__nonexistent_cycle6_r1_test__.md"],
            env={"KB_DEBUG": ""},  # Force env off so only the flag triggers
        )
        assert result.exit_code == 1
        assert "Traceback" in result.output, (
            f"--verbose flag must surface traceback without KB_DEBUG. output={result.output[:500]}"
        )
