"""Cycle 23 AC6 — hermetic end-to-end ingest → query → lint workflow.

Phase 4.5 HIGH (Step 4 plan AC6). Drives the five-operation pipeline end-
to-end against a ``tmp_project`` fixture with only the *synthesis* LLM
call stubbed — the ingest path runs with an explicit ``extraction=dict``
so ``kb.ingest.extractors.call_llm_json`` is never invoked, and the
vector-index + embedding model loads are monkeypatched to no-ops so
this test stays hermetic on cold CI runners.

Covers integration gaps that single-module unit tests miss: page write
→ wikilink-injection interaction, source-merge on shared entity pages,
lint reading the wiki just-written by ingest, query synthesis reading
the wiki + returning citation shapes that match the lint contract.
"""

from __future__ import annotations

from pathlib import Path


def _ensure_vector_stubs(monkeypatch) -> None:
    """Skip embedding model / vector index work (cycle 23 Q12)."""
    monkeypatch.setattr("kb.query.embeddings.rebuild_vector_index", lambda *a, **kw: False)

    def _no_model():  # pragma: no cover — stubbed
        return None

    monkeypatch.setattr("kb.query.embeddings._get_model", _no_model)


def test_ingest_query_lint_end_to_end(tmp_project: Path, monkeypatch):
    """AC6 — ingest two raw articles, query the wiki, then lint it.

    Patches ``kb.query.engine.call_llm`` to a canned answer. ``tmp_project``
    is pre-seeded with wiki/log.md + index.md by the fixture; ingest + query
    must coexist without stepping on those invariants.
    """
    _ensure_vector_stubs(monkeypatch)

    # Point kb.config globals at tmp_project so ingest's internal PROJECT_ROOT
    # checks resolve against the sandbox.
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr("kb.config.WIKI_DIR", tmp_project / "wiki")
    monkeypatch.setattr("kb.config.RAW_DIR", tmp_project / "raw")
    monkeypatch.setattr("kb.ingest.pipeline.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr("kb.ingest.pipeline.WIKI_DIR", tmp_project / "wiki")
    monkeypatch.setattr("kb.ingest.pipeline.RAW_DIR", tmp_project / "raw")

    # ── Step 1: seed two raw sources ──────────────────────────────────────
    articles_dir = tmp_project / "raw" / "articles"
    alpha_path = articles_dir / "alpha.md"
    beta_path = articles_dir / "beta.md"
    alpha_path.write_text(
        "---\ntitle: Alpha Article\n---\n\n# Alpha\n\n"
        "Alpha describes the Alpha concept and mentions Beta.\n",
        encoding="utf-8",
    )
    beta_path.write_text(
        "---\ntitle: Beta Article\n---\n\n# Beta\n\nBeta follows from Alpha.\n",
        encoding="utf-8",
    )

    # ── Step 2: ingest both with explicit extraction (no LLM) ─────────────
    from kb.ingest.pipeline import ingest_source

    wiki = tmp_project / "wiki"
    r1 = ingest_source(
        alpha_path,
        source_type="article",
        extraction={
            "title": "Alpha Article",
            "summary": "Alpha describes the Alpha concept.",
            "entities": [{"name": "Alpha", "description": "Alpha entity"}],
            "concepts": [],
            "entities_mentioned": ["Alpha"],
            "concepts_mentioned": [],
        },
        wiki_dir=wiki,
    )
    assert r1["pages_created"], f"ingest produced no pages: {r1}"

    r2 = ingest_source(
        beta_path,
        source_type="article",
        extraction={
            "title": "Beta Article",
            "summary": "Beta follows from Alpha.",
            "entities": [{"name": "Beta", "description": "Beta entity"}],
            "concepts": [],
            "entities_mentioned": ["Beta", "Alpha"],
            "concepts_mentioned": [],
        },
        wiki_dir=wiki,
    )
    # At least a Beta summary or entity page should materialise
    assert r2["pages_created"] or r2["pages_updated"], f"second ingest produced nothing: {r2}"

    # ── Step 3: query with stubbed synthesis ──────────────────────────────
    def _fake_call_llm(prompt, tier="write", **_kw):
        return (
            "Alpha and Beta are related concepts discussed across two "
            "articles. [source: raw/articles/alpha.md]"
        )

    monkeypatch.setattr("kb.query.engine.call_llm", _fake_call_llm)

    # Prevent search_pages from trying to load the real vector index
    monkeypatch.setattr("kb.query.engine._flag_stale_results", lambda results, *a, **kw: None)

    from kb.query.engine import query_wiki

    result = query_wiki("What is Alpha?", wiki_dir=wiki)
    assert "answer" in result
    # citations may be empty in the stub, but the key must exist
    assert "citations" in result
    assert isinstance(result["citations"], list)
    assert "source_pages" in result

    # ── Step 4: lint the wiki just written ────────────────────────────────
    from kb.lint.runner import run_all_checks

    report = run_all_checks(wiki_dir=wiki)
    # Report shape must include summary counts (lint contract); zero critical
    # errors should be present against a freshly-ingested two-article corpus.
    assert "summary" in report
    assert report["summary"].get("error", 0) == 0, (
        f"lint reported errors after hermetic ingest: {report['summary']}"
    )
