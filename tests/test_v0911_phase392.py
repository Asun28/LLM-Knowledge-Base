"""Tests for Phase 3.92 backlog fixes (v0.9.11)."""

from pathlib import Path


# ── Task 2: Review history 10k cap ──────────────────────────────


class TestReviewHistoryCap:
    """review/refiner.py must cap review history at MAX_REVIEW_HISTORY_ENTRIES."""

    def test_review_history_capped_at_limit(self, tmp_path):
        """refine_page caps history at MAX_REVIEW_HISTORY_ENTRIES entries."""
        from kb.config import MAX_REVIEW_HISTORY_ENTRIES
        from kb.review.refiner import load_review_history, save_review_history

        history_path = tmp_path / "review_history.json"

        # Pre-populate with MAX entries
        entries = [
            {"timestamp": f"2026-01-01T00:00:{i % 60:02d}", "page_id": f"p{i}", "status": "applied"}
            for i in range(MAX_REVIEW_HISTORY_ENTRIES)
        ]
        save_review_history(entries, history_path)

        # Create a wiki page to refine
        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        page = wiki_dir / "concepts" / "test.md"
        page.write_text(
            "---\ntitle: Test\nsource:\n  - raw/articles/a.md\n"
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\nBody.",
            encoding="utf-8",
        )

        from kb.review.refiner import refine_page

        refine_page(
            "concepts/test",
            "Updated body.",
            revision_notes="test cap",
            wiki_dir=wiki_dir,
            history_path=history_path,
        )

        history = load_review_history(history_path)
        assert len(history) == MAX_REVIEW_HISTORY_ENTRIES, (
            f"Expected {MAX_REVIEW_HISTORY_ENTRIES} entries, got {len(history)}"
        )
