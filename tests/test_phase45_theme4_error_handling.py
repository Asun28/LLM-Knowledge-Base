"""Regression tests for Phase 4.5 HIGH cycle 1 — Theme 4 error-handling granularity + Q_C.

Items covered: H15, H16, H18, Q_C.
"""

import logging
from pathlib import Path

import httpx
import pytest

from kb.utils.llm import LLMError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bad_request_error(message: str):
    """Create a real anthropic.BadRequestError with the given message."""
    import anthropic

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(400, request=request, text=message)
    return anthropic.BadRequestError(message=message, response=response, body={})


def _make_rate_limit_error(message: str = "rate limit exceeded"):
    """Create a real anthropic.RateLimitError."""
    import anthropic

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(429, request=request, text=message)
    return anthropic.RateLimitError(message=message, response=response, body={})


# ---------------------------------------------------------------------------
# H15: rewrite_query — narrow except to LLMError, log at WARNING
# ---------------------------------------------------------------------------


def test_h15_rewrite_query_propagates_value_error(monkeypatch):
    """Regression: Phase 4.5 HIGH item H15 (ValueError must propagate from rewrite_query)."""
    from kb.query.rewriter import rewrite_query

    def _raise_value_error(*a, **kw):
        raise ValueError("bad tier")

    monkeypatch.setattr("kb.query.rewriter.call_llm", _raise_value_error)

    with pytest.raises(ValueError, match="bad tier"):
        # Use a question that triggers _should_rewrite (has pronoun)
        rewrite_query("How does it work?", conversation_context="prior context about rag")


def test_h15_rewrite_query_catches_llm_error_and_warns(monkeypatch, caplog):
    """Regression: Phase 4.5 HIGH item H15 (LLMError falls back + logs WARNING, not DEBUG)."""
    from kb.query.rewriter import rewrite_query

    def _raise_llm_error(*a, **kw):
        raise LLMError("scan tier failed")

    monkeypatch.setattr("kb.query.rewriter.call_llm", _raise_llm_error)

    with caplog.at_level(logging.WARNING, logger="kb.query.rewriter"):
        result = rewrite_query("How does it work?", conversation_context="context about rag")

    # Should fall back to original question
    assert result == "How does it work?"
    # Should emit a WARNING (not just DEBUG)
    warning_msgs = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning_msgs, "Expected at least one WARNING log from rewrite_query on LLMError"
    # Should include the question or error text in the log
    all_text = " ".join(r.getMessage() for r in warning_msgs)
    assert "How does it work?" in all_text or "scan tier failed" in all_text, (
        "WARNING should mention the question or error"
    )


def test_h15_rewrite_query_does_not_emit_debug_only_on_llm_error(monkeypatch, caplog):
    """Regression: Phase 4.5 HIGH item H15 (LLMError must not be silently swallowed at DEBUG)."""
    from kb.query.rewriter import rewrite_query

    def _raise_llm_error(*a, **kw):
        raise LLMError("scan tier failed")

    monkeypatch.setattr("kb.query.rewriter.call_llm", _raise_llm_error)

    with caplog.at_level(logging.DEBUG, logger="kb.query.rewriter"):
        rewrite_query("How does it work?", conversation_context="context about rag")

    # Confirm no record is at DEBUG level for this error (only WARNING or above)
    debug_only_errors = [
        r
        for r in caplog.records
        if r.levelno == logging.DEBUG
        and ("failed" in r.getMessage().lower() or "error" in r.getMessage().lower())
    ]
    assert not debug_only_errors, (
        "LLMError should emit WARNING, not DEBUG — "
        f"found: {[r.getMessage() for r in debug_only_errors]}"
    )


# ---------------------------------------------------------------------------
# H16: kb_query use_api=True — Error[category] tags
# ---------------------------------------------------------------------------


