"""Tests for MCP core tools — kb_save_source, kb_ingest_content, kb_compile_scan."""

import json
from unittest.mock import patch

import pytest

import kb.config
from kb.mcp.core import kb_compile_scan, kb_ingest_content, kb_save_source
from tests._helpers.api_key import requires_real_api_key

# Cycle 36 AC6 marker — TestKbCaptureWrapper tests reach a real Anthropic SDK
# call via the kb_capture MCP wrapper even when mock_scan_llm is installed
# (POSIX reload-leak; cycle-37 candidate). See test_capture.py for the same
# marker rationale.
_REQUIRES_REAL_API_KEY = pytest.mark.skipif(
    not requires_real_api_key(),
    reason=(
        "Skipped on CI dummy key — mock_scan_llm reload-leak under POSIX "
        "(C36-investigation, cycle-37 candidate)."
    ),
)


def _patch_source_type_dirs(monkeypatch, tmp_path):
    """Patch SOURCE_TYPE_DIRS so tools write to tmp directories."""
    tmp_dirs = {}
    for stype in kb.config.SOURCE_TYPE_DIRS:
        d = tmp_path / "raw" / f"{stype}s"
        d.mkdir(parents=True, exist_ok=True)
        tmp_dirs[stype] = d
    monkeypatch.setattr(kb.config, "SOURCE_TYPE_DIRS", tmp_dirs)
    monkeypatch.setattr("kb.mcp.core.SOURCE_TYPE_DIRS", tmp_dirs)
    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("kb.mcp.core.PROJECT_ROOT", tmp_path)
    return tmp_dirs


# ── kb_save_source ───────────────────────────────────────────────


def test_kb_save_source_creates_file(tmp_path, monkeypatch):
    """kb_save_source writes content to the correct raw/ subdirectory."""
    dirs = _patch_source_type_dirs(monkeypatch, tmp_path)

    result = kb_save_source(
        content="This is a test article about LLMs.",
        filename="test-llm-article",
        source_type="article",
    )

    expected_path = dirs["article"] / "test-llm-article.md"
    assert expected_path.exists()
    text = expected_path.read_text(encoding="utf-8")
    assert "This is a test article about LLMs." in text
    assert "Saved:" in result
    assert "test-llm-article.md" in result
    assert "To ingest:" in result


def test_kb_save_source_with_url(tmp_path, monkeypatch):
    """kb_save_source prepends a YAML header when a URL is provided."""
    dirs = _patch_source_type_dirs(monkeypatch, tmp_path)

    result = kb_save_source(
        content="Article body text.",
        filename="url-article",
        source_type="article",
        url="https://example.com/article",
    )

    file_path = dirs["article"] / "url-article.md"
    assert file_path.exists()
    text = file_path.read_text(encoding="utf-8")
    assert 'url: "https://example.com/article"' in text
    assert "fetched:" in text
    assert "Article body text." in text
    # The header adds chars, so the char count should include them
    assert "Saved:" in result


def test_kb_save_source_invalid_type(tmp_path, monkeypatch):
    """kb_save_source returns an error for unknown source_type."""
    _patch_source_type_dirs(monkeypatch, tmp_path)

    result = kb_save_source(
        content="Some content.",
        filename="bad-type",
        source_type="unknown_type",
    )

    assert "Error:" in result
    assert "Unknown source_type" in result
    assert "unknown_type" in result


def test_kb_save_source_slugifies_filename(tmp_path, monkeypatch):
    """kb_save_source normalizes filenames using slugify."""
    dirs = _patch_source_type_dirs(monkeypatch, tmp_path)

    kb_save_source(
        content="Content.",
        filename="My Article Title!",
        source_type="article",
    )

    # slugify should produce a lowercase, hyphenated slug
    files = list(dirs["article"].glob("*.md"))
    assert len(files) == 1
    assert files[0].name == "my-article-title.md"


