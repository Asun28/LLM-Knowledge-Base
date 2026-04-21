"""End-to-end smoke test for the KB five-operation pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


KARPATHY_GIST_CONTENT = """# Karpathy LLM Wiki Pattern

## Core concept

The Karpathy LLM wiki pattern treats a knowledge base as a persistent
compounding artifact rather than a disposable chat transcript. Each pass over
source material should leave behind durable pages that can be searched,
linked, linted, and evolved by later work.

## Three-layer architecture

- `raw/` stores original source material such as articles, papers, videos, and
  conversations.
- `wiki/` stores synthesized pages for entities, concepts, summaries, and
  relationships.
- `schema` keeps page shapes, extraction expectations, and validation rules
  explicit enough that agents can operate consistently.

## Five operations

1. Ingest converts raw files into durable wiki pages.
2. Compile connects pages, updates indexes, and injects wikilinks.
3. Query uses BM25 search and synthesis to answer questions with citations.
4. Lint checks health issues such as stale pages, dead links, and weak
   provenance.
5. Evolve finds gaps, suggests new pages, and identifies useful connections.

## Supporting files

Indexes, source maps, logs, manifests, feedback, and verdict histories support
the operational loop. They let an agent reason about provenance, freshness,
duplication, and improvement work without rereading every raw source.

## Rationale

The pattern has a Memex parallel: Vannevar Bush imagined durable associative
trails through knowledge. Karpathy's LLM wiki pattern updates that idea for
agents by combining files, links, search, and repeated synthesis into a
knowledge flywheel.

## Key entities

- Karpathy
- Vannevar Bush
- Memex
- BM25
- Obsidian
"""


def test_karpathy_gist_five_cycle(tmp_project: Path, monkeypatch) -> None:
    """Ingest, compile, query, lint, and evolve an isolated Karpathy gist."""
    from kb.compile.linker import inject_wikilinks_batch
    from kb.evolve.analyzer import generate_evolution_report
    from kb.ingest.pipeline import ingest_source
    from kb.lint.runner import run_all_checks
    from kb.query.engine import query_wiki
    from kb.utils.pages import load_all_pages

    raw_dir = tmp_project / "raw"
    wiki_dir = tmp_project / "wiki"
    source_path = raw_dir / "articles" / "karpathy-llm-wiki.md"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(KARPATHY_GIST_CONTENT, encoding="utf-8")

    extraction = {
        "title": "Karpathy LLM Wiki Pattern",
        "summary": (
            "A five-operation KB pattern: ingest, compile, query with BM25, "
            "lint, and evolve persistent wiki artifacts."
        ),
        "core_argument": (
            "A durable LLM wiki compounds over time through five operations: "
            "Ingest, Compile, Query, Lint, and Evolve, with BM25 search helping "
            "query the accumulated pages."
        ),
        "entities": ["Andrej Karpathy", "Vannevar Bush", "Memex"],
        "concepts": ["Compile-Not-Retrieve Pattern", "BM25 Search"],
        "entities_mentioned": ["Andrej Karpathy", "Vannevar Bush", "Memex"],
        "concepts_mentioned": ["Compile-Not-Retrieve Pattern", "BM25 Search"],
        "key_points": [
            "The KB is a persistent compounding artifact.",
            "The architecture has raw, wiki, and schema layers.",
            "The operational loop is Ingest, Compile, Query, Lint, and Evolve.",
            "BM25 supports retrieval over accumulated wiki pages.",
        ],
        "topics": ["LLM wiki", "knowledge base", "Memex", "BM25", "Obsidian"],
        "confidence": "stated",
        "source_type": "article",
    }

    # Stage 1: Ingest.
    ingest_result = ingest_source(
        source_path,
        source_type="article",
        extraction=extraction,
        wiki_dir=wiki_dir,
        raw_dir=raw_dir,
        _skip_vector_rebuild=True,
    )

    assert len(ingest_result["pages_created"]) >= 3
    assert not ingest_result.get("duplicate", False)

    # Stage 2: Compile.
    pages = load_all_pages(wiki_dir=wiki_dir)
    assert len(pages) >= 3
    assert any("karpathy-llm-wiki.md" in source for page in pages for source in page["sources"])
    for page in pages:
        assert {"title", "type", "confidence", "created", "updated"} <= page.keys()

    title_by_id = {page["id"]: page["title"] for page in pages}
    new_pages = [(title_by_id[pid], pid) for pid in ingest_result["pages_created"]]
    link_result = inject_wikilinks_batch(new_pages=new_pages, wiki_dir=wiki_dir, pages=pages)
    assert isinstance(link_result, dict)

    # Stage 3: Query.
    mocked_answer = (
        "The five operations are Ingest, Compile, Query, Lint, and Evolve. "
        "[[summaries/karpathy-llm-wiki-pattern]]"
    )

    def fake_call_llm(*_args, **_kwargs):
        return mocked_answer

    monkeypatch.setattr("kb.query.engine.call_llm", fake_call_llm)

    query_result = query_wiki(
        "What are the five operations in the Karpathy LLM wiki pattern?",
        wiki_dir=wiki_dir,
        raw_dir=raw_dir,
    )

    assert mocked_answer in query_result["answer"]
    assert isinstance(query_result["source_pages"], list)
    assert query_result["source_pages"]
    assert isinstance(query_result["citations"], list)

    # Stage 4: Lint.
    lint_report = run_all_checks(wiki_dir=wiki_dir, raw_dir=raw_dir)
    assert isinstance(lint_report, dict)
    assert lint_report["summary"].get("error", 0) == 0

    # Stage 5: Evolve.
    monkeypatch.setattr("kb.feedback.reliability.get_flagged_pages", lambda path=None: [])
    evolve_report = generate_evolution_report(wiki_dir=wiki_dir)
    assert isinstance(evolve_report, dict)
    assert "new_page_suggestions" in evolve_report or "recommendations" in evolve_report
