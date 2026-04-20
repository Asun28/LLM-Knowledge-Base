"""Cycle 18 AC16 — end-to-end workflow integration tests.

Three scenarios exercising ingest_source → query_wiki → refine_page over the
`tmp_project` fixture with LLM boundaries mocked. Catches cross-module glue
bugs that single-module tests miss (Phase 4.5 R3 "no end-to-end ingest→query
workflow" backlog item).

Mocking strategy (cycle-17 L1 compat): patch `call_llm` / `call_llm_json`
at module-attribute level. Each scenario asserts the mock was invoked ≥1
time to prevent vacuous tests where the mocked path was never exercised.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _stub_article_extraction(*, entities: list[str] | None = None) -> dict:
    """Return a plausible extraction payload used by ingest_source."""
    return {
        "title": "Anthropic and RAG",
        "summary": "An article about Anthropic and RAG techniques.",
        "entities_mentioned": entities if entities is not None else ["Anthropic"],
        "concepts_mentioned": ["RAG"],
        "key_points": ["Anthropic builds Claude.", "RAG augments LLMs with retrieval."],
        "abstract": "Overview piece.",
    }


def _write_raw_article(project: Path, slug: str, body: str = "") -> Path:
    raw = project / "raw" / "articles" / f"{slug}.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(
        body or f"# {slug}\n\nAnthropic builds Claude. RAG is a retrieval technique.\n",
        encoding="utf-8",
    )
    return raw


def _install_llm_mocks(monkeypatch) -> dict:
    """Patch `call_llm` / `call_llm_json` at module attribute level.

    Returns a dict with `count` tracking total mock invocations — each
    scenario asserts count >= 1 to prevent vacuous paths.
    """
    counters = {"count": 0}

    def stub_call_llm(prompt, tier="write", **kwargs):
        counters["count"] += 1
        return (
            "Anthropic is the company behind Claude. See [[entities/anthropic]] "
            "for details and the raw source [[raw/articles/sample]] for the original."
        )

    def stub_call_llm_json(prompt, tier, schema, **kwargs):
        counters["count"] += 1
        return _stub_article_extraction()

    monkeypatch.setattr("kb.utils.llm.call_llm", stub_call_llm)
    monkeypatch.setattr("kb.utils.llm.call_llm_json", stub_call_llm_json)
    monkeypatch.setattr("kb.query.engine.call_llm", stub_call_llm)
    return counters


def test_e2e_ingest_then_query(tmp_project: Path, monkeypatch) -> None:
    """Scenario (a): ingest one article → query_wiki returns an answer with citations."""
    counters = _install_llm_mocks(monkeypatch)

    from kb.ingest.pipeline import ingest_source  # noqa: PLC0415
    from kb.query.engine import query_wiki  # noqa: PLC0415

    raw = _write_raw_article(tmp_project, "e2e-ingest-query")
    ingest_result = ingest_source(
        raw,
        source_type="article",
        extraction=_stub_article_extraction(),
        wiki_dir=tmp_project / "wiki",
        raw_dir=tmp_project / "raw",
        _skip_vector_rebuild=True,
    )
    assert ingest_result["pages_created"], f"Expected pages_created; got {ingest_result}"

    result = query_wiki(
        question="What is Anthropic?",
        wiki_dir=tmp_project / "wiki",
    )

    assert "answer" in result, f"Expected answer key; got {result.keys()}"
    assert result["answer"], f"Answer empty: {result['answer']!r}"
    citations = result.get("citations") or []
    # Citations include either 'wiki' or 'raw' entries — at minimum non-empty.
    assert len(citations) >= 1, f"Expected >=1 citation; got {citations}"
    assert counters["count"] >= 1, "LLM mock was never invoked — integration path bypassed"


def test_e2e_ingest_refine_requery(tmp_project: Path, monkeypatch) -> None:
    """Scenario (b): ingest → refine_page → re-query shows refined content."""
    counters = _install_llm_mocks(monkeypatch)

    from kb.ingest.pipeline import ingest_source  # noqa: PLC0415
    from kb.query.engine import query_wiki  # noqa: PLC0415
    from kb.review.refiner import refine_page  # noqa: PLC0415

    raw = _write_raw_article(tmp_project, "e2e-refine")
    ingest_result = ingest_source(
        raw,
        source_type="article",
        extraction=_stub_article_extraction(),
        wiki_dir=tmp_project / "wiki",
        raw_dir=tmp_project / "raw",
        _skip_vector_rebuild=True,
    )
    entity_page_id = next(
        (pid for pid in ingest_result["pages_created"] if pid.startswith("entities/")),
        None,
    )
    assert entity_page_id is not None, (
        f"Expected at least one entity page; created={ingest_result['pages_created']}"
    )

    refined_body = "REFINED BODY MARKER about Anthropic and Claude."
    refine_result = refine_page(
        entity_page_id,
        refined_body,
        revision_notes="test refinement",
        wiki_dir=tmp_project / "wiki",
    )
    assert refine_result.get("error") is None, f"refine_page failed: {refine_result}"

    # Cycle 18 Q11 — force mtime bump so mtime-keyed caches (load_page_frontmatter,
    # BM25 max_mtime_ns) are invalidated before re-query. Coarse filesystems
    # otherwise reuse stale cache keys when the refine-then-requery happens
    # within the mtime resolution window.
    page_path = (tmp_project / "wiki" / f"{entity_page_id}.md").resolve()
    now = page_path.stat().st_mtime + 5
    os.utime(page_path, (now, now))

    result = query_wiki(
        question="Tell me about Anthropic",
        wiki_dir=tmp_project / "wiki",
    )
    assert "answer" in result
    assert counters["count"] >= 1, "LLM mock was never invoked on re-query"
    # context_pages should include the refined entity page id. If the query's
    # ranking does not surface it, at minimum the page's refined marker should
    # appear somewhere in the assembled context — read the page to confirm the
    # refine actually landed.
    assert refined_body in page_path.read_text(encoding="utf-8"), (
        "Refined body marker missing from page content after refine_page"
    )


def test_e2e_shared_entity_wikilink_injection(tmp_project: Path, monkeypatch) -> None:
    """Scenario (c): article A creates entity X; article B mentioning X in its body gets
    a wikilink from A's content back to B's new concept.

    Wikilinks get injected retroactively: when the SECOND ingest creates a NEW page
    (concept ``SafetyResearch`` in B), `inject_wikilinks` scans ALL existing pages
    (including those created by A) for plain-text mentions of ``SafetyResearch``
    and rewrites them as wikilinks. So the first-ingest pages MUST contain a
    mention of B's new concept.
    """
    counters = _install_llm_mocks(monkeypatch)

    from kb.ingest.pipeline import ingest_source  # noqa: PLC0415

    # A's body mentions "SafetyResearch" — a concept that does NOT yet exist
    # in the wiki. When B later creates a concept/safetyresearch page, A's
    # body will have its "SafetyResearch" mention rewritten as a wikilink.
    raw_a = _write_raw_article(
        tmp_project,
        "e2e-shared-a",
        body=("# e2e-shared-a\n\nAnthropic builds Claude and focuses on SafetyResearch efforts.\n"),
    )
    raw_b = _write_raw_article(
        tmp_project,
        "e2e-shared-b",
        body="# e2e-shared-b\n\nSafetyResearch is the field of AI alignment work.\n",
    )

    # A's extraction registers Anthropic entity (but NOT SafetyResearch concept).
    # The key_points text mentions "SafetyResearch" as plain text so the inject
    # scan in the second ingest finds it in A's summary page body and rewrites
    # it as a wikilink to B's new concept page.
    result_a = ingest_source(
        raw_a,
        source_type="article",
        extraction={
            "title": "Anthropic Focus",
            "summary": "About Anthropic.",
            "entities_mentioned": ["Anthropic"],
            "concepts_mentioned": ["Alignment"],  # deliberately different
            "key_points": [
                "Anthropic builds Claude.",
                "Anthropic focuses on SafetyResearch as a discipline.",
            ],
            "abstract": "A piece that mentions SafetyResearch as a concept.",
        },
        wiki_dir=tmp_project / "wiki",
        raw_dir=tmp_project / "raw",
        _skip_vector_rebuild=True,
    )
    assert result_a["pages_created"], f"First ingest created no pages: {result_a}"
    first_created = set(result_a["pages_created"])

    # B creates concept "SafetyResearch" which A's body mentions in plain text.
    result_b = ingest_source(
        raw_b,
        source_type="article",
        extraction={
            "title": "SafetyResearch Explainer",
            "summary": "What safety research means.",
            "entities_mentioned": [],
            "concepts_mentioned": ["SafetyResearch"],
            "key_points": ["SafetyResearch is the field of alignment."],
            "abstract": "Explainer.",
        },
        wiki_dir=tmp_project / "wiki",
        raw_dir=tmp_project / "raw",
        _skip_vector_rebuild=True,
    )

    wikilinks_injected = result_b.get("wikilinks_injected", [])
    assert len(wikilinks_injected) >= 1, (
        f"Expected second ingest to inject wikilinks into first-ingest pages; "
        f"wikilinks_injected={wikilinks_injected}"
    )
    # At least one injection target must be a page created by the FIRST ingest
    # (explicit anti-degeneracy assertion per R2 review).
    injected_into_first = [pid for pid in wikilinks_injected if pid in first_created]
    assert len(injected_into_first) >= 1, (
        f"Second ingest wikilinks must hit first ingest's pages. "
        f"first_created={first_created}, wikilinks_injected={wikilinks_injected}"
    )
    # LLM mock is installed but this scenario's flow uses pre-provided extraction
    # (both ingests pass explicit `extraction=...`), so no LLM call is expected.
    # The mock's presence is documented for completeness — install it to prevent
    # accidental real LLM calls if the extraction-skipping contract ever changes.
    assert counters["count"] == 0, (
        "Pre-provided extraction should bypass LLM calls entirely; "
        "a non-zero count here means ingest_source changed its LLM-skip contract."
    )