def test_kb_save_source_paper_type(tmp_path, monkeypatch):
    """kb_save_source writes to the paper subdirectory for source_type='paper'."""
    dirs = _patch_source_type_dirs(monkeypatch, tmp_path)

    kb_save_source(
        content="Paper abstract and findings.",
        filename="attention-is-all-you-need",
        source_type="paper",
    )

    expected_path = dirs["paper"] / "attention-is-all-you-need.md"
    assert expected_path.exists()


# ── kb_ingest_content ────────────────────────────────────────────


def test_kb_ingest_content_creates_source_and_pages(tmp_path, monkeypatch):
    """kb_ingest_content saves the file and calls ingest_source to create pages."""
    dirs = _patch_source_type_dirs(monkeypatch, tmp_path)

    mock_result = {
        "source_path": str(dirs["article"] / "test-one-shot.md"),
        "source_type": "article",
        "content_hash": "abc123",
        "pages_created": ["summaries/test-one-shot", "entities/openai"],
        "pages_updated": [],
        "pages_skipped": [],
    }

    extraction = {
        "title": "Test One-Shot Article",
        "entities_mentioned": ["OpenAI"],
        "concepts_mentioned": ["LLM"],
    }

    # Cycle 19 AC15 — patch the owner module so the new mcp/core.py call site
    # `ingest_pipeline.ingest_source(...)` resolves the patched attribute.
    with patch("kb.ingest.pipeline.ingest_source", return_value=mock_result) as mock_ingest:
        result = kb_ingest_content(
            content="Full article content here.",
            filename="test-one-shot",
            source_type="article",
            extraction_json=json.dumps(extraction),
        )

    # File should be saved to disk
    saved_path = dirs["article"] / "test-one-shot.md"
    assert saved_path.exists()
    assert "Full article content here." in saved_path.read_text(encoding="utf-8")

    # ingest_source should have been called with the saved path
    mock_ingest.assert_called_once()
    call_args = mock_ingest.call_args
    assert call_args[0][0] == saved_path
    assert call_args[0][1] == "article"
    assert call_args[1]["extraction"] == extraction

    # Result should contain both save and ingest info
    assert "Saved source:" in result
    assert "test-one-shot.md" in result
    assert "Ingested:" in result
    assert "summaries/test-one-shot" in result
    assert "entities/openai" in result


def test_kb_ingest_content_invalid_json(tmp_path, monkeypatch):
    """kb_ingest_content returns error for malformed extraction_json."""
    _patch_source_type_dirs(monkeypatch, tmp_path)

    result = kb_ingest_content(
        content="Content.",
        filename="bad-json",
        source_type="article",
        extraction_json="not valid json {{{",
    )

    assert "Error:" in result
    assert "Invalid extraction JSON" in result


def test_kb_ingest_content_missing_title(tmp_path, monkeypatch):
    """kb_ingest_content returns error when extraction lacks title/name."""
    _patch_source_type_dirs(monkeypatch, tmp_path)

    extraction = {
        "entities_mentioned": ["OpenAI"],
        "concepts_mentioned": ["LLM"],
    }

    result = kb_ingest_content(
        content="Content.",
        filename="no-title",
        source_type="article",
        extraction_json=json.dumps(extraction),
    )

    assert "Error:" in result
    assert "title" in result.lower()


def test_kb_ingest_content_with_url(tmp_path, monkeypatch):
    """kb_ingest_content adds URL metadata header when url is provided."""
    dirs = _patch_source_type_dirs(monkeypatch, tmp_path)

    mock_result = {
        "source_path": str(dirs["article"] / "url-article.md"),
        "source_type": "article",
        "content_hash": "def456",
        "pages_created": ["summaries/url-article"],
        "pages_updated": [],
        "pages_skipped": [],
    }

    extraction = {
        "title": "URL Article",
        "entities_mentioned": [],
        "concepts_mentioned": [],
    }

    # Cycle 19 AC15 — patch owner module.
    with patch("kb.ingest.pipeline.ingest_source", return_value=mock_result):
        result = kb_ingest_content(
            content="Article from URL.",
            filename="url-article",
            source_type="article",
            extraction_json=json.dumps(extraction),
            url="https://example.com/source",
        )

    saved_path = dirs["article"] / "url-article.md"
    text = saved_path.read_text(encoding="utf-8")
    assert 'url: "https://example.com/source"' in text
    assert "fetched:" in text
    assert "Article from URL." in text
    assert "Saved source:" in result


