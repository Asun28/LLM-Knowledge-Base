"""Regression tests for query-engine raw_dir sandboxing."""

from pathlib import Path

from kb.query.engine import query_wiki


def test_query_raw_fallback_respects_wiki_dir_sandbox(tmp_project, monkeypatch):
    """Regression: Phase 4.5 CRITICAL item 7.

    query_wiki ignored wiki_dir for search_raw_sources.
    """
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    (raw_dir / "articles").mkdir(parents=True, exist_ok=True)
    (raw_dir / "articles" / "sandbox-marker.md").write_text(
        "# Sandbox\nUnique marker token zqxv42.\n", encoding="utf-8"
    )

    from kb.query import engine as eng

    calls = []
    real_fn = eng.search_raw_sources

    def spy(question, raw_dir=None, max_results=5):
        calls.append(raw_dir)
        return real_fn(question, raw_dir=raw_dir, max_results=max_results)

    monkeypatch.setattr(eng, "search_raw_sources", spy)
    # Stub out LLM so the test doesn't require an API key
    monkeypatch.setattr(eng, "call_llm", lambda prompt, **kw: "synthesized answer")

    (wiki_dir / "concepts").mkdir(parents=True, exist_ok=True)
    fm = (
        "---\ntitle: Dummy\nsource: []\ntype: concept\n"
        "confidence: stated\ncreated: 2026-04-15\nupdated: 2026-04-15\n"
        "---\n\nbody zqxv42\n"
    )
    (wiki_dir / "concepts" / "dummy.md").write_text(fm, encoding="utf-8")

    _ = query_wiki("zqxv42", wiki_dir=wiki_dir)
    assert calls, "search_raw_sources was never invoked"
    for received in calls:
        assert received is not None, "raw_dir not threaded through"
        assert Path(received).resolve() == raw_dir.resolve(), (
            f"raw_dir leaked to {received}, expected sandbox {raw_dir}"
        )
