"""Cycle 14 TASK 6 — status ranking boost in query/engine.py.

Covers AC23, AC24. Threat T9 (attacker-controlled status frontmatter gated
by validate_frontmatter).
"""

from __future__ import annotations

import pytest

from kb.config import STATUS_RANKING_BOOST
from kb.query.engine import _apply_status_boost


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
        "status": "",
        "score": score,
    }
    page.update(extras)
    return page


class TestBoostAppliesToMature:
    """AC24(a) — status: mature gets boosted."""

    def test_mature_page_gets_boost(self):
        page = _base_page("cap-theorem", score=0.5, status="mature")
        boosted = _apply_status_boost(page)
        expected = 0.5 * (1 + STATUS_RANKING_BOOST)
        assert boosted["score"] == pytest.approx(expected)
        # Original not mutated
        assert page["score"] == 0.5

    def test_evergreen_page_gets_boost(self):
        page = _base_page("rag", score=0.4, status="evergreen")
        boosted = _apply_status_boost(page)
        expected = 0.4 * (1 + STATUS_RANKING_BOOST)
        assert boosted["score"] == pytest.approx(expected)

    def test_two_pages_boost_reorders_ties(self):
        a = _base_page("a", score=0.50, status="")
        b = _base_page("b", score=0.50, status="mature")
        ba = _apply_status_boost(a)
        bb = _apply_status_boost(b)
        assert bb["score"] > ba["score"]


class TestBoostSkipsOtherStatuses:
    """AC24(b, c, d) — seed / developing / missing / invalid → no boost."""

    def test_seed_no_boost(self):
        page = _base_page("seed-page", score=0.5, status="seed")
        boosted = _apply_status_boost(page)
        assert boosted["score"] == 0.5

    def test_developing_no_boost(self):
        page = _base_page("dev-page", score=0.5, status="developing")
        boosted = _apply_status_boost(page)
        assert boosted["score"] == 0.5

    def test_missing_status_no_boost(self):
        page = _base_page("missing", score=0.5)
        assert page["status"] == ""
        boosted = _apply_status_boost(page)
        assert boosted["score"] == 0.5

    def test_invalid_status_no_boost(self):
        """AC24(c) — invalid status (not in PAGE_STATUSES) gets NO boost."""
        page = _base_page("bogus", score=0.5, status="INVALID_VALUE")
        boosted = _apply_status_boost(page)
        assert boosted["score"] == 0.5


class TestFrontmatterValidationGate:
    """AC24(d) / Threat T9 — validate_frontmatter gate."""

    def test_mature_with_invalid_confidence_no_boost(self):
        """status=mature + invalid confidence → validate_frontmatter fails
        → no boost (attacker-planted frontmatter attack mitigation)."""
        page = _base_page("bad-conf", score=0.5, status="mature", confidence="INVALID_CONF")
        boosted = _apply_status_boost(page)
        assert boosted["score"] == 0.5

    def test_mature_with_invalid_type_no_boost(self):
        page = _base_page("bad-type", score=0.5, status="mature", type="bogus")
        boosted = _apply_status_boost(page)
        assert boosted["score"] == 0.5

    def test_mature_with_missing_sources_no_boost(self):
        """Empty sources list → validate_frontmatter flags empty source list → no boost."""
        page = _base_page("no-src", score=0.5, status="mature", sources=[])
        boosted = _apply_status_boost(page)
        assert boosted["score"] == 0.5

    def test_mature_valid_full_metadata_boosts(self):
        """Sanity — all required fields present and valid → boost."""
        page = _base_page("full-valid", score=0.6, status="mature")
        boosted = _apply_status_boost(page)
        assert boosted["score"] > 0.6


class TestDeterminism:
    """AC24(e) — same input produces same order across runs."""

    def test_boost_is_deterministic(self):
        page = _base_page("x", score=0.5, status="mature")
        boosted1 = _apply_status_boost(page)
        boosted2 = _apply_status_boost(page)
        boosted3 = _apply_status_boost(page)
        assert boosted1["score"] == boosted2["score"] == boosted3["score"]


class TestNoMutation:
    """Input page dict should not be mutated; helper returns a new dict."""

    def test_input_dict_not_mutated(self):
        page = _base_page("nomut", score=0.5, status="mature")
        _apply_status_boost(page)
        assert page["score"] == 0.5  # unchanged