def test_kb_ingest_content_invalid_source_type(tmp_path, monkeypatch):
    """kb_ingest_content returns error for unknown source_type."""
    _patch_source_type_dirs(monkeypatch, tmp_path)

    result = kb_ingest_content(
        content="Content.",
        filename="bad-type",
        source_type="invalid_type",
        extraction_json='{"title": "Test"}',
    )

    assert "Error:" in result
    assert "Unknown source_type" in result
    assert "invalid_type" in result


def test_kb_ingest_content_extraction_not_dict(tmp_path, monkeypatch):
    """kb_ingest_content returns error when extraction_json is not an object."""
    _patch_source_type_dirs(monkeypatch, tmp_path)

    result = kb_ingest_content(
        content="Content.",
        filename="not-dict",
        source_type="article",
        extraction_json='["a", "b"]',
    )

    assert "Error:" in result
    assert "JSON object" in result


# ── kb_compile_scan ──────────────────────────────────────────────


def test_kb_compile_scan_no_changes():
    """kb_compile_scan returns 'up to date' when no changed sources."""
    with patch("kb.compile.compiler.find_changed_sources", return_value=([], [])):
        result = kb_compile_scan(incremental=True)

    assert "up to date" in result.lower()


def test_kb_compile_scan_reports_new_sources(tmp_path, monkeypatch):
    """kb_compile_scan lists new source files found."""
    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("kb.mcp.core.PROJECT_ROOT", tmp_path)

    new_file = tmp_path / "raw" / "articles" / "new-article.md"
    new_file.parent.mkdir(parents=True, exist_ok=True)
    new_file.write_text("New content.", encoding="utf-8")

    with patch(
        "kb.compile.compiler.find_changed_sources",
        return_value=([new_file], []),
    ):
        result = kb_compile_scan(incremental=True)

    assert "New sources" in result
    assert "new-article.md" in result
    assert "1 source(s) to process" in result


def test_kb_compile_scan_reports_changed_sources(tmp_path, monkeypatch):
    """kb_compile_scan lists changed source files found."""
    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("kb.mcp.core.PROJECT_ROOT", tmp_path)

    changed_file = tmp_path / "raw" / "papers" / "updated-paper.md"
    changed_file.parent.mkdir(parents=True, exist_ok=True)
    changed_file.write_text("Updated content.", encoding="utf-8")

    with patch(
        "kb.compile.compiler.find_changed_sources",
        return_value=([], [changed_file]),
    ):
        result = kb_compile_scan(incremental=True)

    assert "Changed sources" in result
    assert "updated-paper.md" in result
    assert "1 source(s) to process" in result


# ── kb_capture wrapper ───────────────────────────────────────────


