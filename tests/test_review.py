"""Tests for the review module (context + refiner)."""

import threading
from datetime import date
from pathlib import Path

from kb.review.context import (
    build_review_checklist,
    build_review_context,
    pair_page_with_sources,
)
from kb.review.refiner import load_review_history, refine_page, save_review_history


def _create_page(wiki_dir: Path, page_id: str, title: str, content: str, source_ref: str) -> None:
    """Helper to create a wiki page with frontmatter."""
    page_path = wiki_dir / f"{page_id}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        f'---\ntitle: "{title}"\nsource:\n  - {source_ref}\n'
        f"created: 2026-04-06\nupdated: 2026-04-06\ntype: concept\n"
        f"confidence: stated\n---\n\n"
    )
    page_path.write_text(fm + content, encoding="utf-8")


def _create_source(raw_dir: Path, source_ref: str, content: str) -> None:
    """Helper to create a raw source file."""
    source_path = raw_dir / source_ref.removeprefix("raw/")
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(content, encoding="utf-8")


# ── pair_page_with_sources ────────────────────────────────────


def test_pair_page_with_sources(tmp_project):
    """pair_page_with_sources returns page content and source content."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG is retrieval.", "raw/articles/rag.md")
    _create_source(raw_dir, "raw/articles/rag.md", "Full RAG article content here.")

    result = pair_page_with_sources("concepts/rag", wiki_dir, raw_dir)
    assert result["page_id"] == "concepts/rag"
    assert "RAG is retrieval." in result["page_content"]
    assert len(result["source_contents"]) == 1
    assert result["source_contents"][0]["content"] == "Full RAG article content here."


def test_pair_page_with_sources_missing_source(tmp_project):
    """pair_page_with_sources handles missing source files gracefully."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG content.", "raw/articles/missing.md")

    result = pair_page_with_sources("concepts/rag", wiki_dir, raw_dir)
    assert result["source_contents"][0]["content"] is None
    assert "error" in result["source_contents"][0]


def test_pair_page_with_sources_page_not_found(tmp_project):
    """pair_page_with_sources returns error for non-existent page."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    result = pair_page_with_sources("concepts/nonexistent", wiki_dir, raw_dir)
    assert "error" in result


def test_pair_page_with_sources_multiple_sources(tmp_project):
    """pair_page_with_sources handles pages with multiple sources."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    page_path = wiki_dir / "concepts" / "rag.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        '---\ntitle: "RAG"\nsource:\n  - raw/articles/rag1.md\n'
        "  - raw/articles/rag2.md\ncreated: 2026-04-06\nupdated: 2026-04-06\n"
        "type: concept\nconfidence: stated\n---\n\nRAG content."
    )
    page_path.write_text(fm, encoding="utf-8")
    _create_source(raw_dir, "raw/articles/rag1.md", "Source 1.")
    _create_source(raw_dir, "raw/articles/rag2.md", "Source 2.")

    result = pair_page_with_sources("concepts/rag", wiki_dir, raw_dir)
    assert len(result["source_contents"]) == 2


# ── build_review_context ──────────────────────────────────────


def test_build_review_context(tmp_project):
    """build_review_context returns formatted text with checklist."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG is retrieval.", "raw/articles/rag.md")
    _create_source(raw_dir, "raw/articles/rag.md", "Full RAG article.")

    context = build_review_context("concepts/rag", wiki_dir, raw_dir)
    assert "Review Context for: concepts/rag" in context
    assert "RAG is retrieval." in context
    assert "Full RAG article." in context
    assert "Review Checklist" in context


def test_build_review_context_not_found(tmp_project):
    """build_review_context returns error string for missing page."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    context = build_review_context("concepts/nonexistent", wiki_dir, raw_dir)
    assert "Error:" in context


def test_build_review_checklist():
    """build_review_checklist returns checklist with all 6 items."""
    checklist = build_review_checklist()
    assert "Source fidelity" in checklist
    assert "Entity/concept accuracy" in checklist
    assert "Wikilink validity" in checklist
    assert "Confidence level" in checklist
    assert "No hallucination" in checklist
    assert "Title accuracy" in checklist


# ── refine_page ───────────────────────────────────────────────


def test_refine_page(tmp_project):
    """refine_page updates content while preserving frontmatter."""
    wiki_dir = tmp_project / "wiki"
    _create_page(wiki_dir, "concepts/rag", "RAG", "Old content.", "raw/articles/rag.md")

    result = refine_page(
        "concepts/rag",
        "New improved content.",
        "Fixed unsourced claim",
        wiki_dir=wiki_dir,
        history_path=tmp_project / "history.json",
    )
    assert result["updated"] is True

    # Verify content changed but frontmatter preserved
    text = (wiki_dir / "concepts" / "rag.md").read_text(encoding="utf-8")
    assert "New improved content." in text
    assert 'title: "RAG"' in text
    assert f"updated: {date.today().isoformat()}" in text
    assert "Old content." not in text


