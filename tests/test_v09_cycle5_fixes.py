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