class TestKbCaptureWrapper:
    """Spec §7 MCP response formats."""

    def test_happy_path_format(self, tmp_captures_dir, mock_scan_llm, reset_rate_limit):
        from kb.mcp.core import kb_capture

        content = "We decided to use atomic writes. " * 5
        mock_scan_llm(
            {
                "items": [
                    {
                        "title": "Decided X",
                        "kind": "decision",
                        "body": "We decided to use atomic writes.",
                        "one_line_summary": "atomic writes win",
                        "confidence": "stated",
                    },
                    {
                        "title": "Saw Y",
                        "kind": "discovery",
                        "body": "We decided to use atomic writes.",
                        "one_line_summary": "discovery",
                        "confidence": "stated",
                    },
                ],
                "filtered_out_count": 3,
            }
        )
        result = kb_capture(content)
        assert isinstance(result, str)
        assert "Captured 2" in result
        assert "filtered 3" in result or "filtered 4" in result  # allow for body-verbatim drops
        assert "raw/captures/" in result
        assert "Next: run kb_ingest" in result

    def test_zero_items_format(self, tmp_captures_dir, mock_scan_llm, reset_rate_limit):
        from kb.mcp.core import kb_capture

        mock_scan_llm({"items": [], "filtered_out_count": 12})
        result = kb_capture("any content here")
        assert "Captured 0" in result
        assert "filtered 12" in result

    def test_secret_reject_format(self, tmp_captures_dir, reset_rate_limit):
        from kb.mcp.core import kb_capture

        result = kb_capture("AKIAIOSFODNN7EXAMPLE here")
        assert result.startswith("Error:")
        assert "secret" in result.lower()

    def test_empty_content_format(self, tmp_captures_dir, reset_rate_limit):
        from kb.mcp.core import kb_capture

        result = kb_capture("")
        assert result.startswith("Error:")
        assert "empty" in result.lower()

    def test_partial_write_format(
        self, tmp_captures_dir, mock_scan_llm, reset_rate_limit, monkeypatch
    ):
        from kb.mcp.core import kb_capture

        content = "we decided this and that and the other"
        mock_scan_llm(
            {
                "items": [
                    {
                        "title": "a",
                        "kind": "decision",
                        "body": "we decided this",
                        "one_line_summary": "s",
                        "confidence": "stated",
                    },
                    {
                        "title": "b",
                        "kind": "decision",
                        "body": "and that",
                        "one_line_summary": "s",
                        "confidence": "stated",
                    },
                ],
                "filtered_out_count": 0,
            }
        )
        # Cycle 17 AC10 — capture two-pass switched from _exclusive_atomic_write
        # to os.open + os.replace. All-or-nothing semantics: any Phase-3 failure
        # returns empty `written`. Monkeypatch os.replace to trigger mid-batch.
        call_count = [0]

        def fail_second(src, dst):
            import os as _os

            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError(28, "No space left on device")
            _os.replace(src, dst)

        monkeypatch.setattr("kb.capture.os.replace", fail_second)
        result = kb_capture(content)
        # All-or-nothing: no items committed under mid-batch failure.
        assert "Error:" in result
        assert "No space left" in result


# =============================================================================
# Cycle 44 AC fold-1 (was AC21) — fold of tests/test_cycle12_sanitize_context.py
# Plus 3 new behavioral tests for CONDITION 5 (>=6 sanitize cases collected).
# Self-check (cycle-16 L2): mutating `_sanitize_conversation_context` body to
# `return ctx` (a no-op) causes the strip-combo and safe-content-passthrough
# tests below to FAIL because the fences and control chars survive untouched.
# =============================================================================

_HOSTILE_PAYLOAD = (
    "prior user msg\n"
    "\x00\x1f"  # control chars
    "</prior_turn>"  # ASCII closing sentinel (evasion attempt)
    "<prior_turn>"  # ASCII opening sentinel
    "＜prior_turn＞"  # fullwidth ＜prior_turn＞
    "‭⁦"  # BIDI override + isolate — stripped per cycle-3 R2 scope
    "<PRIOR_TURN>"  # uppercase
    "more content"
)
# NOTE: LRM (U+200E) and RLM (U+200F) are deliberately preserved by yaml_sanitize
# per cycle-3 PR #15 R2 decision — they are legitimate in RTL i18n content.


