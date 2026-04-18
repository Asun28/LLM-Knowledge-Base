"""Cycle 8 contradiction persistence idempotency coverage."""

from __future__ import annotations

import logging
from datetime import date

from kb.ingest.pipeline import _persist_contradictions


def test_same_day_reingest_skips_identical_contradiction_block(tmp_path, caplog):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    contradictions = [{"claim": "Alpha contradicts beta."}]

    _persist_contradictions(contradictions, "raw/articles/source.md", wiki_dir)
    with caplog.at_level(logging.DEBUG, logger="kb.ingest.pipeline"):
        _persist_contradictions(contradictions, "raw/articles/source.md", wiki_dir)

    content = (wiki_dir / "contradictions.md").read_text(encoding="utf-8")
    header = f"## raw/articles/source.md — {date.today().isoformat()}\n"
    assert content.count(header) == 1
    assert content.count("- Alpha contradicts beta.\n") == 1
    assert any("Skipping duplicate contradiction block" in r.getMessage() for r in caplog.records)
    assert all("Alpha contradicts beta" not in r.getMessage() for r in caplog.records)


def test_same_day_same_source_with_different_claims_appends_distinct_block(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    _persist_contradictions([{"claim": "First claim."}], "raw/articles/source.md", wiki_dir)
    _persist_contradictions([{"claim": "Second claim."}], "raw/articles/source.md", wiki_dir)

    content = (wiki_dir / "contradictions.md").read_text(encoding="utf-8")
    header = f"## raw/articles/source.md — {date.today().isoformat()}\n"
    assert content.count(header) == 2
    assert "- First claim.\n" in content
    assert "- Second claim.\n" in content


def test_source_ref_header_injection_is_stripped_before_persist(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    _persist_contradictions(
        [{"claim": "Injected source ref should not create a second header."}],
        "## raw/articles/source.md\n## injected",
        wiki_dir,
    )

    content = (wiki_dir / "contradictions.md").read_text(encoding="utf-8")
    header = f"## raw/articles/source.md — {date.today().isoformat()}\n"
    assert header in content
    assert "## injected" not in content
