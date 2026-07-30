"""Tests for the query engine and citations."""

import os
from datetime import UTC, date, datetime, time
from pathlib import Path
from unittest.mock import patch

import pytest

from kb.query.citations import extract_citations, format_citations
from kb.query.embeddings import _vec_db_path
from kb.query.engine import _flag_stale_results, query_wiki, search_pages


def _create_wiki_page(path: Path, title: str, content: str, page_type: str = "concept") -> None:
    """Helper to create a wiki page with frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = f"""---
title: "{title}"
source:
  - raw/articles/test.md
created: 2026-04-06
updated: 2026-04-06
type: {page_type}
confidence: stated
---

"""
    path.write_text(fm + content, encoding="utf-8")


# ── Citation tests ─────────────────────────────────────────────


def test_extract_citations():
    """extract_citations finds [source: path] patterns."""
    text = "RAG is important [source: concepts/rag] and uses LLMs [source: concepts/llm]."
    citations = extract_citations(text)
    assert len(citations) == 2
    assert citations[0]["path"] == "concepts/rag"
    assert citations[0]["type"] == "wiki"


def test_extract_citations_raw_refs():
    """extract_citations finds [ref: path] patterns."""
    text = "According to the paper [ref: raw/papers/attention.pdf], transformers work."
    citations = extract_citations(text)
    assert len(citations) == 1
    assert citations[0]["type"] == "raw"
    assert citations[0]["path"] == "raw/papers/attention.pdf"


def test_extract_citations_empty():
    """extract_citations returns empty list for no citations."""
    assert extract_citations("No citations here.") == []


def test_format_citations():
    """format_citations produces markdown source list."""
    citations = [
        {"type": "wiki", "path": "concepts/rag", "context": "..."},
        {"type": "raw", "path": "raw/papers/test.pdf", "context": "..."},
    ]
    result = format_citations(citations)
    assert "[[concepts/rag]]" in result
    assert "`raw/papers/test.pdf`" in result


def test_format_citations_deduplicates():
    """format_citations removes duplicate paths."""
    citations = [
        {"type": "wiki", "path": "concepts/rag", "context": "..."},
        {"type": "wiki", "path": "concepts/rag", "context": "..."},
    ]
    result = format_citations(citations)
    assert result.count("concepts/rag") == 1


def test_format_citations_empty():
    """format_citations returns empty string for no citations."""
    assert format_citations([]) == ""


def test_format_citations_html_mode():
    """HTML mode returns <ul> with escaped <a> anchors."""
    citations = [
        {"type": "wiki", "path": "concepts/rag", "context": "..."},
        {"type": "raw", "path": "raw/articles/foo.md", "context": "..."},
    ]
    result = format_citations(citations, mode="html")
    assert "<ul" in result
    assert '<a href="./wiki/concepts/rag.md">concepts/rag</a>' in result
    assert "<code>raw/articles/foo.md</code>" in result


def test_format_citations_marp_mode():
    """Marp mode matches markdown rendering (kept distinct for future divergence)."""
    citations = [
        {"type": "wiki", "path": "concepts/rag", "context": "..."},
        {"type": "raw", "path": "raw/a.md", "context": "..."},
    ]
    out = format_citations(citations, mode="marp")
    assert "[[concepts/rag]]" in out
    assert "`raw/a.md`" in out


def test_format_citations_default_mode_unchanged():
    """Default mode must match previous behavior exactly — no call-site breakage."""
    citations = [{"type": "wiki", "path": "concepts/rag", "context": "x"}]
    legacy = format_citations(citations)
    explicit = format_citations(citations, mode="markdown")
    assert legacy == explicit
    assert "[[concepts/rag]]" in legacy


def test_format_citations_invalid_mode():
    """Unknown mode raises ValueError."""
    with pytest.raises(ValueError, match="mode"):
        format_citations([], mode="latex")


# ── Search tests ───────────────────────────────────────────────


def test_search_pages(tmp_wiki):
    """search_pages finds pages matching query terms."""
    _create_wiki_page(
        tmp_wiki / "concepts" / "rag.md",
        "Retrieval Augmented Generation",
        "RAG combines retrieval with generation for better LLM answers.",
    )
    _create_wiki_page(
        tmp_wiki / "concepts" / "fine-tuning.md",
        "Fine-Tuning",
        "Fine-tuning adapts a pre-trained model to specific tasks.",
    )
    results = search_pages("How does RAG work?", tmp_wiki)
    assert len(results) >= 1
    assert results[0]["id"] == "concepts/rag"


def test_search_pages_title_boost(tmp_wiki):
    """search_pages weights title matches higher than content matches."""
    _create_wiki_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "A technique for language models.",
    )
    _create_wiki_page(
        tmp_wiki / "summaries" / "article1.md",
        "Some Article",
        "This article mentions RAG briefly in passing.",
        page_type="summary",
    )
    results = search_pages("RAG", tmp_wiki)
    assert len(results) >= 1
    # Title match should rank higher
    assert results[0]["id"] == "concepts/rag"


def test_search_pages_empty_wiki(tmp_wiki):
    """search_pages returns empty list for empty wiki."""
    results = search_pages("anything", tmp_wiki)
    assert results == []


def test_search_pages_no_match(tmp_wiki):
    """search_pages returns empty list when no pages match."""
    _create_wiki_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "About retrieval augmented generation.",
    )
    results = search_pages("quantum computing", tmp_wiki)
    assert results == []


# ── Cycle 10 — vector min-similarity threshold (folded from test_cycle10_vector_min_sim.py) ─


class _FakeVectorIndexCycle10:
    """Stub vector index returning preset (page_id, distance) hits."""

    def __init__(self, hits):
        self.hits = hits

    def query(self, _vec, limit):
        return self.hits[:limit]


def _enable_fake_vector_index_cycle10(tmp_wiki, monkeypatch, hits):
    vec_path = _vec_db_path(tmp_wiki)
    vec_path.parent.mkdir(parents=True, exist_ok=True)
    vec_path.touch()

    monkeypatch.setattr("kb.query.embeddings.embed_texts", lambda _texts: [[0.1, 0.2]])
    monkeypatch.setattr(
        "kb.query.embeddings.get_vector_index",
        lambda _path: _FakeVectorIndexCycle10(hits),
    )


def test_search_pages_filters_low_cosine_vector_hits(tmp_wiki, create_wiki_page, monkeypatch):
    create_wiki_page(
        "concepts/page-high",
        title="High Alpha",
        content="unrelated alpha body",
        wiki_dir=tmp_wiki,
    )
    create_wiki_page(
        "concepts/page-low",
        title="Low Beta",
        content="unrelated beta body",
        wiki_dir=tmp_wiki,
    )
    _enable_fake_vector_index_cycle10(
        tmp_wiki,
        monkeypatch,
        [("concepts/page-high", 1.0), ("concepts/page-low", 3.0)],
    )

    results = search_pages("test query", max_results=10, wiki_dir=tmp_wiki)

    assert [result["id"] for result in results] == ["concepts/page-high"]


def test_search_pages_returns_empty_when_bm25_empty_and_all_vec_below_threshold(
    tmp_wiki, create_wiki_page, monkeypatch
):
    create_wiki_page(
        "concepts/page-a",
        title="Alpha",
        content="unrelated alpha body",
        wiki_dir=tmp_wiki,
    )
    create_wiki_page(
        "concepts/page-b",
        title="Beta",
        content="unrelated beta body",
        wiki_dir=tmp_wiki,
    )
    _enable_fake_vector_index_cycle10(
        tmp_wiki,
        monkeypatch,
        [("concepts/page-a", 3.0), ("concepts/page-b", 4.0)],
    )

    results = search_pages("noise query", max_results=10, wiki_dir=tmp_wiki)

    assert results == []


# ── Query integration tests ────────────────────────────────────


@patch("kb.query.engine.call_llm")
def test_query_wiki(mock_llm, tmp_wiki):
    """query_wiki searches, builds context, and calls LLM."""
    mock_llm.return_value = "RAG combines retrieval with generation [source: concepts/rag]."
    _create_wiki_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "RAG uses a retriever to find relevant documents before generating.",
    )
    result = query_wiki("What is RAG?", tmp_wiki)
    assert result["question"] == "What is RAG?"
    assert "RAG" in result["answer"]
    assert len(result["citations"]) >= 1
    assert "concepts/rag" in result["source_pages"]
    mock_llm.assert_called_once()


@patch("kb.query.engine.call_llm")
def test_query_wiki_no_results(mock_llm, tmp_wiki):
    """query_wiki handles empty wiki gracefully."""
    result = query_wiki("What is quantum computing?", tmp_wiki)
    assert "No relevant pages" in result["answer"]
    mock_llm.assert_not_called()


# ── Phase 4.5 HIGH regression tests ──────────────────────────────────────────


@patch("kb.query.engine.call_llm")
def test_query_wiki_h5_raw_dir_derivation(mock_llm, tmp_wiki):
    """Regression: Phase 4.5 HIGH item H5 (drop dead raw_dir containment try/except).

    query_wiki must still work after the dead candidate.relative_to() block was removed.
    raw_dir is now derived unconditionally from wiki_dir without a try/except guard.
    """
    mock_llm.return_value = "RAG stands for Retrieval-Augmented Generation."
    _create_wiki_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "RAG is a technique combining retrieval with generation.",
    )
    # wiki_dir is tmp_wiki — raw is derived as tmp_wiki.parent / "raw"
    result = query_wiki("What is RAG?", tmp_wiki)
    # Must return a valid dict (no crash from the removed try/except)
    assert isinstance(result, dict)
    assert "answer" in result
    assert "citations" in result


# ── _flag_stale_results edge cases ─────────────────────────────


class TestFlagStaleResultsEdgeCases:
    """Folded from tests/test_cycle11_stale_results.py cycle 40 (cycle 11
    AC9/AC10/AC11 stale-result edge-case contract tests).
    """

    def test_flag_stale_results_empty_sources_is_not_stale(self):
        results = _flag_stale_results([{"updated": "2026-01-01", "sources": []}])

        assert results == [{"updated": "2026-01-01", "sources": [], "stale": False}]

    def test_flag_stale_results_missing_sources_is_not_stale(self):
        results = _flag_stale_results([{"updated": "2026-01-01"}])

        assert results == [{"updated": "2026-01-01", "stale": False}]

    # Cycle 15 AC1 note — removed the `20260101` int parametrize case. Python 3.11+
    # extended `date.fromisoformat` to accept YYYYMMDD "basic format", so the
    # integer 20260101 → str "20260101" parses to 2026-01-01. Combined with the
    # cycle-15 decay gate (90d default for unknown sources), a page "updated" in
    # early January gets flagged stale by April, violating the original intent.
    # The remaining non-ISO fixtures are genuinely unparseable and still round-trip.
    @pytest.mark.parametrize("updated", ["yesterday", "04/19/2026", ""])
    def test_flag_stale_results_non_iso_updated_values_are_not_stale(self, updated):
        results = _flag_stale_results([{"updated": updated, "sources": ["raw/source.md"]}])

        assert results == [{"updated": updated, "sources": ["raw/source.md"], "stale": False}]

    def test_flag_stale_results_source_mtime_equal_to_updated_is_not_stale(self, tmp_path):
        source = tmp_path / "raw" / "source.md"
        source.parent.mkdir()
        source.write_text("source\n", encoding="utf-8")

        # date.today(), not a fixed date — the Signal-2 decay gate flags pages
        # older than SOURCE_DECAY_DEFAULT_DAYS, so a hardcoded date ages out.
        source_date = date.today()
        source_time = datetime.combine(source_date, time.min, tzinfo=UTC).timestamp()
        os.utime(source, (source_time, source_time))

        results = _flag_stale_results(
            [{"updated": source_date.isoformat(), "sources": ["raw/source.md"]}],
            project_root=tmp_path,
        )

        assert results == [
            {"updated": source_date.isoformat(), "sources": ["raw/source.md"], "stale": False}
        ]


# ── Tier-1 budget wiring (cycle 52 fold) ─
# Source: tests/test_cycle15_query_tier1_wiring.py (deleted in same commit).
# Cycle 15 AC2/AC21 — `_build_query_context` uses tier1_budget_for.
# Function-local imports per cycle-19 L2 lazy-import safety in receiver.


def _summary_page(pid: str, content_chars: int) -> dict:
    return {
        "id": pid,
        "path": f"/wiki/summaries/{pid}.md",
        "title": f"Summary {pid}",
        "type": "summary",
        "confidence": "stated",
        "content": "x" * content_chars,
        "score": 1.0,
    }


def test_tier1_wiki_pages_budget_controls_summaries(monkeypatch):
    """AC21 — monkeypatching split['wiki_pages'] shrinks summaries cap proportionally."""
    from kb import config
    from kb.query.engine import _build_query_context

    # Create many 2KB summaries that would all fit at 60% split but NOT at 10%.
    pages = [_summary_page(f"s{i}", content_chars=2_000) for i in range(20)]

    # At 60% split (default), wiki_pages_budget = 20_000 * 60 / 100 = 12_000 chars.
    # A 2KB summary + header (~100 chars) = ~2100 chars; 5-6 fit into 12K.
    default_result = _build_query_context(pages)
    default_count = len(default_result["context_pages"])
    assert default_count >= 5, "default 60% split should admit at least 5 summaries"

    # Monkeypatch wiki_pages split to 10 → wiki_pages_budget = 20_000 * 10 / 100 = 2_000.
    # Only 1 summary fits (first-page truncation path).
    shrunken = dict(config.CONTEXT_TIER1_SPLIT)
    shrunken["wiki_pages"] = 10
    shrunken["chat_history"] = 20
    shrunken["index"] = 15
    shrunken["system"] = 55  # sum to 100
    monkeypatch.setattr(config, "CONTEXT_TIER1_SPLIT", shrunken)

    shrunken_result = _build_query_context(pages)
    shrunken_count = len(shrunken_result["context_pages"])
    assert shrunken_count < default_count, (
        "shrinking wiki_pages split must reduce summaries admitted; "
        f"default={default_count} shrunken={shrunken_count}"
    )


def test_tier1_budget_for_is_called(monkeypatch):
    """AC21 — _build_query_context invokes tier1_budget_for('wiki_pages').

    R1 MINOR 2 — only the engine-module alias is observable at the call site
    (``_build_query_context`` resolves ``tier1_budget_for`` from its own
    module namespace), so we patch ONLY the engine import. Patching
    ``config.tier1_budget_for`` would be redundant noise.
    """
    import kb.query.engine as engine_mod
    from kb import config
    from kb.query.engine import _build_query_context

    spy_calls: list[str] = []
    real = config.tier1_budget_for

    def _spy(component: str) -> int:
        spy_calls.append(component)
        return real(component)

    # Patch the engine's import alias so the spy is picked up.
    monkeypatch.setattr(engine_mod, "tier1_budget_for", _spy)

    pages = [_summary_page("x", content_chars=500)]
    _build_query_context(pages)
    assert "wiki_pages" in spy_calls, (
        f"expected tier1_budget_for('wiki_pages') call; got {spy_calls}"
    )


# ── Cycle 69 AC16 — fold from test_v0917_rewriter.py (4 tests, bare-fn shape per Q5) ─


def test_rewrite_query_standalone_query_unchanged():
    from kb.query.rewriter import rewrite_query

    result = rewrite_query("What is a transformer?", conversation_context="")
    assert result == "What is a transformer?"


def test_rewrite_query_returns_string():
    """Mock call_llm so this test does not require a real API key.

    The question has a deictic word ("it") which triggers _should_rewrite.
    """
    from unittest.mock import patch

    from kb.query.rewriter import rewrite_query

    with patch("kb.query.rewriter.call_llm", return_value="How does attention work?"):
        result = rewrite_query(
            "How does it work?",
            conversation_context="User asked about attention mechanisms in transformers.",
        )
    assert isinstance(result, str)
    assert len(result) > 0


def test_rewrite_query_no_context_returns_original():
    from kb.query.rewriter import rewrite_query

    result = rewrite_query("Tell me more", conversation_context=None)
    assert result == "Tell me more"


def test_rewrite_query_empty_query():
    from kb.query.rewriter import rewrite_query

    result = rewrite_query("", conversation_context="some context")
    assert result == ""


# ── Cycle 69 AC17 — folded from test_v0917_raw_fallback.py (3 tests, class host shape) ─


class TestSearchRawSources:
    def test_finds_matching_raw_file(self, tmp_project, create_raw_source):
        from kb.query.engine import search_raw_sources

        create_raw_source(
            "raw/articles/attention.md", "The attention mechanism computes...", tmp_project
        )
        results = search_raw_sources(
            "attention mechanism", raw_dir=tmp_project / "raw", max_results=5
        )
        assert len(results) >= 1
        assert any("attention" in r["id"] for r in results)

    def test_returns_empty_for_no_match(self, tmp_project, create_raw_source):
        from kb.query.engine import search_raw_sources

        create_raw_source("raw/articles/unrelated.md", "Nothing relevant.", tmp_project)
        results = search_raw_sources(
            "quantum computing entanglement", raw_dir=tmp_project / "raw", max_results=5
        )
        assert len(results) == 0

    def test_result_has_expected_keys(self, tmp_project, create_raw_source):
        from kb.query.engine import search_raw_sources

        create_raw_source("raw/articles/test.md", "Test content about transformers.", tmp_project)
        results = search_raw_sources("transformers", raw_dir=tmp_project / "raw", max_results=5)
        if results:
            r = results[0]
            assert "id" in r
            assert "content" in r
            assert "score" in r
            assert r["id"].startswith("raw/")


# ── Cycle 69 AC19 — fold from test_v0917_hybrid.py::TestRRFFusion (-> TestHybridQuery, Q5) ─


class TestHybridQuery:
    def test_single_list(self):
        from kb.query.hybrid import rrf_fusion

        results = [
            {"id": "a", "score": 10.0},
            {"id": "b", "score": 5.0},
        ]
        fused = rrf_fusion([results])
        assert len(fused) == 2
        assert fused[0]["id"] == "a"  # Rank 0 → 1/(60+0) > 1/(60+1)

    def test_two_lists_same_order(self):
        from kb.query.hybrid import rrf_fusion

        list1 = [{"id": "a", "score": 10.0}, {"id": "b", "score": 5.0}]
        list2 = [{"id": "a", "score": 0.9}, {"id": "b", "score": 0.5}]
        fused = rrf_fusion([list1, list2])
        assert fused[0]["id"] == "a"  # Appears rank 0 in both lists

    def test_two_lists_disjoint(self):
        from kb.query.hybrid import rrf_fusion

        list1 = [{"id": "a", "score": 10.0}]
        list2 = [{"id": "b", "score": 0.9}]
        fused = rrf_fusion([list1, list2])
        assert len(fused) == 2
        # Both at rank 0 in their list, so equal RRF score — either order OK
        ids = {r["id"] for r in fused}
        assert ids == {"a", "b"}

    def test_boosted_by_multiple_lists(self):
        from kb.query.hybrid import rrf_fusion

        list1 = [{"id": "a", "score": 10.0}, {"id": "b", "score": 5.0}]
        list2 = [{"id": "b", "score": 0.9}, {"id": "c", "score": 0.5}]
        fused = rrf_fusion([list1, list2])
        # b appears in both lists (rank 1 + rank 0) so gets boosted
        b_score = next(r["score"] for r in fused if r["id"] == "b")
        c_score = next(r["score"] for r in fused if r["id"] == "c")
        assert b_score > c_score

    def test_empty_lists(self):
        from kb.query.hybrid import rrf_fusion

        assert rrf_fusion([]) == []
        assert rrf_fusion([[], []]) == []

    def test_rrf_scores_are_positive(self):
        from kb.query.hybrid import rrf_fusion

        results = [{"id": "a", "score": 1.0}]
        fused = rrf_fusion([results])
        assert all(r["score"] > 0 for r in fused)


# ─────────────────────────────────────────────────────────────────────
# Folded from tests/test_v01004_query_correctness.py
# (cycle 77 freeze-and-fold) — Phase 4 query/ correctness fixes.
# Tests moved VERBATIM; names preserved; provenance in CHANGELOG-history cycle-77.
# ─────────────────────────────────────────────────────────────────────


def test_citation_rejects_double_dot_midcomponent():
    from kb.query.citations import extract_citations

    text = "See [source: raw/a..b/page]."
    cites = extract_citations(text)
    assert cites == [], f"Expected empty but got {cites}"


def test_citation_rejects_empty_component():
    from kb.query.citations import extract_citations

    text = "See [source: raw//page]."
    assert extract_citations(text) == []


def test_citation_accepts_valid_path():
    from kb.query.citations import extract_citations

    text = "See [source: raw/articles/my-paper.md]."
    cites = extract_citations(text)
    assert len(cites) == 1


def test_rewrite_query_falls_back_on_overlong_output(monkeypatch):
    from kb.query import rewriter as _rw

    def _fake_llm(prompt, tier="scan", **kwargs):
        return "The question asks about X. Standalone version: What is RAG?"

    monkeypatch.setattr(_rw, "call_llm", _fake_llm)
    out = _rw.rewrite_query("What is RAG?", conversation_context="user: earlier\nassistant: ok")
    # Fallback: output is > 3x len of original, so use original
    assert out == "What is RAG?"


def test_rewrite_query_skip_heuristic_detects_deictic():
    from kb.query import rewriter as _rw

    assert _rw._should_rewrite("Tell me more about that approach") is True
    assert _rw._should_rewrite("What is retrieval augmented generation system") is False


def test_bm25_empty_corpus_logs_debug_not_warning(caplog):
    import logging

    from kb.query.bm25 import BM25Index

    # BM25Index takes list of token lists; pass one doc with no tokens → avgdl=0
    with caplog.at_level(logging.DEBUG, logger="kb.query.bm25"):
        BM25Index(documents=[[]])

    # Must have no WARNING records about avgdl
    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    avgdl_warnings = [
        r for r in warning_records if "avgdl" in r.message.lower() or "avg" in r.message.lower()
    ]
    assert avgdl_warnings == [], f"Unexpected avgdl warning: {avgdl_warnings}"


# ─────────────────────────────────────────────────────────────────────
# Folded from tests/test_v01005_query_perf_docs.py
# (cycle 77 freeze-and-fold) — Phase 4 query/ perf and doc fixes.
# Tests moved VERBATIM; names preserved; provenance in CHANGELOG-history cycle-77.
# ─────────────────────────────────────────────────────────────────────


def test_get_vector_index_function_exists():
    from kb.query import embeddings as _em

    assert callable(getattr(_em, "get_vector_index", None)), "get_vector_index must exist"


def test_reset_model_function_exists():
    from kb.query import embeddings as _em

    assert callable(getattr(_em, "_reset_model", None)), "_reset_model must exist"


def test_get_vector_index_caches_instance(monkeypatch, tmp_path):
    from kb.query import embeddings as _em

    build_count = {"n": 0}

    class _FakeIdx:
        def __init__(self, path):
            build_count["n"] += 1

        def query(self, vec, top_k=10):
            return []

    monkeypatch.setattr(_em, "VectorIndex", _FakeIdx)
    _em._reset_model()  # clear cache

    vec_path = str(tmp_path / "fake.vec")
    _em.get_vector_index(vec_path)
    _em.get_vector_index(vec_path)
    assert build_count["n"] == 1, f"Expected 1 VectorIndex build, got {build_count['n']}"


def test_dedup_jaccard_strips_wikilinks():
    from kb.query.dedup import _dedup_by_text_similarity

    # Both pages share wikilinks but have different actual content
    pages = [
        {
            "id": "p1",
            "content_lower": "[[entities/foo]] [[concepts/bar]] quantum computing entanglement",
            "bm25_score": 10,
        },
        {
            "id": "p2",
            "content_lower": "[[entities/foo]] [[concepts/bar]] classical ml gradient descent",
            "bm25_score": 9,
        },
    ]
    out = _dedup_by_text_similarity(pages, threshold=0.85)
    # After stripping wikilink tokens, content is different — both should be kept
    assert len(out) == 2, f"Expected 2 pages, got {len(out)}: {[p['id'] for p in out]}"


def test_mcp_core_logs_trust_merge_failure(monkeypatch, caplog):
    from pathlib import Path

    from kb.mcp import core as _core

    src_text = Path(_core.__file__).read_text(encoding="utf-8")
    # Verify there's a debug log call in the vicinity of the trust merge except block
    assert "logger.debug" in src_text, "Expected logger.debug call in core.py"
    # The specific trust-merge error path — verify it's present
    assert "Trust score" in src_text or "trust" in src_text.lower()


# ═══════════════════════════════════════════════════════════════════════
# Cycle 78 freeze-and-fold — moved verbatim from tests/test_v0917_dedup.py,
# tests/test_v0917_embeddings.py, tests/test_v0917_layered_context.py,
# tests/test_v0917_stale_query.py, and tests/test_v0916_task05.py
# (query/engine + query/citations parts).
# Only deviations: fold-site imports below; one function-local `import time`
# (receiver's module-level `time` is datetime.time).
# ═══════════════════════════════════════════════════════════════════════

import re  # noqa: E402  — fold-site import (cycle 78)
from datetime import timedelta  # noqa: E402  — fold-site import (cycle 78)

from kb.query.dedup import dedup_results  # noqa: E402  — fold-site import (cycle 78)
from kb.query.embeddings import VectorIndex, embed_texts  # noqa: E402  — fold-site (cycle 78)
from kb.query.engine import _build_query_context  # noqa: E402  — fold-site import (cycle 78)

# ── tests/test_v0917_dedup.py — 4-layer search dedup pipeline (Phase 4) ──


def _result(page_id, score, page_type="concept", text="some content here"):
    return {"id": page_id, "score": score, "type": page_type, "content_lower": text}


class TestDedupBySource:
    def test_keeps_highest_score_per_page(self):
        results = [
            _result("concepts/a", 5.0),
            _result("concepts/a", 3.0),
            _result("concepts/b", 4.0),
        ]
        deduped = dedup_results(results)
        ids = [r["id"] for r in deduped]
        assert ids.count("concepts/a") == 1
        assert deduped[0]["score"] == 5.0

    def test_preserves_order_by_score(self):
        results = [
            _result("concepts/a", 5.0),
            _result("concepts/b", 3.0),
            _result("concepts/c", 1.0),
        ]
        deduped = dedup_results(results)
        scores = [r["score"] for r in deduped]
        assert scores == sorted(scores, reverse=True)


class TestDedupByTextSimilarity:
    def test_removes_near_duplicate_text(self):
        results = [
            _result("concepts/a", 5.0, text="the transformer architecture uses attention"),
            _result(
                "concepts/b", 4.0, text="the transformer architecture uses attention mechanisms"
            ),
        ]
        deduped = dedup_results(results, jaccard_threshold=0.7)
        assert len(deduped) == 1
        assert deduped[0]["id"] == "concepts/a"  # Higher score kept

    def test_keeps_different_content(self):
        results = [
            _result("concepts/a", 5.0, text="transformers use self-attention mechanisms"),
            _result("concepts/b", 4.0, text="recurrent neural networks process sequences"),
        ]
        deduped = dedup_results(results)
        assert len(deduped) == 2


class TestDedupByTypeDiversity:
    def test_caps_single_type(self):
        results = [_result(f"entities/e{i}", 10 - i, "entity") for i in range(10)]
        results.append(_result("concepts/c1", 0.5, "concept"))
        deduped = dedup_results(results, max_type_ratio=0.6)
        entity_count = sum(1 for r in deduped if r["type"] == "entity")
        total = len(deduped)
        assert entity_count <= int(total * 0.6) + 1  # Allow rounding


class TestDedupPerPageCap:
    def test_caps_results_per_page(self):
        results = [
            _result("concepts/a", 5.0, text="first chunk about topic"),
            _result("concepts/a", 4.5, text="second chunk about topic"),
            _result("concepts/a", 4.0, text="third chunk about topic"),
        ]
        deduped = dedup_results(results, max_per_page=2)
        a_count = sum(1 for r in deduped if r["id"] == "concepts/a")
        assert a_count <= 2


class TestDedupEndToEnd:
    def test_empty_input(self):
        assert dedup_results([]) == []

    def test_single_result(self):
        results = [_result("concepts/a", 5.0)]
        assert len(dedup_results(results)) == 1


# ── tests/test_v0917_embeddings.py — embedding wrapper + vector index (Phase 4) ──


class TestEmbedTexts:
    def test_returns_array_for_single_text(self):
        vecs = embed_texts(["hello world"])
        assert len(vecs) == 1
        assert len(vecs[0]) > 0

    def test_returns_consistent_dims(self):
        vecs = embed_texts(["first text", "second text", "third text"])
        assert len(vecs) == 3
        dims = {len(v) for v in vecs}
        assert len(dims) == 1  # All same dimension

    def test_empty_input(self):
        vecs = embed_texts([])
        assert vecs == []


class TestVectorIndex:
    def test_build_and_query(self, tmp_path):
        db_path = tmp_path / "test_vec.db"
        idx = VectorIndex(db_path)
        idx.build(
            [
                ("concepts/a", [1.0, 0.0, 0.0]),
                ("concepts/b", [0.0, 1.0, 0.0]),
                ("concepts/c", [0.9, 0.1, 0.0]),
            ]
        )
        results = idx.query([1.0, 0.0, 0.0], limit=2)
        assert len(results) == 2
        # Closest match first
        assert results[0][0] == "concepts/a"
        # Second should be concepts/c (most similar to [1,0,0])
        assert results[1][0] == "concepts/c"

    def test_query_returns_page_id_and_distance(self, tmp_path):
        db_path = tmp_path / "test_vec.db"
        idx = VectorIndex(db_path)
        idx.build([("concepts/a", [1.0, 0.0])])
        results = idx.query([1.0, 0.0], limit=1)
        assert len(results) == 1
        page_id, distance = results[0]
        assert isinstance(page_id, str)
        assert isinstance(distance, float)

    def test_empty_index(self, tmp_path):
        db_path = tmp_path / "test_vec.db"
        idx = VectorIndex(db_path)
        idx.build([])
        results = idx.query([1.0, 0.0], limit=5)
        assert results == []


# ── tests/test_v0917_layered_context.py — layered context assembly (Phase 4) ──


def _page(pid, content, ptype="concept"):
    return {
        "id": pid,
        "title": pid.split("/")[-1].replace("-", " ").title(),
        "type": ptype,
        "confidence": "stated",
        "content": content,
    }


class TestLayeredContextAssembly:
    def test_short_content_fits_entirely(self):
        pages = [_page("concepts/a", "Short content.")]
        ctx = _build_query_context(pages, max_chars=10000)
        assert "concepts/a" in ctx["context"]
        assert "Short content." in ctx["context"]

    def test_summaries_prioritized_in_tier1(self):
        pages = [
            _page("concepts/big", "x" * 5000, "concept"),
            _page("summaries/small", "summary text", "summary"),
        ]
        ctx = _build_query_context(pages, max_chars=6000)
        # Both should fit within 6000 chars
        assert "summaries/small" in ctx["context_pages"]

    def test_budget_respected(self):
        pages = [_page(f"concepts/p{i}", "x" * 2000) for i in range(20)]
        ctx = _build_query_context(pages, max_chars=5000)
        assert len(ctx["context"]) <= 5500  # Allow small header overhead

    def test_empty_pages(self):
        ctx = _build_query_context([], max_chars=10000)
        assert ctx["context_pages"] == []

    def test_returns_context_pages_list(self):
        pages = [_page("concepts/a", "Content A"), _page("concepts/b", "Content B")]
        ctx = _build_query_context(pages, max_chars=10000)
        assert "concepts/a" in ctx["context_pages"]
        assert "concepts/b" in ctx["context_pages"]


# ── tests/test_v0917_stale_query.py — stale truth flagging at query time (Phase 4) ──


class TestFlagStaleResults:
    def test_flags_page_with_newer_source(self, tmp_project, create_wiki_page, create_raw_source):
        old_date = (date.today() - timedelta(days=30)).isoformat()
        create_wiki_page(
            page_id="concepts/stale-topic",
            title="Stale Topic",
            content="Old content.",
            source_ref="raw/articles/new-source.md",
            updated=old_date,
            wiki_dir=tmp_project / "wiki",
        )
        # Create a raw source that is "newer" (mtime is now)
        create_raw_source("raw/articles/new-source.md", "Updated content.", tmp_project)

        results = [
            {
                "id": "concepts/stale-topic",
                "sources": ["raw/articles/new-source.md"],
                "updated": old_date,
                "score": 5.0,
            }
        ]
        flagged = _flag_stale_results(results, project_root=tmp_project)
        assert flagged[0].get("stale") is True

    def test_does_not_flag_fresh_page(self, tmp_project, create_wiki_page, create_raw_source):
        import time  # fold-site local import: receiver's module-level `time` is datetime.time

        today = date.today().isoformat()
        create_wiki_page(
            page_id="concepts/fresh-topic",
            title="Fresh Topic",
            content="Fresh content.",
            source_ref="raw/articles/old-source.md",
            updated=today,
            wiki_dir=tmp_project / "wiki",
        )
        source_path = create_raw_source("raw/articles/old-source.md", "Source.", tmp_project)
        # Backdate the source file mtime to before the page updated date
        old_ts = time.time() - 86400 * 60
        os.utime(source_path, (old_ts, old_ts))

        results = [
            {
                "id": "concepts/fresh-topic",
                "sources": ["raw/articles/old-source.md"],
                "updated": today,
                "score": 5.0,
            }
        ]
        flagged = _flag_stale_results(results, project_root=tmp_project)
        assert flagged[0].get("stale") is False

    def test_handles_missing_source_gracefully(self):
        results = [
            {
                "id": "concepts/orphan",
                "sources": ["raw/articles/nonexistent.md"],
                "updated": date.today().isoformat(),
                "score": 5.0,
            }
        ]
        flagged = _flag_stale_results(results)
        assert flagged[0].get("stale") is False

    def test_handles_no_sources(self):
        results = [{"id": "concepts/no-src", "sources": [], "updated": "2026-04-12", "score": 1.0}]
        flagged = _flag_stale_results(results)
        assert flagged[0].get("stale") is False


# ── tests/test_v0916_task05.py — query/engine PageRank + query/citations parts ──


class TestPageRankEdgeFreeGraph:
    """_compute_pagerank_scores must return {} for graphs with no edges."""

    def test_edge_free_graph_returns_empty(self, tmp_wiki):
        """A wiki with pages but no wikilinks should get empty pagerank."""
        # Create two pages with no wikilinks between them
        for name in ("page-a", "page-b"):
            page = tmp_wiki / "concepts" / f"{name}.md"
            page.write_text(
                f'---\ntitle: "{name}"\nsource: []\ncreated: 2026-01-01\n'
                "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
                f"Content for {name}.\n",
                encoding="utf-8",
            )

        from kb.query.engine import _compute_pagerank_scores

        scores = _compute_pagerank_scores(tmp_wiki)
        assert scores == {}


class TestPageRankOSErrorCaught:
    """_compute_pagerank_scores must catch OSError from build_graph."""

    def test_os_error_returns_empty(self):
        from unittest.mock import patch

        from kb.query.engine import _compute_pagerank_scores

        with patch("kb.query.engine.build_graph", side_effect=OSError("disk error")):
            result = _compute_pagerank_scores()
            assert result == {}


class TestExtractCitationsTypeOverride:
    """extract_citations must override cite_type based on path prefix."""

    def test_source_keyword_with_raw_path(self):
        from kb.query.citations import extract_citations

        text = "According to [source: raw/papers/test.pdf] the model works."
        cites = extract_citations(text)
        assert len(cites) == 1
        assert cites[0]["type"] == "raw"  # overridden from "wiki"
        assert cites[0]["path"] == "raw/papers/test.pdf"

    def test_source_keyword_with_wiki_path(self):
        from kb.query.citations import extract_citations

        text = "According to [source: concepts/rag] the model works."
        cites = extract_citations(text)
        assert len(cites) == 1
        assert cites[0]["type"] == "wiki"  # stays as wiki


class TestExtractCitationsModuleLevel:
    """_CITATION_PATTERN should be a module-level compiled regex."""

    def test_pattern_is_module_level(self):
        from kb.query import citations

        assert hasattr(citations, "_CITATION_PATTERN")
        assert isinstance(citations._CITATION_PATTERN, re.Pattern)


# Cycle 80 freeze-and-fold — moved verbatim from tests/test_v0915_task04.py
# (Phase 3.96 Task 4 — Query & Citation fixes; BM25 tokenize classes folded to test_bm25.py).
class TestExtractCitationsNoDeadCode:
    def test_wikilink_in_citation_not_normalized(self):
        from kb.query.citations import extract_citations

        # The dead re.sub used to normalize [[wikilinks]] inside citation text.
        # After removal, wikilinks in surrounding text don't affect extraction.
        text = "According to [[concepts/rag]], this is true. [source: concepts/rag]"
        result = extract_citations(text)
        assert len(result) == 1
        assert result[0]["path"] == "concepts/rag"

    def test_plain_citation_extracted(self):
        from kb.query.citations import extract_citations

        text = "See [source: entities/gpt-4] for details."
        result = extract_citations(text)
        assert len(result) == 1
        assert result[0]["path"] == "entities/gpt-4"
        assert result[0]["type"] == "wiki"

    def test_ref_citation_extracted(self):
        from kb.query.citations import extract_citations

        text = "Documented in [ref: raw/papers/paper.md]."
        result = extract_citations(text)
        assert len(result) == 1
        assert result[0]["path"] == "raw/papers/paper.md"
        assert result[0]["type"] == "raw"


class TestCitationPathTraversal:
    def test_dot_slash_prefix_rejected(self):
        from kb.query.citations import extract_citations

        text = "[source: ./config]"
        result = extract_citations(text)
        assert result == []

    def test_dot_dot_rejected(self):
        from kb.query.citations import extract_citations

        text = "[source: ../secret]"
        result = extract_citations(text)
        assert result == []

    def test_leading_slash_rejected(self):
        from kb.query.citations import extract_citations

        text = "[source: /etc/passwd]"
        result = extract_citations(text)
        assert result == []

    def test_normal_path_accepted(self):
        from kb.query.citations import extract_citations

        text = "[source: concepts/rag]"
        result = extract_citations(text)
        assert len(result) == 1
        assert result[0]["path"] == "concepts/rag"


class TestQueryMaxTokensConfig:
    def test_query_max_tokens_defined(self):
        from kb.config import QUERY_MAX_TOKENS

        # 2048 * 1.3 — compensates for the Opus-4.7-generation tokenizer that
        # Sonnet 5 and Opus 4.8 use (~30% more tokens for the same text).
        assert QUERY_MAX_TOKENS == 2662

    def test_query_max_tokens_is_int(self):
        from kb.config import QUERY_MAX_TOKENS

        assert isinstance(QUERY_MAX_TOKENS, int)


class TestBuildQueryContextOversize:
    """Test that the top-ranked page is truncated rather than skipped when oversized."""

    def _make_page(self, page_id: str, content: str) -> dict:
        return {
            "id": page_id,
            "title": "Test Page",
            "type": "concept",
            "confidence": "stated",
            "content": content,
            "content_lower": content.lower(),
        }

    def test_top_page_truncated_not_skipped(self):
        from kb.query.engine import _build_query_context

        # Create a page with content that exceeds the budget
        large_content = "x" * 500
        page = self._make_page("concepts/big", large_content)
        result = _build_query_context([page], max_chars=200)
        # Should include the page (truncated), not return empty
        assert result["context_pages"] == ["concepts/big"]
        assert len(result["context"]) <= 200

    def test_top_page_context_within_budget(self):
        from kb.query.engine import _build_query_context

        large_content = "x" * 500
        page = self._make_page("concepts/big", large_content)
        result = _build_query_context([page], max_chars=200)
        assert len(result["context"]) <= 200

    def test_small_page_fits_normally(self):
        from kb.query.engine import _build_query_context

        page = self._make_page("concepts/small", "short content")
        result = _build_query_context([page], max_chars=10_000)
        assert result["context_pages"] == ["concepts/small"]
        assert "short content" in result["context"]

    def test_extremely_tiny_budget_returns_fallback(self):
        from kb.query.engine import _build_query_context

        # Budget smaller than even the page header — should return empty
        page = self._make_page("concepts/big", "x" * 500)
        result = _build_query_context([page], max_chars=5)
        # With a 5-char budget the header (~60 chars) won't fit — empty fallback
        assert result["context_pages"] == []


# -- Cycle 90 fold from test_v4_11_markdown.py --
# Tests for kb.query.formats.markdown adapter.

import yaml  # noqa: E402  — fold-site import (cycle 90)

from kb.query.formats.markdown import render_markdown  # noqa: E402  — fold-site (cycle 90)


@pytest.fixture
def sample_result():
    return {
        "question": "What is compile-not-retrieve?",
        "answer": "Compile-not-retrieve is a philosophy where...",
        "citations": [
            {"type": "wiki", "path": "concepts/compile-not-retrieve", "context": "..."},
            {"type": "wiki", "path": "entities/karpathy", "context": "..."},
        ],
        "source_pages": ["concepts/compile-not-retrieve", "entities/karpathy"],
        "context_pages": ["concepts/compile-not-retrieve"],
    }


def test_markdown_has_frontmatter(sample_result):
    out = render_markdown(sample_result)
    assert out.startswith("---\n")
    parts = out.split("---\n", 2)
    assert len(parts) >= 3
    fm = yaml.safe_load(parts[1])
    assert fm["type"] == "query_output"
    assert fm["format"] == "markdown"
    assert fm["query"] == "What is compile-not-retrieve?"
    assert "generated_at" in fm


def test_markdown_embeds_answer(sample_result):
    out = render_markdown(sample_result)
    assert "Compile-not-retrieve is a philosophy where..." in out


def test_markdown_renders_wiki_sources(sample_result):
    out = render_markdown(sample_result)
    assert "[[concepts/compile-not-retrieve]]" in out
    assert "[[entities/karpathy]]" in out


def test_markdown_h1_is_question(sample_result):
    out = render_markdown(sample_result)
    assert "# What is compile-not-retrieve?" in out


def test_markdown_no_citations(sample_result):
    sample_result["citations"] = []
    out = render_markdown(sample_result)
    assert "**Sources:**" not in out


def test_markdown_kb_version_from_module(sample_result):
    import kb

    out = render_markdown(sample_result)
    parts = out.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    assert fm["kb_version"] == kb.__version__


def test_markdown_handles_quotes_in_question(sample_result):
    sample_result["question"] = 'What about "quoted" text?'
    out = render_markdown(sample_result)
    parts = out.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    assert fm["query"] == 'What about "quoted" text?'


def test_markdown_rejects_oversize():
    from kb.config import MAX_OUTPUT_CHARS

    oversize = {
        "question": "q",
        "answer": "x" * (MAX_OUTPUT_CHARS + 1),
        "citations": [],
        "source_pages": [],
    }
    with pytest.raises(ValueError, match="MAX_OUTPUT_CHARS"):
        render_markdown(oversize)


# -- Cycle 90 fold from test_phase4_audit_query.py --
# Tests for query engine correctness — Phase 4 audit.
# Only deviations: fold-site import below; _build_query_context reuses the
# cycle-78 fold-site import above; helper renamed _make_page → _make_page_p4q
# (TestBuildQueryContextOversize in this receiver defines a _make_page method).

from kb.config import (  # noqa: E402  — fold-site import (cycle 90)
    CONTEXT_TIER1_BUDGET,
    QUERY_CONTEXT_MAX_CHARS,
    tier1_budget_for,
)


def _make_page_p4q(pid, ptype, size):
    """Create a minimal page dict for testing."""
    return {
        "id": pid,
        "type": ptype,
        "confidence": "stated",
        "title": pid,
        "content": "x" * size,
    }


def test_tier1_budget_prevents_summary_starvation():
    """A huge summary must not consume the full budget — entity pages must get context."""
    # Summary that exceeds CONTEXT_TIER1_BUDGET alone
    big_summary = _make_page_p4q("summaries/big", "summary", CONTEXT_TIER1_BUDGET + 5000)
    small_entity = _make_page_p4q("entities/foo", "entity", 100)
    pages = [big_summary, small_entity]

    result = _build_query_context(pages, max_chars=QUERY_CONTEXT_MAX_CHARS)

    assert "entities/foo" in result["context_pages"], (
        f"Entity page was starved by oversized summary. Got context_pages={result['context_pages']}"
    )


def test_tier1_budget_allows_multiple_small_summaries():
    """Multiple small summaries that fit within the summaries tier-1 budget must all be included.

    Cycle 15 AC2 — the summaries cap is ``tier1_budget_for("wiki_pages")`` (60% of
    ``CONTEXT_TIER1_BUDGET``), not the full tier-1 pool. Size the fixture to
    the scoped budget so the regression still exercises the multi-fit path.
    """
    summaries_cap = tier1_budget_for("wiki_pages")
    chunk = summaries_cap // 4
    summaries = [_make_page_p4q(f"summaries/s{i}", "summary", chunk - 200) for i in range(3)]
    result = _build_query_context(summaries, max_chars=QUERY_CONTEXT_MAX_CHARS)
    for s in summaries:
        assert s["id"] in result["context_pages"], f"Summary {s['id']} was unexpectedly excluded"


def test_raw_fallback_truncates_first_oversized_section(tmp_path, monkeypatch):
    """First raw-source section larger than the remaining budget must be truncated, not skipped.

    Cycle 3 H15: raw fallback is now gated on a SEMANTIC signal (context is
    empty OR only-summary), not a post-truncation char count. To keep the
    truncation-behavior regression, we force-trigger fallback by staging a
    summary-only wiki context.
    """
    import kb.query.engine as eng

    # A raw source whose content exceeds the entire query budget
    large_content = "y" * (QUERY_CONTEXT_MAX_CHARS + 1000)
    monkeypatch.setattr(
        eng,
        "search_raw_sources",
        lambda q, **kw: [{"id": "raw/articles/big.md", "content": large_content}],
    )
    # A tiny SUMMARY page so the cycle-3 semantic gate (only-summary context)
    # triggers raw fallback without requiring the pre-cycle-3 char-count path.
    tiny_summary = _make_page_p4q("summaries/tiny", "summary", 50)
    monkeypatch.setattr(eng, "search_pages", lambda q, wiki_dir=None, **kw: [tiny_summary])
    captured_prompts = []
    monkeypatch.setattr(
        eng, "call_llm", lambda prompt, **kw: captured_prompts.append(prompt) or "answer"
    )

    eng.query_wiki("test question", wiki_dir=tmp_path)

    # raw source content must appear in the prompt (truncated, not absent)
    assert captured_prompts, "call_llm was not called"
    assert "raw/articles/big.md" in captured_prompts[0], (
        "Oversized raw source was completely skipped instead of truncated"
    )


def test_raw_fallback_skips_when_non_summary_context_present(tmp_path, monkeypatch):
    """Cycle 3 H15: raw fallback must not fire when non-summary context pages exist.

    Prior test asserted that a SUMMARY page > half-budget suppresses
    fallback — that encoded the char-count gate which cycle 3 explicitly
    replaced because summaries LOSE detail (they are the case where raw
    fallback IS valuable). The new semantic gate triggers fallback on
    only-summary or empty contexts; a context containing entities /
    concepts / comparisons / synthesis pages is sufficient to skip.
    """
    import kb.query.engine as eng

    raw_called = []
    monkeypatch.setattr(eng, "search_raw_sources", lambda q, **kw: raw_called.append(True) or [])

    # Non-summary context page — cycle 3 semantic gate skips fallback.
    entity_page = _make_page_p4q("entities/large", "entity", 500)
    monkeypatch.setattr(eng, "search_pages", lambda q, wiki_dir=None, **kw: [entity_page])
    monkeypatch.setattr(eng, "call_llm", lambda prompt, **kw: "answer")

    eng.query_wiki("test question", wiki_dir=tmp_path)
    assert not raw_called, (
        "Cycle 3 H15: non-summary context should skip raw fallback under the "
        "semantic gate (only-summary or empty contexts trigger)."
    )


def test_bm25_limit_independent_of_vector_multiplier():
    """BM25 candidate count must not be coupled to VECTOR_SEARCH_LIMIT_MULTIPLIER."""
    from kb.config import BM25_SEARCH_LIMIT_MULTIPLIER, VECTOR_SEARCH_LIMIT_MULTIPLIER
    from kb.query.hybrid import hybrid_search

    bm25_calls = []
    vector_calls = []

    def fake_bm25(q, lim):
        bm25_calls.append(lim)
        return []

    def fake_vector(q, lim):
        vector_calls.append(lim)
        return []

    # hybrid_search(question, bm25_fn, vector_fn, expand_fn=None, *, limit=N)
    hybrid_search("test", fake_bm25, fake_vector, limit=5)

    assert bm25_calls, "BM25 was not called"
    assert vector_calls, "Vector search was not called"
    # BM25 limit must equal limit * BM25_SEARCH_LIMIT_MULTIPLIER
    assert bm25_calls[0] == 5 * BM25_SEARCH_LIMIT_MULTIPLIER, (
        f"BM25 limit was {bm25_calls[0]}, expected {5 * BM25_SEARCH_LIMIT_MULTIPLIER}"
    )
    # Vector search limit must equal limit * VECTOR_SEARCH_LIMIT_MULTIPLIER
    assert all(v == 5 * VECTOR_SEARCH_LIMIT_MULTIPLIER for v in vector_calls), (
        f"Vector limit mismatch: {vector_calls}"
    )
    # BM25 and vector limits must differ (since multipliers differ)
    if BM25_SEARCH_LIMIT_MULTIPLIER != VECTOR_SEARCH_LIMIT_MULTIPLIER:
        assert bm25_calls[0] != vector_calls[0], (
            "BM25 and vector limits are identical — decoupling had no effect"
        )


# -- Cycle 92 fold from test_v0915_task11.py (query engine + create_raw_source fixture subset) --


class TestComputePageRankScores:
    """11.7: _compute_pagerank_scores."""

    def test_non_empty_graph_returns_scores(self, tmp_wiki, create_wiki_page):
        from kb.query.engine import _compute_pagerank_scores

        create_wiki_page("concepts/a", wiki_dir=tmp_wiki, content="See [[concepts/b]].")
        create_wiki_page("concepts/b", wiki_dir=tmp_wiki, content="See [[concepts/a]].")
        scores = _compute_pagerank_scores(tmp_wiki)
        assert len(scores) > 0
        assert all(0.0 <= v <= 1.0 for v in scores.values())

    def test_empty_wiki_returns_empty(self, tmp_wiki):
        from kb.query.engine import _compute_pagerank_scores

        scores = _compute_pagerank_scores(tmp_wiki)
        assert scores == {}

    def test_single_page_scores(self, tmp_wiki, create_wiki_page):
        from kb.query.engine import _compute_pagerank_scores

        # Edge-free graph (single page, no wikilinks) returns {} — PageRank blending skipped
        create_wiki_page("concepts/single", wiki_dir=tmp_wiki, content="No links.")
        scores = _compute_pagerank_scores(tmp_wiki)
        assert scores == {}

    def test_hub_page_has_higher_score(self, tmp_wiki, create_wiki_page):
        from kb.query.engine import _compute_pagerank_scores

        # Create a hub page that many pages link to
        create_wiki_page("concepts/hub", wiki_dir=tmp_wiki, content="Hub page.")
        for i in range(3):
            create_wiki_page(
                f"concepts/spoke{i}",
                wiki_dir=tmp_wiki,
                content="Links to [[concepts/hub]].",
            )
        scores = _compute_pagerank_scores(tmp_wiki)
        # Hub should have higher score (more inbound links)
        assert scores["concepts/hub"] > 0.0


class TestBuildQueryContext:
    """11.8: _build_query_context truncation."""

    def test_oversize_page_handled(self):
        from kb.query.engine import _build_query_context

        big_page = {
            "id": "concepts/big",
            "title": "Big",
            "type": "concept",
            "confidence": "stated",
            "content": "x" * 100_000,
        }
        small_page = {
            "id": "concepts/small",
            "title": "Small",
            "type": "concept",
            "confidence": "stated",
            "content": "Small content.",
        }
        result = _build_query_context([big_page, small_page], max_chars=1000)
        assert result["context_pages"]  # at least one page included

    def test_empty_pages_returns_empty(self):
        from kb.query.engine import _build_query_context

        result = _build_query_context([], max_chars=1000)
        assert result["context_pages"] == []

    def test_context_respects_max_chars(self):
        from kb.query.engine import _build_query_context

        pages = [
            {
                "id": "concepts/a",
                "title": "A",
                "type": "concept",
                "confidence": "stated",
                "content": "x" * 500,
            },
            {
                "id": "concepts/b",
                "title": "B",
                "type": "concept",
                "confidence": "stated",
                "content": "y" * 500,
            },
        ]
        result = _build_query_context(pages, max_chars=700)
        # context_pages is a list of page IDs (strings)
        # Both 500-char pages shouldn't fit in 700 chars
        assert len(result["context_pages"]) <= 1

    def test_single_page_fits_exactly(self):
        from kb.query.engine import _build_query_context

        page = {
            "id": "concepts/test",
            "title": "Test",
            "type": "concept",
            "confidence": "stated",
            "content": "Test content.",
        }
        result = _build_query_context([page], max_chars=10000)
        assert len(result["context_pages"]) == 1


class TestCreateRawSourceValidation:
    """11.11: create_raw_source fixture path validation."""

    def test_raw_source_with_valid_prefix(self, create_raw_source):
        path = create_raw_source("raw/articles/test.md", "Content")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "Content"

    def test_raw_source_invalid_prefix_raises(self, create_raw_source):
        with pytest.raises(AssertionError, match="source_ref must start with 'raw/'"):
            create_raw_source("wiki/articles/test.md", "Content")

    def test_raw_source_videos_subdirectory(self, create_raw_source):
        path = create_raw_source("raw/videos/video.txt", "Video")
        assert path.exists()

    def test_raw_source_papers_subdirectory(self, create_raw_source):
        path = create_raw_source("raw/papers/paper.pdf", "Paper")
        assert path.exists()