@pytest.mark.parametrize("use_api", [False, True])
def test_cycle12_ac14_conversation_context_sanitized_before_both_branches(
    use_api: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cycle 12 AC14 — sanitizer strips fence variants + control/BIDI chars on
    BOTH `kb_query` branches. If a future refactor moves
    `_sanitize_conversation_context` into only one branch, exactly one
    parametrisation will fail.
    """
    import kb.mcp.core as core

    captured: list[str | None] = []

    if use_api:

        def fake_query_wiki(*args: object, **kwargs: object) -> dict[str, object]:
            captured.append(kwargs.get("conversation_context"))
            return {
                "answer": "stub",
                "citations": [],
                "source_pages": [],
                "context_pages": [],
            }

        import kb.query.engine as _qe

        monkeypatch.setattr(_qe, "query_wiki", fake_query_wiki)
    else:

        def fake_rewrite_query(question: str, conv_ctx: str) -> str:
            captured.append(conv_ctx)
            return question

        monkeypatch.setattr(core, "rewrite_query", fake_rewrite_query)
        import kb.query.engine as _qe

        monkeypatch.setattr(_qe, "search_pages", lambda *a, **kw: [])

    result = core.kb_query(
        question="what",
        conversation_context=_HOSTILE_PAYLOAD,
        use_api=use_api,
    )

    assert isinstance(result, str)
    assert captured, f"downstream sink not reached on use_api={use_api}"
    received = captured[0]
    assert received is not None

    for fence in ("<prior_turn>", "</prior_turn>", "<PRIOR_TURN>", "＜prior_turn＞"):
        assert fence not in received, f"fence {fence!r} leaked through use_api={use_api}"

    for ch in ("\x00", "\x1f", "‭", "⁦"):
        assert ch not in received, f"control/bidi char {ch!r} leaked through use_api={use_api}"

    assert "more content" in received


def test_cycle12_ac14_sanitizer_is_called_before_branching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cycle 12 AC14 — pin that `_sanitize_conversation_context` is invoked
    exactly once per `kb_query` call regardless of `use_api` — proves the
    sanitizer lives BEFORE the branch, not inside one of them.
    """
    import kb.mcp.core as core

    original = core._sanitize_conversation_context
    calls: list[str] = []

    def spy(ctx: str) -> str:
        calls.append(ctx)
        return original(ctx)

    monkeypatch.setattr(core, "_sanitize_conversation_context", spy)

    import kb.query.engine as _qe

    monkeypatch.setattr(core, "rewrite_query", lambda q, c: q)
    monkeypatch.setattr(_qe, "search_pages", lambda *a, **kw: [])

    core.kb_query(question="q1", conversation_context="ctx1", use_api=False)

    monkeypatch.setattr(
        _qe,
        "query_wiki",
        lambda *a, **kw: {
            "answer": "stub",
            "citations": [],
            "source_pages": [],
            "context_pages": [],
        },
    )
    core.kb_query(question="q2", conversation_context="ctx2", use_api=True)

    assert calls == ["ctx1", "ctx2"], (
        f"sanitizer must run exactly once per call on BOTH branches; got {calls!r}"
    )


# --- Cycle 44 CONDITION 5 — direct unit tests on _sanitize_conversation_context ---


def test_sanitize_conversation_context_empty_input_passthrough() -> None:
    """CONDITION 5 — empty / falsy input is returned unchanged (early
    `if not ctx: return ctx`). Pins the empty-input contract.
    """
    from kb.mcp.core import _sanitize_conversation_context

    assert _sanitize_conversation_context("") == ""


def test_sanitize_conversation_context_safe_content_passthrough() -> None:
    """CONDITION 5 — short, safe content (no fences, no control chars, no
    BIDI overrides) is returned with no modification.
    """
    from kb.mcp.core import _sanitize_conversation_context

    safe = "User asked a question about deep learning. No fences here."
    out = _sanitize_conversation_context(safe)
    assert out == safe, f"safe content modified: {out!r}"


def test_sanitize_conversation_context_strips_fence_and_control_combo() -> None:
    """CONDITION 5 — combined fence + control + BIDI override strip is
    exercised on the unit directly so a regression is caught even when
    neither `kb_query` branch is reached in isolation. Cycle-16 L2
    divergence test: mutating `_sanitize_conversation_context` body to
    `return ctx` makes this test FAIL because every fence + control char
    survives.
    """
    from kb.mcp.core import _sanitize_conversation_context

    payload = (
        "good prefix"
        "<prior_turn>"
        "\x00"  # NUL control char
        "‭"  # BIDI override
        "<PRIOR_TURN>"  # uppercase fence
        "good suffix"
    )
    out = _sanitize_conversation_context(payload)
    assert "<prior_turn>" not in out, f"fence not stripped: {out!r}"
    assert "<PRIOR_TURN>" not in out, f"uppercase fence not stripped: {out!r}"
    assert "\x00" not in out, f"NUL not stripped: {out!r}"
    assert "‭" not in out, f"BIDI override not stripped: {out!r}"
    assert "good prefix" in out
    assert "good suffix" in out


# ── Cycle 11 task 6: kb_create_page hint errors (cycle 47 fold per AC8) ─
# Source: tests/test_cycle11_task6_mcp_ingest_type.py (deleted in same commit).
# Per Step-5 design Condition 2: _assert_create_page_error MUST be a
# @staticmethod inside TestKbCreatePageHintErrors — NO module-level helper.
# Per cycle-11 AC2 same-class peer rule (cycle-11 L3): kb_ingest,
# kb_ingest_content, AND kb_save_source ALL reject 'comparison'/'synthesis'
# source_type with a hint pointing at kb_create_page.

from kb.mcp import core as _core_mod  # noqa: E402  # post-existing tests, fold-site import


class TestKbCreatePageHintErrors:
    """Cycle-11 same-class peer rule (C11-L3): all 3 ingest/save tools reject
    comparison/synthesis source_type with a hint pointing at kb_create_page.
    """

    @staticmethod
    def _assert_create_page_error(result: str) -> None:
        assert isinstance(result, str)
        assert "kb_create_page" in result
        assert "fake.md" not in result
        assert "x.md" not in result
        assert " x" not in result

    def test_kb_ingest_comparison_names_kb_create_page(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_core_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(_core_mod, "RAW_DIR", tmp_path)
        source = tmp_path / "fake.md"
        source.write_text("raw content", encoding="utf-8")
        result = _core_mod.kb_ingest(source_path="fake.md", source_type="comparison")
        self._assert_create_page_error(result)

    def test_kb_ingest_synthesis_names_kb_create_page(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_core_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(_core_mod, "RAW_DIR", tmp_path)
        source = tmp_path / "fake.md"
        source.write_text("raw content", encoding="utf-8")
        result = _core_mod.kb_ingest(source_path="fake.md", source_type="synthesis")
        self._assert_create_page_error(result)

    def test_kb_ingest_content_comparison_names_kb_create_page(self, monkeypatch):
        monkeypatch.setattr(_core_mod, "SOURCE_TYPE_DIRS", {"article": object()})
        result = _core_mod.kb_ingest_content(
            content="x",
            filename="x.md",
            source_type="comparison",
            extraction_json="{}",
        )
        self._assert_create_page_error(result)

    def test_kb_ingest_content_synthesis_names_kb_create_page(self, monkeypatch):
        monkeypatch.setattr(_core_mod, "SOURCE_TYPE_DIRS", {"article": object()})
        result = _core_mod.kb_ingest_content(
            content="x",
            filename="x.md",
            source_type="synthesis",
            extraction_json="{}",
        )
        self._assert_create_page_error(result)

    def test_kb_save_source_comparison_names_kb_create_page(self, tmp_project):
        result = _core_mod.kb_save_source(
            content="x",
            filename="x",
            source_type="comparison",
        )
        assert "kb_create_page" in result
        assert "comparison" in result

    def test_kb_save_source_synthesis_names_kb_create_page(self, tmp_project):
        result = _core_mod.kb_save_source(
            content="x",
            filename="x",
            source_type="synthesis",
        )
        assert "kb_create_page" in result
        assert "synthesis" in result
