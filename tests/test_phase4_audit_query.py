"""Tests for query engine correctness — Phase 4 audit."""
import pytest
from kb.config import CONTEXT_TIER1_BUDGET, QUERY_CONTEXT_MAX_CHARS
from kb.query.engine import _build_query_context


def _make_page(pid, ptype, size):
    """Create a minimal page dict for testing."""
    return {
        "id": pid, "type": ptype, "confidence": "stated",
        "title": pid, "content": "x" * size,
    }


def test_tier1_budget_prevents_summary_starvation():
    """A huge summary must not consume the full budget — entity pages must get context."""
    # Summary that exceeds CONTEXT_TIER1_BUDGET alone
    big_summary = _make_page("summaries/big", "summary", CONTEXT_TIER1_BUDGET + 5000)
    small_entity = _make_page("entities/foo", "entity", 100)
    pages = [big_summary, small_entity]

    result = _build_query_context(pages, max_chars=QUERY_CONTEXT_MAX_CHARS)

    assert "entities/foo" in result["context_pages"], (
        f"Entity page was starved by oversized summary. "
        f"Got context_pages={result['context_pages']}"
    )


def test_tier1_budget_allows_multiple_small_summaries():
    """Multiple small summaries that fit within CONTEXT_TIER1_BUDGET must all be included."""
    chunk = CONTEXT_TIER1_BUDGET // 4
    summaries = [_make_page(f"summaries/s{i}", "summary", chunk - 200) for i in range(3)]
    result = _build_query_context(summaries, max_chars=QUERY_CONTEXT_MAX_CHARS)
    for s in summaries:
        assert s["id"] in result["context_pages"], f"Summary {s['id']} was unexpectedly excluded"


def test_raw_fallback_truncates_first_oversized_section(tmp_path, monkeypatch):
    """First raw-source section larger than the remaining budget must be truncated, not skipped."""
    import kb.query.engine as eng

    # A raw source whose content exceeds the entire query budget
    large_content = "y" * (QUERY_CONTEXT_MAX_CHARS + 1000)
    monkeypatch.setattr(eng, "search_raw_sources", lambda q, **kw: [
        {"id": "raw/articles/big.md", "content": large_content}
    ])
    # A tiny wiki page so matching_pages is non-empty (avoids early-return)
    # but wiki context stays tiny so raw fallback fires
    tiny_page = _make_page("entities/tiny", "entity", 50)
    monkeypatch.setattr(eng, "search_pages", lambda q, wiki_dir=None, **kw: [tiny_page])
    captured_prompts = []
    monkeypatch.setattr(eng, "call_llm", lambda prompt, **kw: (captured_prompts.append(prompt) or "answer"))

    result = eng.query_wiki("test question", wiki_dir=tmp_path)

    # raw source content must appear in the prompt (truncated, not absent)
    assert captured_prompts, "call_llm was not called"
    assert "raw/articles/big.md" in captured_prompts[0], (
        "Oversized raw source was completely skipped instead of truncated"
    )


def test_raw_fallback_skips_when_context_already_full(tmp_path, monkeypatch):
    """Raw fallback must not fire when wiki context already exceeds the half-budget threshold."""
    import kb.query.engine as eng
    from kb.config import QUERY_CONTEXT_MAX_CHARS

    raw_called = []
    monkeypatch.setattr(eng, "search_raw_sources", lambda q, **kw: (raw_called.append(True) or []))

    # Return a page that fills more than half the budget
    big_page = _make_page("summaries/large", "summary", QUERY_CONTEXT_MAX_CHARS // 2 + 1000)
    monkeypatch.setattr(eng, "search_pages", lambda q, wiki_dir=None, **kw: [big_page])
    monkeypatch.setattr(eng, "call_llm", lambda prompt, **kw: "answer")

    eng.query_wiki("test question", wiki_dir=tmp_path)
    assert not raw_called, "Raw fallback was triggered even though wiki context was already full"
