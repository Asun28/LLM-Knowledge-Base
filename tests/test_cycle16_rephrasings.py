"""Cycle 16 AC7-AC9 — _suggest_rephrasings for low-coverage advisory.

Behavioural regressions on the new helper and its wiring into the refusal
branch. Direct import + monkeypatch of call_llm — no inspect.getsource.
"""

import logging

import pytest

from kb.query import engine, rewriter
from kb.utils.llm import LLMError


class TestSuggestRephrasingsHelper:
    def test_empty_context_returns_empty(self, monkeypatch) -> None:
        """AC7 — no context pages → skip LLM call and return []."""
        called = {"n": 0}

        def _spy(*a, **k):
            called["n"] += 1
            return "should-not-happen"

        monkeypatch.setattr(rewriter, "call_llm", _spy)
        assert engine._suggest_rephrasings("test q", []) == []
        assert called["n"] == 0

    def test_llm_error_returns_empty(self, monkeypatch) -> None:
        """AC7/T3 — LLMError swallowed, return []."""

        def _raise_llm(*a, **k):
            raise LLMError("rate limit")

        monkeypatch.setattr(rewriter, "call_llm", _raise_llm)
        result = engine._suggest_rephrasings("q", [{"title": "x"}])
        assert result == []

    def test_os_error_returns_empty(self, monkeypatch) -> None:
        """AC7 — OSError swallowed (network) — return []."""

        def _raise_os(*a, **k):
            raise OSError("network down")

        monkeypatch.setattr(rewriter, "call_llm", _raise_os)
        result = engine._suggest_rephrasings("q", [{"title": "x"}])
        assert result == []

    def test_generic_exception_propagates(self, monkeypatch) -> None:
        """Q5/C5 — narrow except; bugs like ValueError must surface, not swallow."""

        def _raise_val(*a, **k):
            raise ValueError("programmer bug")

        monkeypatch.setattr(rewriter, "call_llm", _raise_val)
        with pytest.raises(ValueError):
            engine._suggest_rephrasings("q", [{"title": "x"}])

    def test_echo_case_insensitive_filtered(self, monkeypatch) -> None:
        """AC9 — case-shifted echo filtered."""
        monkeypatch.setattr(
            rewriter,
            "call_llm",
            lambda *a, **k: "What Is X\nother phrasing",
        )
        result = engine._suggest_rephrasings("what is x", [{"title": "X"}])
        assert "other phrasing" in result
        assert all("what is x" != r.lower() for r in result)

    def test_echo_punctuation_shifted_filtered(self, monkeypatch) -> None:
        """Q6/C5 — question with trailing '?' filters out candidate without '?'."""
        monkeypatch.setattr(
            rewriter,
            "call_llm",
            lambda *a, **k: "What is attention\nDefine attention",
        )
        result = engine._suggest_rephrasings("What is attention?", [{"title": "Attention"}])
        assert "Define attention" in result
        # The punctuation-stripped echo "What is attention" must be gone.
        assert "What is attention" not in result

    def test_echo_whitespace_normalised_filtered(self, monkeypatch) -> None:
        """Q6 — weird whitespace around LLM candidate still matches question."""
        monkeypatch.setattr(
            rewriter,
            "call_llm",
            lambda *a, **k: " a  b \nreal alt",
        )
        result = engine._suggest_rephrasings("a b", [{"title": "T"}])
        assert result == ["real alt"]

    def test_bullet_prefix_stripped(self, monkeypatch) -> None:
        """Q5/C5 — bullet/number prefixes removed so clean text emerges."""
        monkeypatch.setattr(
            rewriter,
            "call_llm",
            lambda *a, **k: "1. alpha\n2) beta\n- gamma\n* delta\n• epsilon",
        )
        result = engine._suggest_rephrasings(
            "original question", [{"title": "T"}], max_suggestions=5
        )
        assert result == ["alpha", "beta", "gamma", "delta", "epsilon"]

    def test_long_line_dropped(self, monkeypatch) -> None:
        """Q5/C5 — lines > 300 chars dropped as garbage."""
        long_line = "foo " + ("x" * 400)
        monkeypatch.setattr(
            rewriter,
            "call_llm",
            lambda *a, **k: f"{long_line}\ngood alt",
        )
        result = engine._suggest_rephrasings("q", [{"title": "T"}])
        assert result == ["good alt"]

    def test_cap_applied(self, monkeypatch) -> None:
        """AC7 — output capped at max_suggestions even when LLM over-supplies."""
        monkeypatch.setattr(
            rewriter,
            "call_llm",
            lambda *a, **k: "a\nb\nc\nd\ne\nf",
        )
        result = engine._suggest_rephrasings("q", [{"title": "T"}], max_suggestions=3)
        assert len(result) == 3

    def test_hostile_title_truncated(self, monkeypatch) -> None:
        """T4 — titles truncated to 200 chars before prompt assembly."""
        captured = {"prompt": ""}

        def _capture(prompt, **k):
            captured["prompt"] = prompt
            return ""

        monkeypatch.setattr(rewriter, "call_llm", _capture)
        hostile_title = "x" * 2000
        engine._suggest_rephrasings("q", [{"title": hostile_title}])
        # The full 2000-char title must NOT appear in the prompt.
        assert hostile_title not in captured["prompt"]
        # The 200-char truncation must be present.
        assert "x" * 200 in captured["prompt"]

    def test_prompt_fences_titles(self, monkeypatch) -> None:
        """Plan-gate amendment T4 — titles wrapped in <page_title>…</page_title> fences."""
        captured = {"prompt": ""}

        def _capture(prompt, **k):
            captured["prompt"] = prompt
            return ""

        monkeypatch.setattr(rewriter, "call_llm", _capture)
        engine._suggest_rephrasings("q", [{"title": "Foo"}, {"title": "Bar"}])
        assert "<page_title>Foo</page_title>" in captured["prompt"]
        assert "<page_title>Bar</page_title>" in captured["prompt"]

    def test_prompt_logs_truncated_question_only(
        self, monkeypatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """T11 — prompt log MUST NOT contain the full question body."""
        monkeypatch.setattr(rewriter, "call_llm", lambda *a, **k: "")
        long_q = "secret-topic-" + ("z" * 200)
        caplog.set_level(logging.INFO, logger="kb.query.engine")
        engine._suggest_rephrasings(long_q, [{"title": "T"}])
        # Ensure no log message contains the full > 80 char question.
        for rec in caplog.records:
            assert long_q not in rec.getMessage()


class TestLowCoverageWiring:
    """AC8 — rephrasings key surfaced only on refusal path.

    R1 Sonnet Major 2: the prior test asserted only `callable(_suggest_rephrasings)`
    which would pass even with the wiring reverted (cycle-11 L2 vacuous test
    pattern). These tests drive the actual low-confidence refusal branch in
    `query_wiki` via a minimal search_pages + telemetry patch and assert the
    `rephrasings` key appears in the returned result_dict.
    """

    def _fake_search_with_low_coverage(self, tmp_wiki) -> None:
        """Helper contract — return fake search_pages that seeds
        coverage_confidence < QUERY_COVERAGE_CONFIDENCE_THRESHOLD via
        the telemetry side-channel.
        """

    def test_refusal_path_includes_rephrasings_key(self, tmp_wiki, monkeypatch) -> None:
        """AC8 — low_confidence path MUST set result_dict['rephrasings']."""

        def fake_search_pages(question, wiki_dir=None, max_results=10, *, search_telemetry=None):
            pages = [
                {
                    "id": "concepts/x",
                    "path": str(tmp_wiki / "concepts/x.md"),
                    "title": "x",
                    "type": "concept",
                    "confidence": "stated",
                    "sources": ["raw/articles/x.md"],
                    "created": "2026-04-20",
                    "updated": "2026-04-20",
                    "content": "body",
                    "score": 0.2,
                }
            ]
            if search_telemetry is not None:
                search_telemetry["vector_attempts"] = 1
                search_telemetry["vector_hits"] = 1
                search_telemetry["vector_scores_by_id"] = {"concepts/x": 0.10}
            return pages

        def fake_suggest(question, context_pages, **kw):
            return ["alt one", "alt two"]

        monkeypatch.setattr(engine, "search_pages", fake_search_pages)
        monkeypatch.setattr(engine, "_suggest_rephrasings", fake_suggest)
        result = engine.query_wiki("what is X?", wiki_dir=tmp_wiki)
        assert result.get("low_confidence") is True
        # The core AC8 invariant: the key is present.
        assert "rephrasings" in result
        assert result["rephrasings"] == ["alt one", "alt two"]

    def test_non_refusal_path_omits_rephrasings_key(self, tmp_wiki, monkeypatch) -> None:
        """AC8 — rephrasings key absent on non-refusal (happy) path."""

        def fake_search_pages(question, wiki_dir=None, max_results=10, *, search_telemetry=None):
            # BM25-only path — no vector hits → coverage_confidence is None
            # → low_confidence branch never fires.
            return [
                {
                    "id": "concepts/y",
                    "path": str(tmp_wiki / "concepts/y.md"),
                    "title": "y",
                    "type": "concept",
                    "confidence": "stated",
                    "sources": ["raw/articles/y.md"],
                    "created": "2026-04-20",
                    "updated": "2026-04-20",
                    "content": "body",
                    "score": 0.9,
                }
            ]

        spy_called = {"n": 0}

        def never_call(*a, **k):
            spy_called["n"] += 1
            return []

        def fake_call_llm(*a, tier="orchestrate", **k):
            # Return a minimal synthesised answer for the happy path.
            return "synthesized answer"

        monkeypatch.setattr(engine, "search_pages", fake_search_pages)
        monkeypatch.setattr(engine, "_suggest_rephrasings", never_call)
        monkeypatch.setattr(engine, "call_llm", fake_call_llm)
        result = engine.query_wiki("what is Y?", wiki_dir=tmp_wiki)
        assert result.get("low_confidence") is not True
        assert "rephrasings" not in result
        assert spy_called["n"] == 0  # helper never invoked on happy path

    def test_helper_is_exported_from_module(self) -> None:
        """AC7 — _suggest_rephrasings is importable from kb.query.engine."""
        from kb.query.engine import _suggest_rephrasings

        assert callable(_suggest_rephrasings)

    def test_normalise_for_echo_is_exported(self) -> None:
        """Q6/C5 — echo normaliser is a module-level function."""
        from kb.query.engine import _normalise_for_echo

        assert _normalise_for_echo("Hello, World!") == "hello world"
        assert _normalise_for_echo("  foo\tbar  ") == "foo bar"
        assert _normalise_for_echo("X?") == _normalise_for_echo("X!")
