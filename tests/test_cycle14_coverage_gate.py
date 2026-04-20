"""Cycle 14 TASK 5 — coverage-confidence refusal gate in query_wiki.

Covers AC5, AC6. Threat T5 (advisory no-echo of user question verbatim).
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from kb import config as kb_config
from kb.query import engine as query_engine


def _make_page(wiki: Path, subdir: str, pid: str, title: str, body: str) -> Path:
    page_dir = wiki / subdir
    page_dir.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(content=body)
    post.metadata["title"] = title
    post.metadata["source"] = f"raw/articles/{pid}.md"
    post.metadata["created"] = "2026-04-20"
    post.metadata["updated"] = "2026-04-20"
    post.metadata["type"] = "concept"
    post.metadata["confidence"] = "stated"
    path = page_dir / f"{pid}.md"
    path.write_text(frontmatter.dumps(post, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def tiny_wiki(tmp_path):
    wiki = tmp_path / "wiki"
    for sd in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki / sd).mkdir(parents=True)
    _make_page(wiki, "concepts", "cap-theorem", "CAP Theorem", "consistency availability partition")
    _make_page(wiki, "concepts", "consensus", "Consensus", "distributed agreement protocol paxos")
    return wiki


class TestCoverageAboveThreshold:
    """AC6(a) — coverage above threshold → no low_confidence, no advisory,
    synthesizer called normally."""

    def test_synthesizer_called_with_sufficient_coverage(self, tiny_wiki, monkeypatch):
        # Simulate high-coverage vector hits by patching search_pages to
        # return results AND populate telemetry with high cosine scores.
        def fake_search_pages(question, wiki_dir=None, max_results=10, *, search_telemetry=None):
            pages = [
                {
                    "id": "concepts/cap-theorem",
                    "path": str(tiny_wiki / "concepts/cap-theorem.md"),
                    "title": "CAP Theorem",
                    "type": "concept",
                    "confidence": "stated",
                    "sources": ["raw/articles/cap-theorem.md"],
                    "created": "2026-04-20",
                    "updated": "2026-04-20",
                    "content": "consistency availability partition",
                    "score": 0.9,
                }
            ]
            if search_telemetry is not None:
                search_telemetry["vector_attempts"] = 1
                search_telemetry["vector_hits"] = 1
                search_telemetry["vector_scores_by_id"] = {"concepts/cap-theorem": 0.85}
            return pages

        monkeypatch.setattr(query_engine, "search_pages", fake_search_pages)
        monkeypatch.setattr(
            query_engine,
            "call_llm",
            lambda *args, **kwargs: "Synthesized answer about CAP.",
        )

        result = query_engine.query_wiki("what is cap theorem", wiki_dir=tiny_wiki)

        assert result["answer"] == "Synthesized answer about CAP."
        assert result["coverage_confidence"] == pytest.approx(0.85, abs=0.01)
        assert "low_confidence" not in result
        assert "advisory" not in result


class TestCoverageBelowThreshold:
    """AC6(b) — coverage below threshold → low_confidence + advisory;
    synthesizer NOT called."""

    def test_gate_triggers_refusal(self, tiny_wiki, monkeypatch):
        call_llm_spy = {"tiers": []}

        def fake_search_pages(question, wiki_dir=None, max_results=10, *, search_telemetry=None):
            pages = [
                {
                    "id": "concepts/consensus",
                    "path": str(tiny_wiki / "concepts/consensus.md"),
                    "title": "Consensus",
                    "type": "concept",
                    "confidence": "stated",
                    "sources": ["raw/articles/consensus.md"],
                    "created": "2026-04-20",
                    "updated": "2026-04-20",
                    "content": "distributed agreement paxos",
                    "score": 0.3,
                }
            ]
            if search_telemetry is not None:
                search_telemetry["vector_attempts"] = 1
                search_telemetry["vector_hits"] = 1
                # Below 0.45 threshold.
                search_telemetry["vector_scores_by_id"] = {"concepts/consensus": 0.10}
            return pages

        def fake_call_llm(prompt, *args, tier="orchestrate", **kwargs):
            # Cycle 16 AC7-AC9 added a scan-tier rephrasings call on the
            # refusal path. The AC5 invariant is now "synthesis (orchestrate
            # tier) MUST NOT fire on refusal", NOT "no call_llm ever".
            call_llm_spy["tiers"].append(tier)
            # Return empty so rephrasings parses to [].
            return ""

        monkeypatch.setattr(query_engine, "search_pages", fake_search_pages)
        monkeypatch.setattr(query_engine, "call_llm", fake_call_llm)

        result = query_engine.query_wiki("something tangential", wiki_dir=tiny_wiki)

        assert result["coverage_confidence"] == pytest.approx(0.10, abs=0.01)
        assert result["low_confidence"] is True
        assert "advisory" in result
        # AC5 invariant: orchestrate (synthesis) tier MUST NOT be invoked.
        assert "orchestrate" not in call_llm_spy["tiers"], (
            f"orchestrate synthesis must NOT fire on refusal (AC5 gate); "
            f"got tiers={call_llm_spy['tiers']}"
        )
        assert result["answer"] == result["advisory"]


class TestBM25OnlyQueryPassesThrough:
    """AC6(c) — no vector hits (BM25-only) → no coverage_confidence value
    AND no low_confidence key (gate inactive)."""

    def test_bm25_only_no_gate(self, tiny_wiki, monkeypatch):
        def fake_search_pages(question, wiki_dir=None, max_results=10, *, search_telemetry=None):
            pages = [
                {
                    "id": "concepts/cap-theorem",
                    "path": str(tiny_wiki / "concepts/cap-theorem.md"),
                    "title": "CAP Theorem",
                    "type": "concept",
                    "confidence": "stated",
                    "sources": ["raw/articles/cap-theorem.md"],
                    "created": "2026-04-20",
                    "updated": "2026-04-20",
                    "content": "consistency availability partition",
                    "score": 0.5,
                }
            ]
            if search_telemetry is not None:
                search_telemetry["vector_attempts"] = 0
                search_telemetry["vector_hits"] = 0
                # No vector_scores_by_id key at all — pure BM25.
            return pages

        monkeypatch.setattr(query_engine, "search_pages", fake_search_pages)
        monkeypatch.setattr(query_engine, "call_llm", lambda *args, **kwargs: "BM25-only answer")

        result = query_engine.query_wiki("cap theorem", wiki_dir=tiny_wiki)

        assert result["coverage_confidence"] is None
        assert "low_confidence" not in result
        assert "advisory" not in result
        assert result["answer"] == "BM25-only answer"


class TestAdvisoryNoQuestionEcho:
    """Threat T5 — advisory MUST NOT include user question verbatim.

    This defends against XSS (if later rendered in HTML) and prompt-
    injection bleed (if result gets pipelined into another LLM call).
    """

    def test_advisory_excludes_malicious_question(self, tiny_wiki, monkeypatch):
        def fake_search_pages(question, wiki_dir=None, max_results=10, *, search_telemetry=None):
            pages = [
                {
                    "id": "concepts/consensus",
                    "path": str(tiny_wiki / "concepts/consensus.md"),
                    "title": "Consensus",
                    "type": "concept",
                    "confidence": "stated",
                    "sources": ["raw/articles/consensus.md"],
                    "created": "2026-04-20",
                    "updated": "2026-04-20",
                    "content": "distributed agreement paxos",
                    "score": 0.3,
                }
            ]
            if search_telemetry is not None:
                search_telemetry["vector_scores_by_id"] = {"concepts/consensus": 0.10}
            return pages

        monkeypatch.setattr(query_engine, "search_pages", fake_search_pages)
        monkeypatch.setattr(query_engine, "call_llm", lambda *a, **k: "")

        malicious = "<script>alert('xss')</script>"
        result = query_engine.query_wiki(malicious, wiki_dir=tiny_wiki)

        assert "low_confidence" in result
        assert "<script>" not in result["advisory"]
        assert "alert" not in result["advisory"]
        assert malicious not in result["advisory"]


class TestEmptyMatchingPagesIncludesCoverage:
    """AC5 — even the no-match return path includes coverage_confidence."""

    def test_no_pages_returns_coverage_none(self, tiny_wiki, monkeypatch):
        def fake_search_pages(question, wiki_dir=None, max_results=10, *, search_telemetry=None):
            return []

        monkeypatch.setattr(query_engine, "search_pages", fake_search_pages)
        result = query_engine.query_wiki("irrelevant", wiki_dir=tiny_wiki)
        assert result["coverage_confidence"] is None
        assert "low_confidence" not in result


class TestBackwardCompatibleReturnShape:
    """Pre-cycle-14 callers receive the same keys PLUS new coverage_confidence."""

    def test_all_legacy_keys_present(self, tiny_wiki, monkeypatch):
        def fake_search_pages(question, wiki_dir=None, max_results=10, *, search_telemetry=None):
            pages = [
                {
                    "id": "concepts/cap-theorem",
                    "path": str(tiny_wiki / "concepts/cap-theorem.md"),
                    "title": "CAP Theorem",
                    "type": "concept",
                    "confidence": "stated",
                    "sources": ["raw/articles/cap-theorem.md"],
                    "created": "2026-04-20",
                    "updated": "2026-04-20",
                    "content": "consistency availability partition",
                    "score": 0.9,
                }
            ]
            if search_telemetry is not None:
                search_telemetry["vector_scores_by_id"] = {"concepts/cap-theorem": 0.85}
            return pages

        monkeypatch.setattr(query_engine, "search_pages", fake_search_pages)
        monkeypatch.setattr(query_engine, "call_llm", lambda *a, **k: "answer")

        result = query_engine.query_wiki("cap", wiki_dir=tiny_wiki)
        expected_keys = {
            "question",
            "answer",
            "citations",
            "source_pages",
            "context_pages",
            "stale_citations",
            "search_mode",
            "coverage_confidence",
        }
        assert expected_keys <= set(result.keys())


class TestThresholdConfigurable:
    """AC4 integration — threshold comes from config, can be tuned."""

    def test_threshold_from_config(self):
        assert query_engine.QUERY_COVERAGE_CONFIDENCE_THRESHOLD == 0.45
        assert kb_config.QUERY_COVERAGE_CONFIDENCE_THRESHOLD == 0.45
