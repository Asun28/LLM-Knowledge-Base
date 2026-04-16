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