def test_refine_page_preserves_frontmatter_format(tmp_project):
    """refine_page preserves exact frontmatter key order and formatting."""
    wiki_dir = tmp_project / "wiki"
    _create_page(wiki_dir, "concepts/rag", "RAG", "Old.", "raw/articles/rag.md")

    refine_page(
        "concepts/rag",
        "New.",
        "test",
        wiki_dir=wiki_dir,
        history_path=tmp_project / "history.json",
    )
    text = (wiki_dir / "concepts" / "rag.md").read_text(encoding="utf-8")
    # Frontmatter should still have source field intact
    assert "raw/articles/rag.md" in text
    assert "type: concept" in text
    assert "confidence: stated" in text


def test_refine_page_logs_to_wiki_log(tmp_project):
    """refine_page appends entry to wiki/log.md."""
    wiki_dir = tmp_project / "wiki"
    _create_page(wiki_dir, "concepts/rag", "RAG", "Old.", "raw/articles/rag.md")

    refine_page(
        "concepts/rag",
        "New.",
        "Fixed claim",
        wiki_dir=wiki_dir,
        history_path=tmp_project / "history.json",
    )
    log = (wiki_dir / "log.md").read_text(encoding="utf-8")
    assert "refine" in log
    assert "concepts/rag" in log
    assert "Fixed claim" in log


def test_refine_page_saves_review_history(tmp_project):
    """refine_page appends to review history JSON."""
    wiki_dir = tmp_project / "wiki"
    history_path = tmp_project / "history.json"
    _create_page(wiki_dir, "concepts/rag", "RAG", "Old.", "raw/articles/rag.md")

    refine_page(
        "concepts/rag",
        "New.",
        "Fixed claim",
        wiki_dir=wiki_dir,
        history_path=history_path,
    )
    history = load_review_history(history_path)
    assert len(history) == 1
    assert history[0]["page_id"] == "concepts/rag"
    assert history[0]["revision_notes"] == "Fixed claim"


def test_refine_page_not_found(tmp_project):
    """refine_page returns error for non-existent page."""
    wiki_dir = tmp_project / "wiki"
    result = refine_page(
        "concepts/nonexistent",
        "Content.",
        "notes",
        wiki_dir=wiki_dir,
        history_path=tmp_project / "history.json",
    )
    assert "error" in result


# ── Review history ────────────────────────────────────────────


def test_load_review_history_empty(tmp_path):
    """load_review_history returns empty list when file doesn't exist."""
    assert load_review_history(tmp_path / "history.json") == []


def test_save_and_load_review_history(tmp_path):
    """Round-trip: save then load review history."""
    history_path = tmp_path / "history.json"
    history = [{"page_id": "concepts/rag", "revision_notes": "test"}]
    save_review_history(history, history_path)
    loaded = load_review_history(history_path)
    assert loaded == history


def test_refine_page_missing_updated_field(tmp_project):
    """refine_page adds updated field when missing from frontmatter."""
    wiki_dir = tmp_project / "wiki"
    page_path = wiki_dir / "concepts" / "rag.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    # Frontmatter without updated: field
    fm = (
        '---\ntitle: "RAG"\nsource:\n  - raw/articles/rag.md\n'
        "created: 2026-04-06\ntype: concept\nconfidence: stated\n---\n\nOld."
    )
    page_path.write_text(fm, encoding="utf-8")

    refine_page(
        "concepts/rag",
        "New.",
        "test",
        wiki_dir=wiki_dir,
        history_path=tmp_project / "history.json",
    )
    text = page_path.read_text(encoding="utf-8")
    assert f"updated: {date.today().isoformat()}" in text


def test_refine_page_creates_log_when_missing(tmp_project):
    """refine_page creates log.md if it doesn't exist."""
    wiki_dir = tmp_project / "wiki"
    _create_page(wiki_dir, "concepts/rag", "RAG", "Old.", "raw/articles/rag.md")
    # Remove the log.md that tmp_project creates
    log_path = wiki_dir / "log.md"
    log_path.unlink()
    assert not log_path.exists()

    refine_page(
        "concepts/rag",
        "New.",
        "test",
        wiki_dir=wiki_dir,
        history_path=tmp_project / "history.json",
    )
    assert log_path.exists()
    log = log_path.read_text(encoding="utf-8")
    assert "concepts/rag" in log


# ── Concurrent-safety regression tests (Phase 4.5 HIGH) ──────────────────────


