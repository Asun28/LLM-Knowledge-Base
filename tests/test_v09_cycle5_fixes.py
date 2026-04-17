"""Cycle 5 mechanical regression tests."""


def test_config_exports_verdict_validation_constants():
    from kb.config import VALID_SEVERITIES, VALID_VERDICT_TYPES

    assert VALID_SEVERITIES == ("error", "warning", "info")
    assert VALID_VERDICT_TYPES == (
        "fidelity",
        "consistency",
        "completeness",
        "review",
        "augment",
    )


def test_wrap_purpose_adds_sentinel_and_caps_content():
    from kb.utils.text import wrap_purpose

    wrapped = wrap_purpose("x" * 5000)

    assert "<kb_purpose>" in wrapped
    assert "</kb_purpose>" in wrapped
    inner = wrapped.split("<kb_purpose>\n", 1)[1].split("\n</kb_purpose>", 1)[0]
    assert len(inner) <= 4096


def test_wrap_purpose_empty_input_returns_empty_string():
    from kb.utils.text import wrap_purpose

    assert wrap_purpose("") == ""
    assert wrap_purpose("   ") == ""


def test_load_verdicts_returns_empty_when_read_text_raises_oserror(tmp_path, monkeypatch):
    from pathlib import Path

    from kb.lint.verdicts import load_verdicts

    verdicts_path = tmp_path / "lint_verdicts.json"
    verdicts_path.write_text("[]", encoding="utf-8")

    def raise_oserror(self, *args, **kwargs):
        if self == verdicts_path:
            raise OSError("read failed")
        return original_read_text(self, *args, **kwargs)

    original_read_text = Path.read_text
    monkeypatch.setattr(Path, "read_text", raise_oserror)

    assert load_verdicts(verdicts_path) == []


def test_query_wiki_wraps_and_caps_purpose(monkeypatch, tmp_path):
    from kb.query import engine

    captured = {}
    page = {
        "id": "concepts/rag",
        "title": "RAG",
        "type": "concept",
        "confidence": "stated",
        "content": "RAG content.",
    }

    monkeypatch.setattr(engine, "search_pages", lambda *args, **kwargs: [page])
    monkeypatch.setattr(engine, "load_purpose", lambda wiki_dir: "x" * 5000)

    def fake_call_llm(prompt, *args, **kwargs):
        captured["prompt"] = prompt
        return "RAG answer [source: concepts/rag]"

    monkeypatch.setattr(engine, "call_llm", fake_call_llm)

    result = engine.query_wiki("What is RAG?", wiki_dir=tmp_path)

    assert result["answer"] == "RAG answer [source: concepts/rag]"
    prompt = captured["prompt"]
    assert "<kb_purpose>" in prompt
    inner = prompt.split("<kb_purpose>\n", 1)[1].split("\n</kb_purpose>", 1)[0]
    assert len(inner) <= 4096


def test_build_extraction_prompt_wraps_and_caps_purpose():
    from kb.ingest.extractors import build_extraction_prompt

    template = {"extract": ["summary"], "name": "article", "description": "Article"}

    prompt = build_extraction_prompt("content", template, purpose="x" * 5000)

    assert "<kb_purpose>" in prompt
    inner = prompt.split("<kb_purpose>\n", 1)[1].split("\n</kb_purpose>", 1)[0]
    assert len(inner) <= 4096


def test_extract_entity_context_matches_entity_word_boundaries():
    from kb.ingest.pipeline import _extract_entity_context

    no_match = _extract_entity_context(
        "Ray",
        {
            "description": "A stray cat found an array.",
            "key_claims": ["The stray cat hid under an array."],
        },
    )
    match = _extract_entity_context(
        "Python",
        {
            "description": "Python is great.",
            "key_claims": ["Python is widely used."],
        },
    )

    assert no_match == ""
    assert "Python is great." in match


def test_kb_query_claude_code_instructions_use_wikilinks(monkeypatch):
    from kb.mcp import core

    page = {
        "id": "concepts/rag",
        "title": "RAG",
        "type": "concept",
        "confidence": "stated",
        "score": 1.0,
        "content": "RAG content.",
    }
    monkeypatch.setattr(core, "search_pages", lambda *args, **kwargs: [page])
    monkeypatch.setattr(core, "compute_trust_scores", lambda: {})

    output = core.kb_query("What is RAG?")

    assert "[[" in output
    assert "[source:" not in output


def test_kb_save_source_escapes_source_type_in_hint(monkeypatch, tmp_path):
    from kb.mcp import core

    source_type = 'article" injected: true'
    monkeypatch.setitem(core.SOURCE_TYPE_DIRS, source_type, tmp_path)

    output = core.kb_save_source("content", "sample", source_type=source_type)

    assert '"article\\" injected: true"' in output


def test_validate_page_id_rejects_control_chars_and_accepts_valid_id():
    from kb.mcp.app import _validate_page_id

    assert _validate_page_id("\x00foo") == "page_id contains control characters."
    assert _validate_page_id("concepts/rag", check_exists=False) is None


def test_cli_configures_logging_when_root_has_no_handlers(monkeypatch):
    import logging

    from kb import cli as cli_module

    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])

    cli_module.cli.callback()

    assert root.handlers


def test_mcp_server_main_configures_logging_when_root_has_no_handlers(monkeypatch):
    import logging

    from kb import mcp_server

    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(mcp_server.mcp, "run", lambda: None)

    mcp_server.main()

    assert root.handlers


def test_anthropic_client_sets_package_user_agent(monkeypatch):
    from kb.utils import llm

    captured = {}

    class FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm.anthropic, "Anthropic", FakeAnthropic)

    llm.get_client()

    assert captured["default_headers"]["User-Agent"].startswith("llm-wiki-flywheel/")
