from pathlib import Path
from types import SimpleNamespace

from kb.config import PROJECT_ROOT
from kb.query.embeddings import _vec_db_path
from kb.query.engine import query_wiki, search_pages


def _write_page(
    path: Path,
    *,
    title: str,
    body: str,
    page_type: str = "concept",
    source: str = "raw/articles/test.md",
    updated: str = "2026-04-18",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "---\n"
            f'title: "{title}"\n'
            "source:\n"
            f'  - "{source}"\n'
            "created: 2020-01-01\n"
            f"updated: {updated}\n"
            f"type: {page_type}\n"
            "confidence: stated\n"
            "---\n\n"
            f"{body}\n"
        ),
        encoding="utf-8",
    )


def test_search_pages_uses_override_vector_db(tmp_project, monkeypatch):
    """AC1 R1 M2: verify search_pages calls get_vector_index against the
    wiki_dir-derived vec_db path, never a PROJECT_ROOT-derived one.

    The previous version of this test gated its assertions behind
    `if calls:` — but `vector_search()` short-circuits on
    `if not vec_path.exists()` before ever calling `get_vector_index`, so
    `calls` was always empty on main and the test passed vacuously. The
    fix: seed a placeholder DB at the EXPECTED override path (derived
    from wiki_dir via `_vec_db_path`), so `vec_path.exists()` is True and
    the spy fires. The spy itself never opens the DB — `get_vector_index`
    is fully monkeypatched — so a zero-byte placeholder is sufficient.
    """
    wiki_dir = tmp_project / "wiki"
    _write_page(wiki_dir / "concepts" / "foo.md", title="Foo", body="test foo")

    fake_project = tmp_project / "poison_project"
    poison_db = fake_project / ".data" / "vector_index.db"
    poison_db.parent.mkdir(parents=True)
    poison_db.write_bytes(b"poison")
    expected_vec_path = _vec_db_path(wiki_dir)

    # Seed the placeholder vec_db at the expected override path so
    # vector_search's vec_path.exists() gate lets get_vector_index run.
    # Use the SQLite magic header — harmless if the spy opens the file,
    # and makes intent obvious vs a bare empty byte string.
    expected_vec_path.parent.mkdir(parents=True, exist_ok=True)
    expected_vec_path.write_bytes(b"SQLite format 3\x00")

    from kb.query import embeddings, engine

    calls = []

    def spy(vec_path):
        calls.append(Path(vec_path))
        return SimpleNamespace(query=lambda _vec, limit: [("concepts/foo", 0.1)])

    monkeypatch.setattr(engine, "PROJECT_ROOT", fake_project)
    monkeypatch.setattr(embeddings, "embed_texts", lambda _texts: [[0.1, 0.2]])
    monkeypatch.setattr(embeddings, "get_vector_index", spy)

    results = search_pages("test", wiki_dir=wiki_dir)

    # AC1 assertions are now unconditional — the guard-gate `if calls:`
    # was the loophole that let the test pass vacuously on main.
    assert results
    assert len(calls) >= 1, "get_vector_index should be called when vec_db exists"
    called_path = calls[0]
    assert called_path == expected_vec_path, f"Expected {expected_vec_path}, got {called_path}"
    # Defense-in-depth: poison path (PROJECT_ROOT-derived) MUST NOT appear.
    assert poison_db not in calls
    assert poison_db.resolve() not in [c.resolve() for c in calls]


def test_flag_stale_results_uses_override_project_root(tmp_project, monkeypatch):
    raw_source = tmp_project / "raw" / "articles" / "src.md"
    raw_source.write_text("recent source", encoding="utf-8")
    wiki_dir = tmp_project / "wiki"
    _write_page(
        wiki_dir / "concepts" / "foo.md",
        title="Foo",
        body="foo body",
        source="raw/articles/src.md",
        updated="2020-01-01",
    )

    from kb.query import engine

    monkeypatch.setattr(engine, "PROJECT_ROOT", tmp_project / "empty_project_root")
    results = search_pages("foo", wiki_dir=wiki_dir)

    foo = next(result for result in results if result["id"] == "concepts/foo")
    assert foo["stale"] is True


def test_query_wiki_search_mode_uses_override_vec_path(tmp_project, monkeypatch):
    wiki_dir = tmp_project / "wiki"
    _write_page(wiki_dir / "concepts" / "bar.md", title="Bar", body="bar body")
    assert not _vec_db_path(wiki_dir).exists()

    fake_project = tmp_project / "poison_project"
    poison_db = fake_project / ".data" / "vector_index.db"
    poison_db.parent.mkdir(parents=True)
    poison_db.write_bytes(b"poison")

    from kb.query import embeddings, engine

    monkeypatch.setattr(engine, "PROJECT_ROOT", fake_project)
    monkeypatch.setattr(embeddings, "_hybrid_available", True)
    monkeypatch.setattr(embeddings, "embed_texts", lambda _texts: [[0.1, 0.2]])
    monkeypatch.setattr(
        embeddings,
        "get_vector_index",
        lambda _path: SimpleNamespace(query=lambda _vec, limit: [("concepts/bar", 0.1)]),
    )
    monkeypatch.setattr(engine, "call_llm", lambda *_args, **_kwargs: "answer")

    result = query_wiki("bar", wiki_dir=wiki_dir)

    assert result["search_mode"] == "bm25_only"


def test_query_wiki_raw_fallback_uses_override_raw_dir(tmp_project, monkeypatch):
    marker = "UNIQUE-TMP-MARKER-Z9"
    wiki_dir = tmp_project / "wiki"
    raw_file = tmp_project / "raw" / "articles" / "leak.md"
    raw_file.write_text(f"# Leak\n{marker}\n", encoding="utf-8")
    _write_page(
        wiki_dir / "summaries" / "stub.md",
        title="Stub",
        body=f"summary stub {marker}",
        page_type="summary",
        source="raw/articles/leak.md",
    )

    from kb.query import engine

    prompts = []
    raw_calls = []
    real_search_raw_sources = engine.search_raw_sources

    def fake_call_llm(prompt, **_kwargs):
        prompts.append(prompt)
        return "answer [ref: raw/articles/leak.md]"

    def spy_search_raw_sources(question, raw_dir=None, max_results=5):
        raw_calls.append(raw_dir)
        return real_search_raw_sources(question, raw_dir=raw_dir, max_results=max_results)

    monkeypatch.setattr(engine, "call_llm", fake_call_llm)
    monkeypatch.setattr(engine, "PROJECT_ROOT", tmp_project / "empty_project_root")
    monkeypatch.setattr(engine, "search_raw_sources", spy_search_raw_sources)

    result = query_wiki(marker, wiki_dir=wiki_dir)

    assert raw_calls
    assert all(Path(raw_dir).resolve() == (tmp_project / "raw").resolve() for raw_dir in raw_calls)
    assert prompts
    assert str(raw_file) not in prompts[0]
    assert "--- Raw Source: raw/articles/leak.md (verbatim) ---" in prompts[0]
    assert marker in prompts[0]
    assert any(
        citation["type"] == "raw" and citation["path"] == "raw/articles/leak.md"
        for citation in result["citations"]
    )
    real_raw_dir = PROJECT_ROOT / "raw" / "articles"
    real_raw_paths = [str(path) for path in real_raw_dir.glob("*.md")]
    citation_paths = [citation["path"] for citation in result["citations"]]
    assert all(real_path not in citation_paths for real_path in real_raw_paths)
