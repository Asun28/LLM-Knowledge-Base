"""Tests for v0.9.2 lint/query fixes."""

import inspect
import logging
from pathlib import Path

import kb.mcp.app
import kb.mcp.browse
from kb.mcp.browse import kb_read_page
from kb.mcp.health import kb_evolve, kb_lint

# ── Helpers ──────────────────────────────────────────────────────


def _write_page(wiki_dir: Path, page_id: str, content: str) -> Path:
    """Write a wiki page with minimal valid frontmatter."""
    page_path = wiki_dir / f"{page_id}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        '---\ntitle: "Test Page"\nsource:\n  - "raw/articles/test.md"\n'
        "created: 2026-04-07\nupdated: 2026-04-07\ntype: concept\n"
        "confidence: stated\n---\n\n"
    )
    page_path.write_text(fm + content, encoding="utf-8")
    return page_path


def _setup_wiki_dir(tmp_wiki, monkeypatch):
    """Monkeypatch WIKI_DIR in both browse and app modules."""
    monkeypatch.setattr(kb.mcp.browse, "WIKI_DIR", tmp_wiki)
    monkeypatch.setattr(kb.mcp.app, "WIKI_DIR", tmp_wiki)


# ── Fix 1: Domain terms NOT filtered from common_words ───────────


def test_term_overlap_includes_domain_terms(tmp_wiki):
    """Pages sharing domain terms like 'entity' should be grouped together.

    Previously 'entity', 'concept', 'summary', 'confidence', 'speculative',
    'inferred' were in common_words and filtered out, preventing grouping.
    """
    from kb.lint.semantic import _group_by_term_overlap

    # Both pages share: entity, concept, summary (3 domain terms = MIN_SHARED_TERMS)
    _write_page(
        tmp_wiki,
        "concepts/alpha",
        "This page discusses entity types. The entity concept is fundamental. "
        "Each entity has a summary field. The summary captures key facts about the entity.",
    )
    _write_page(
        tmp_wiki,
        "concepts/beta",
        "Another page about entity design. The entity concept matters here too. "
        "We generate a summary for each entity. The summary helps retrieval.",
    )

    groups = _group_by_term_overlap(tmp_wiki)

    # The two pages should be grouped together via shared domain terms
    found = False
    for group in groups:
        if "concepts/alpha" in group and "concepts/beta" in group:
            found = True
            break
    assert found, f"Expected concepts/alpha and concepts/beta to be grouped, got: {groups}"


# ── Fix 2: Consistency groups chunked, not truncated ─────────────


def test_consistency_groups_chunked_not_truncated(tmp_wiki):
    """build_consistency_context with 8 page_ids should include ALL 8, not just first 5."""
    from kb.lint.semantic import build_consistency_context

    # Create 8 pages
    page_ids = []
    for i in range(8):
        pid = f"concepts/page-{i}"
        _write_page(tmp_wiki, pid, f"Content for page {i}. Some unique text here.")
        page_ids.append(pid)

    result = build_consistency_context(page_ids=page_ids, wiki_dir=tmp_wiki)

    # All 8 pages should appear in the output
    for pid in page_ids:
        assert pid in result, f"Page {pid} missing from consistency context"

    # Should have 2 groups (5 + 3) since MAX_CONSISTENCY_GROUP_SIZE is 5
    assert "Group 1" in result
    assert "Group 2" in result


def test_consistency_groups_exact_max_size_single_group(tmp_wiki):
    """Exactly MAX_CONSISTENCY_GROUP_SIZE (5) pages should be one group."""
    from kb.lint.semantic import build_consistency_context

    page_ids = []
    for i in range(5):
        pid = f"concepts/exact-{i}"
        _write_page(tmp_wiki, pid, f"Content for exact page {i}.")
        page_ids.append(pid)

    result = build_consistency_context(page_ids=page_ids, wiki_dir=tmp_wiki)

    for pid in page_ids:
        assert pid in result
    assert "Group 1" in result
    # Should NOT have Group 2
    assert "Group 2" not in result


def test_consistency_auto_groups_not_truncated(tmp_wiki):
    """Auto-discovered groups should not be truncated either."""
    from kb.lint.semantic import build_consistency_context

    # Create 7 pages all sharing the same source (triggers _group_by_shared_sources)
    source_ref = "raw/articles/shared-source.md"
    page_ids = []
    for i in range(7):
        pid = f"concepts/shared-{i}"
        page_path = tmp_wiki / f"{pid}.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        fm = (
            f'---\ntitle: "Shared Page {i}"\nsource:\n  - "{source_ref}"\n'
            f"created: 2026-04-07\nupdated: 2026-04-07\ntype: concept\n"
            f"confidence: stated\n---\n\n"
        )
        page_path.write_text(fm + f"Content for shared page {i}.", encoding="utf-8")
        page_ids.append(pid)

    result = build_consistency_context(wiki_dir=tmp_wiki)

    # All 7 pages should appear in the output (not truncated to 5)
    for pid in page_ids:
        assert pid in result, f"Page {pid} missing from auto-discovered consistency context"


