"""Cycle 15 AC3/AC22 — authored_by ranking boost in query/engine.py.

Mirrors the cycle-14 status-boost test structure (`test_cycle14_status_boost.py`).
Covers the T7 validate_frontmatter gate — attacker-planted invalid
frontmatter must NOT win the boost.
"""

from __future__ import annotations

import pytest

from kb.config import AUTHORED_BY_BOOST
from kb.query.engine import _apply_authored_by_boost


def _base_page(pid: str, score: float, **extras) -> dict:
    """Minimal page dict shape matching load_all_pages output."""
    page = {
        "id": pid,
        "path": f"/wiki/concepts/{pid}.md",
        "title": f"Page {pid}",
        "type": "concept",
        "confidence": "stated",
        "sources": [f"raw/articles/{pid}.md"],
        "created": "2026-04-20",
        "updated": "2026-04-20",
        "content": "body",
        "authored_by": "",
        "score": score,
    }
    page.update(extras)
    return page


class TestBoostAppliesToHumanHybrid:
    """AC22 — authored_by in {human, hybrid} gets boosted when frontmatter valid."""

    def test_human_page_gets_boost(self):
        page = _base_page("docs", score=0.5, authored_by="human")
        boosted = _apply_authored_by_boost(page)
        expected = 0.5 * (1 + AUTHORED_BY_BOOST)
        assert boosted["score"] == pytest.approx(expected)
        # Non-mutating
        assert page["score"] == 0.5

    def test_hybrid_page_gets_boost(self):
        page = _base_page("collab", score=0.4, authored_by="hybrid")
        boosted = _apply_authored_by_boost(page)
        expected = 0.4 * (1 + AUTHORED_BY_BOOST)
        assert boosted["score"] == pytest.approx(expected)

    def test_boost_reorders_ties(self):
        a = _base_page("a", score=0.50, authored_by="llm")
        b = _base_page("b", score=0.50, authored_by="human")
        ba = _apply_authored_by_boost(a)
        bb = _apply_authored_by_boost(b)
        assert bb["score"] > ba["score"]


class TestBoostSkipsNonTrusted:
    """AC22 — llm / absent / invalid authored_by → no boost, no raise."""

    def test_llm_page_no_boost(self):
        page = _base_page("rag-synthesis", score=0.5, authored_by="llm")
        boosted = _apply_authored_by_boost(page)
        assert boosted["score"] == 0.5

    def test_absent_authored_by_no_boost(self):
        page = _base_page("plain", score=0.5)  # authored_by defaults to ""
        boosted = _apply_authored_by_boost(page)
        assert boosted["score"] == 0.5

    def test_invalid_authored_by_value_no_boost_no_raise(self):
        # `robot` is not in AUTHORED_BY_VALUES → no boost, no exception.
        page = _base_page("bad", score=0.5, authored_by="robot")
        boosted = _apply_authored_by_boost(page)
        assert boosted["score"] == 0.5


class TestValidateFrontmatterGateT7:
    """AC22 T7 — invalid frontmatter must not win boost (attacker-planted)."""

    def test_human_with_missing_source_no_boost(self):
        """T7 — authored_by: human + empty sources list = invalid; no boost."""
        page = _base_page("poisoned", score=0.5, authored_by="human")
        page["sources"] = []  # empty sources → validate_frontmatter errors
        boosted = _apply_authored_by_boost(page)
        assert boosted["score"] == 0.5

    def test_human_with_invalid_type_no_boost(self):
        """T7 — authored_by: human + bogus type field = invalid; no boost."""
        page = _base_page("poisoned2", score=0.5, authored_by="human", type="nonsense")
        boosted = _apply_authored_by_boost(page)
        assert boosted["score"] == 0.5

    def test_hybrid_with_invalid_confidence_no_boost(self):
        """T7 — authored_by: hybrid + bogus confidence = invalid; no boost."""
        page = _base_page("poisoned3", score=0.5, authored_by="hybrid", confidence="forged")
        boosted = _apply_authored_by_boost(page)
        assert boosted["score"] == 0.5


class TestNonMutating:
    """AC3 — helper never mutates input (copy-semantics)."""

    def test_returns_new_dict_on_boost(self):
        page = _base_page("x", score=0.5, authored_by="human")
        boosted = _apply_authored_by_boost(page)
        assert boosted is not page
        assert page["score"] == 0.5

    def test_returns_same_dict_on_no_boost(self):
        # When no boost applies, the helper is free to return the same dict
        # (no allocation). Both behaviours are acceptable; just verify score.
        page = _base_page("y", score=0.5, authored_by="llm")
        boosted = _apply_authored_by_boost(page)
        assert boosted["score"] == 0.5