def test_h16_bad_request_too_long_returns_prompt_too_long_tag(monkeypatch):
    """Regression: Phase 4.5 HIGH item H16 (BadRequestError 'too long' → Error[prompt_too_long])."""
    import kb.mcp.core as core_mod

    err = _make_bad_request_error("Request is too long for the context window")

    def _raise(question, **kw):
        raise err

    import kb.query.engine as _qe

    monkeypatch.setattr(_qe, "query_wiki", _raise)

    result = core_mod.kb_query("some question", use_api=True)

    assert result.startswith("Error[prompt_too_long]"), (
        f"Expected Error[prompt_too_long], got: {result!r}"
    )


def test_h16_bad_request_generic_returns_invalid_input_tag(monkeypatch):
    """Regression: Phase 4.5 HIGH item H16 (generic BadRequestError → Error[invalid_input])."""
    import kb.mcp.core as core_mod

    err = _make_bad_request_error("Invalid parameter value")

    def _raise(question, **kw):
        raise err

    import kb.query.engine as _qe

    monkeypatch.setattr(_qe, "query_wiki", _raise)

    result = core_mod.kb_query("some question", use_api=True)

    assert result.startswith("Error[invalid_input]"), (
        f"Expected Error[invalid_input], got: {result!r}"
    )


def test_h16_rate_limit_error_returns_rate_limit_tag(monkeypatch):
    """Regression: Phase 4.5 HIGH item H16 (RateLimitError → Error[rate_limit])."""
    import kb.mcp.core as core_mod

    err = _make_rate_limit_error()

    def _raise(question, **kw):
        raise err

    import kb.query.engine as _qe

    monkeypatch.setattr(_qe, "query_wiki", _raise)

    result = core_mod.kb_query("some question", use_api=True)

    assert "Error[rate_limit]" in result, f"Expected Error[rate_limit] in result, got: {result!r}"


def test_h16_llm_error_returns_internal_tag(monkeypatch):
    """Regression: Phase 4.5 HIGH item H16 (LLMError → Error[internal])."""
    import kb.mcp.core as core_mod

    def _raise(question, **kw):
        raise LLMError("retry exhausted")

    import kb.query.engine as _qe

    monkeypatch.setattr(_qe, "query_wiki", _raise)

    result = core_mod.kb_query("some question", use_api=True)

    assert "Error[internal]" in result, f"Expected Error[internal] in result, got: {result!r}"
    assert "LLM call failed" in result or "retry exhausted" in result, (
        f"Expected LLM failure detail in result, got: {result!r}"
    )


def test_h16_unexpected_exception_returns_internal_tag(monkeypatch):
    """Regression: Phase 4.5 HIGH item H16 (unexpected Exception → Error[internal])."""
    import kb.mcp.core as core_mod

    def _raise(question, **kw):
        raise RuntimeError("disk full")

    import kb.query.engine as _qe

    monkeypatch.setattr(_qe, "query_wiki", _raise)

    result = core_mod.kb_query("some question", use_api=True)

    assert "Error[internal]" in result, f"Expected Error[internal] in result, got: {result!r}"


# ---------------------------------------------------------------------------
# H18: kb_query Claude Code mode — applies rewrite_query when context non-empty
# ---------------------------------------------------------------------------


def test_h18_claude_code_mode_calls_rewrite_query_with_context(monkeypatch, tmp_wiki):
    """Regression: Phase 4.5 HIGH item H18 (rewrite_query called in CC mode with context)."""
    import kb.mcp.core as core_mod

    rewrite_calls = []

    def spy_rewrite(question, conversation_context=None):
        rewrite_calls.append({"question": question, "conversation_context": conversation_context})
        return question  # return unchanged

    monkeypatch.setattr(core_mod, "rewrite_query", spy_rewrite)
    # Return empty results so we get the "no pages found" path — avoids full wiki setup
    import kb.query.engine as _qe

    monkeypatch.setattr(_qe, "search_pages", lambda *a, **kw: [])

    core_mod.kb_query("What is it?", conversation_context="User asked about RAG earlier.")

    assert rewrite_calls, "rewrite_query should have been called in Claude Code mode"
    assert rewrite_calls[0]["conversation_context"] == "User asked about RAG earlier.", (
        "rewrite_query should receive the conversation_context"
    )