def test_refine_page_concurrent_both_succeed(tmp_project):
    """Regression: Phase 4.5 HIGH item H1 (refine_page concurrent RMW overwrite).

    Two threads calling refine_page on the same page concurrently must both succeed
    and both audit entries must appear in the history file.
    """
    wiki_dir = tmp_project / "wiki"
    history_path = tmp_project / "history.json"
    _create_page(wiki_dir, "concepts/concurrent", "Concurrent", "Original.", "raw/articles/c.md")

    for iteration in range(10):
        # Reset page content to known state for each iteration
        _create_page(
            wiki_dir, "concepts/concurrent", "Concurrent", "Original.", "raw/articles/c.md"
        )

        results = []
        errors: list[Exception] = []

        def _refine(body: str, note: str) -> None:
            try:
                res = refine_page(
                    "concepts/concurrent",
                    body,
                    note,
                    wiki_dir=wiki_dir,
                    history_path=history_path,
                )
                results.append(res)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=_refine, args=("Body from thread-1.", "note-t1"))
        t2 = threading.Thread(target=_refine, args=("Body from thread-2.", "note-t2"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Iteration {iteration}: unexpected exceptions: {errors}"
        assert len(results) == 2, f"Iteration {iteration}: expected 2 results, got {results}"
        for r in results:
            assert r.get("updated") is True or "error" not in r, (
                f"Iteration {iteration}: unexpected error result: {r}"
            )

        # Both audit entries must appear in the history
        history = load_review_history(history_path)
        notes = [h["revision_notes"] for h in history if h["page_id"] == "concepts/concurrent"]
        assert "note-t1" in notes, f"Iteration {iteration}: note-t1 missing from history: {notes}"
        assert "note-t2" in notes, f"Iteration {iteration}: note-t2 missing from history: {notes}"


def test_append_wiki_log_concurrent(tmp_project):
    """Regression: Phase 4.5 HIGH item H4 (append_wiki_log concurrent append).

    4 threads × 5 appends each = 20 entries; all must appear in the final log.
    H4 lock was already added in Task 1 — this test is the regression guard.
    """
    from kb.utils.wiki_log import append_wiki_log

    wiki_dir = tmp_project / "wiki"
    log_path = wiki_dir / "log.md"
    log_path.write_text("# Wiki Log\n\n", encoding="utf-8")

    errors: list[Exception] = []

    def _append_five(thread_id: int) -> None:
        for i in range(5):
            try:
                append_wiki_log("test", f"entry-t{thread_id}-i{i}", log_path)
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=_append_five, args=(tid,)) for tid in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Unexpected exceptions during concurrent log writes: {errors}"
    log_content = log_path.read_text(encoding="utf-8")
    for tid in range(4):
        for i in range(5):
            assert f"entry-t{tid}-i{i}" in log_content, f"Missing log entry: entry-t{tid}-i{i}"


# ── Phase 4 review/feedback/config fixes (cycle 55 fold) ──────────────
# Source: tests/test_v01011_review_feedback_fixes.py (deleted in same commit).


def test_refine_page_rejects_multiline_frontmatter_body(tmp_wiki):
    """Content that looks like a multi-line frontmatter block must be rejected."""
    from kb.review.refiner import refine_page

    page = tmp_wiki / "concepts" / "foo.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "---\ntitle: foo\ntype: concept\nconfidence: stated\n---\nBody\n",
        encoding="utf-8",
    )
    # Multi-line frontmatter-looking content
    malicious = "---\ntitle: evil\ntype: concept\nconfidence: stated\n---\n"
    result = refine_page("concepts/foo", malicious, revision_notes="update", wiki_dir=tmp_wiki)
    assert "error" in result, "Expected error for frontmatter-block content"


def test_refine_page_updated_regex_anchored(tmp_wiki):
    """'last_updated: 2023-01-01' in the body must NOT be rewritten by the date update."""
    from kb.review.refiner import refine_page

    page = tmp_wiki / "concepts" / "bar.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "---\ntitle: bar\ntype: concept\nconfidence: stated\n"
        "updated: 2023-01-01\n---\n"
        "Some body text with last_updated: 2022-12-31 in it.\n",
        encoding="utf-8",
    )
    refine_page(
        "concepts/bar",
        "New body with last_updated: 2022-12-31 inside.",
        revision_notes="x",
        wiki_dir=tmp_wiki,
    )
    final = page.read_text(encoding="utf-8")
    # The body's 'last_updated: 2022-12-31' must survive untouched
    assert "last_updated: 2022-12-31" in final