# ── Fix 3: Query context truncation logging ──────────────────────


def test_query_context_truncation_logging(caplog):
    """Truncation of query context should produce a debug log message."""
    from kb.query.engine import _build_query_context

    pages = [
        {
            "id": "concepts/big-page",
            "type": "concept",
            "confidence": "stated",
            "title": "Big Page",
            "content": "x" * 5000,
        },
        {
            "id": "concepts/excluded-page",
            "type": "concept",
            "confidence": "stated",
            "title": "Excluded Page",
            "content": "y" * 5000,
        },
    ]

    with caplog.at_level(logging.DEBUG, logger="kb.query.engine"):
        result = _build_query_context(pages, max_chars=3000)

    # First page should be partially included (truncated)
    assert "[...truncated]" in result

    # Should have logged truncation
    assert any(
        "truncated" in r.message.lower() or "excluded" in r.message.lower() for r in caplog.records
    ), f"Expected truncation log message, got: {[r.message for r in caplog.records]}"


def test_query_context_exclusion_logging(caplog):
    """When remaining space is <= 100 chars, page should be excluded with a log message."""
    from kb.query.engine import _build_query_context

    pages = [
        {
            "id": "concepts/fills-space",
            "type": "concept",
            "confidence": "stated",
            "title": "Fills Space",
            "content": "x" * 500,
        },
        {
            "id": "concepts/no-room",
            "type": "concept",
            "confidence": "stated",
            "title": "No Room",
            "content": "y" * 500,
        },
    ]

    # Set max_chars so second page has < 100 chars remaining
    first_section_size = len(
        "--- Page: concepts/fills-space (type: concept, confidence: stated) ---\n"
        f"Title: Fills Space\n\n{'x' * 500}\n"
    )
    max_chars = first_section_size + 50  # Only 50 chars left for second page

    with caplog.at_level(logging.DEBUG, logger="kb.query.engine"):
        _build_query_context(pages, max_chars=max_chars)

    assert any("excluded" in r.message.lower() for r in caplog.records), (
        f"Expected exclusion log message, got: {[r.message for r in caplog.records]}"
    )


# ── Fix 4: BM25 empty corpus avgdl warning ──────────────────────


def test_bm25_empty_corpus_avgdl_warning(caplog):
    """BM25Index with all-empty documents should log a warning about avgdl fallback."""
    from kb.query.bm25 import BM25Index

    with caplog.at_level(logging.WARNING, logger="kb.query.bm25"):
        index = BM25Index([[], [], []])

    assert index.avgdl == 1.0
    assert any("avgdl" in r.message.lower() for r in caplog.records), (
        f"Expected avgdl warning, got: {[r.message for r in caplog.records]}"
    )


def test_bm25_nonempty_corpus_no_warning(caplog):
    """BM25Index with non-empty documents should NOT log the avgdl warning."""
    from kb.query.bm25 import BM25Index

    with caplog.at_level(logging.WARNING, logger="kb.query.bm25"):
        index = BM25Index([["hello", "world"], ["foo", "bar"]])

    assert index.avgdl > 0
    assert not any("avgdl" in r.message.lower() for r in caplog.records)


# ── Fix 5: Case-insensitive page lookup validates path ───────────


def test_read_page_case_insensitive_finds_page(tmp_wiki, monkeypatch):
    """kb_read_page should find a page even with different casing."""
    _setup_wiki_dir(tmp_wiki, monkeypatch)

    # Create page with specific casing
    _write_page(tmp_wiki, "concepts/MyTopic", "Content about my topic.")

    # Query with different casing
    result = kb_read_page("concepts/mytopic")

    # Should find the page and return its content
    assert "Content about my topic" in result


def test_read_page_case_insensitive_valid_path(tmp_wiki, monkeypatch):
    """Case-insensitive match should be within WIKI_DIR (path validation)."""
    _setup_wiki_dir(tmp_wiki, monkeypatch)

    # Create a normal page
    _write_page(tmp_wiki, "concepts/safe-page", "Safe content.")

    # A page_id that passes initial _validate_page_id but the case-insensitive
    # fallback should still validate the resolved path
    result = kb_read_page("concepts/Safe-Page")
    assert "Safe content" in result


# ── Fix 6: health.py uses logger.error, not logger.exception ────


def test_health_lint_uses_logger_error():
    """Verify kb_lint error handler uses logger.error, not logger.exception."""
    source = inspect.getsource(kb_lint)
    assert "logger.error" in source
    assert "logger.exception" not in source


def test_health_evolve_uses_logger_error():
    """Verify kb_evolve error handler uses logger.error, not logger.exception."""
    source = inspect.getsource(kb_evolve)
    assert "logger.error" in source
    assert "logger.exception" not in source