def test_h18_claude_code_mode_skips_rewrite_when_no_context(monkeypatch):
    """Regression: Phase 4.5 HIGH item H18 (rewrite_query not called when context empty)."""
    import kb.mcp.core as core_mod

    rewrite_calls = []

    def spy_rewrite(question, conversation_context=None):
        rewrite_calls.append({"question": question, "conversation_context": conversation_context})
        return question

    monkeypatch.setattr(core_mod, "rewrite_query", spy_rewrite)
    import kb.query.engine as _qe

    monkeypatch.setattr(_qe, "search_pages", lambda *a, **kw: [])

    core_mod.kb_query("What is RAG?", conversation_context="")

    # Should NOT be called — or if called, context must be empty/None
    for call in rewrite_calls:
        assert not call.get("conversation_context"), (
            "rewrite_query should not be invoked with non-empty context when context is empty"
        )


# ---------------------------------------------------------------------------
# Q_C: _update_existing_page — return on frontmatter parse error (no dupe source)
# ---------------------------------------------------------------------------


def _write_page(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_qc_update_existing_page_no_duplicate_source_on_bad_frontmatter(tmp_wiki):
    """Regression: Phase 4.5 Q_C (_update_existing_page returns on frontmatter parse error).

    When frontmatter.loads() raises, the function must return early instead of
    falling through to source injection, which previously caused duplicate source: entries.
    """
    from kb.ingest.pipeline import _update_existing_page

    # Create a page with deliberately malformed frontmatter that will raise
    # a yaml.YAMLError when parsed (tab character in YAML key is invalid)
    bad_frontmatter_content = (
        "---\n"
        "title: Test Page\n"
        "\tsource:\n"  # tab in YAML key position causes YAMLError
        "  - raw/articles/existing-source.md\n"
        "type: entity\n"
        "confidence: stated\n"
        "---\n\n"
        "Body content.\n"
    )
    page_path = tmp_wiki / "entities" / "test-entity.md"
    _write_page(page_path, bad_frontmatter_content)

    # Call once — with Q_C fix, returns early on bad frontmatter
    _update_existing_page(page_path, "raw/articles/new-source.md")

    # Call again — should NOT accumulate injections
    _update_existing_page(page_path, "raw/articles/new-source.md")
    content_after_second = page_path.read_text(encoding="utf-8")

    # Count occurrences of the source ref (Q_C fix: should be 0, returns early)
    count = content_after_second.count("new-source.md")
    assert count <= 1, (
        f"Source ref 'new-source.md' appears {count} times after two calls — "
        "duplicate injection on frontmatter error (Q_C regression)"
    )


def test_qc_update_existing_page_valid_frontmatter_works_normally(tmp_wiki):
    """Regression: Phase 4.5 Q_C (valid frontmatter path unaffected by the fix)."""
    import frontmatter as fm_mod

    from kb.ingest.pipeline import _update_existing_page

    valid_content = (
        "---\n"
        "title: Test Page\n"
        "source:\n"
        "  - raw/articles/existing-source.md\n"
        "type: entity\n"
        "confidence: stated\n"
        "updated: 2026-01-01\n"
        "---\n\n"
        "Body content.\n"
    )
    page_path = tmp_wiki / "entities" / "valid-entity.md"
    _write_page(page_path, valid_content)

    _update_existing_page(page_path, "raw/articles/new-source.md")
    content_after = page_path.read_text(encoding="utf-8")

    # The new source should be in the frontmatter source list
    post = fm_mod.loads(content_after)
    sources = post.metadata.get("source", [])
    if isinstance(sources, str):
        sources = [sources]
    assert "raw/articles/new-source.md" in sources, (
        "Valid-frontmatter page should have new source injected into frontmatter source: list"
    )