def test_embedding_dim_resolved():
    """EMBEDDING_DIM must be either deleted from config or validated in VectorIndex.

    Q2 host-shape preservation: this test joins test_review.py despite touching
    config + embeddings, because the source file groups it under "Phase 4
    review/feedback/config fixes" and splitting would create a merge surface
    with the parallel cycle-53 test_query.py edits.
    """
    from kb import config

    if not hasattr(config, "EMBEDDING_DIM"):
        return  # Deleted — PASS

    # If it still exists, it must be used somewhere (VectorIndex.build)
    import inspect

    try:
        from kb.query.embeddings import VectorIndex

        src = inspect.getsource(VectorIndex)
        assert "EMBEDDING_DIM" in src, (
            "EMBEDDING_DIM defined in config but not validated in VectorIndex"
        )
    except ImportError:
        pass


# ── Phase 3.97 Task 08 — Feedback store fixes (cycle 57 fold) ───────────────
#
# Folded from tests/test_v0916_task08.py per cycle-55 review/feedback receiver
# precedent. All 4 classes folded verbatim. No helper extraction.


class TestLoadFeedbackNullTypes:
    """load_feedback must reject entries/page_scores with None values."""

    def test_null_entries_returns_default(self, tmp_path):
        import json

        fb_file = tmp_path / "feedback.json"
        fb_file.write_text(
            json.dumps({"entries": None, "page_scores": {}}),
            encoding="utf-8",
        )

        from kb.feedback.store import load_feedback

        result = load_feedback(fb_file)
        assert isinstance(result["entries"], list)
        assert result["entries"] == []

    def test_null_page_scores_returns_default(self, tmp_path):
        import json

        fb_file = tmp_path / "feedback.json"
        fb_file.write_text(
            json.dumps({"entries": [], "page_scores": None}),
            encoding="utf-8",
        )

        from kb.feedback.store import load_feedback

        result = load_feedback(fb_file)
        assert isinstance(result["page_scores"], dict)
        assert result["page_scores"] == {}

    def test_both_null_returns_default(self, tmp_path):
        import json

        fb_file = tmp_path / "feedback.json"
        fb_file.write_text(
            json.dumps({"entries": None, "page_scores": None}),
            encoding="utf-8",
        )

        from kb.feedback.store import load_feedback

        result = load_feedback(fb_file)
        assert result["entries"] == []
        assert result["page_scores"] == {}


class TestAddFeedbackEntryKeyError:
    """add_feedback_entry must handle missing keys in page_scores."""

    def test_missing_wrong_key_no_crash(self, tmp_path):
        import json

        fb_file = tmp_path / "feedback.json"
        fb_file.write_text(
            json.dumps(
                {
                    "entries": [],
                    "page_scores": {
                        "concepts/test": {"useful": 5, "trust": 0.7}
                        # missing "wrong" and "incomplete"
                    },
                }
            ),
            encoding="utf-8",
        )

        from kb.feedback.store import add_feedback_entry

        # Should not raise KeyError
        entry = add_feedback_entry(
            question="test question",
            rating="useful",
            cited_pages=["concepts/test"],
            path=fb_file,
        )
        assert entry["rating"] == "useful"


class TestFeedbackLockSleep:
    """_feedback_lock must sleep after evicting a stale lock."""

    def test_lock_eviction_sleeps(self, tmp_path):
        """After evicting a stale lock, the loop should sleep before retry."""
        import json
        import time

        fb_file = tmp_path / "feedback.json"
        fb_file.write_text(json.dumps({"entries": [], "page_scores": {}}), encoding="utf-8")

        lock_file = fb_file.with_suffix(".json.lock")
        # Cycle 2 item 2: valid ASCII int for dead PID (empty content now raises).
        lock_file.write_text("999999999", encoding="ascii")

        from kb.feedback.store import _feedback_lock

        start = time.monotonic()
        with _feedback_lock(fb_file, timeout=0.3):
            elapsed = time.monotonic() - start
            # Should have waited at least a little (the sleep after eviction)
            assert elapsed >= 0.01


class TestGetCoverageGapsDedup:
    """get_coverage_gaps must deduplicate repeated questions."""

    def test_duplicate_questions_deduplicated(self, tmp_path):
        import json

        fb_file = tmp_path / "feedback.json"
        fb_file.write_text(
            json.dumps(
                {
                    "entries": [
                        {
                            "question": "What is RAG?",
                            "rating": "incomplete",
                            "notes": "missing context",
                        },
                        {
                            "question": "What is RAG?",
                            "rating": "incomplete",
                            "notes": "still incomplete",
                        },
                        {
                            "question": "What is RAG?",
                            "rating": "incomplete",
                            "notes": "again",
                        },
                        {
                            "question": "What is LLM?",
                            "rating": "incomplete",
                            "notes": "need more",
                        },
                    ],
                    "page_scores": {},
                }
            ),
            encoding="utf-8",
        )

        from kb.feedback.reliability import get_coverage_gaps

        gaps = get_coverage_gaps(fb_file)
        questions = [g["question"] for g in gaps]
        assert questions.count("What is RAG?") == 1
        assert questions.count("What is LLM?") == 1
