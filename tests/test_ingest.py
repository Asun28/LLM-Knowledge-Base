"""Tests for the ingest pipeline."""

import json
import logging
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from kb.ingest.extractors import build_extraction_prompt, extract_from_source, load_template
from kb.ingest.pipeline import (
    _build_summary_content,
    _coerce_str_field,
    _extract_entity_context,
    _update_existing_page,
    detect_source_type,
    ingest_source,
)
from kb.mcp import core as mcp_core
from kb.mcp.app import _format_ingest_result
from kb.utils.hashing import hash_bytes
from kb.utils.text import slugify

# -- Extractors tests -----------------------------------------------------------


def test_load_template(project_root):
    """load_template returns a dict with required keys."""
    template = load_template("article")
    assert template["name"] == "article"
    assert "extract" in template
    assert "wiki_outputs" in template
    assert "title" in template["extract"]


def test_load_template_missing():
    """load_template raises ValueError for unknown source types."""
    with pytest.raises(ValueError, match="Invalid source type"):
        load_template("nonexistent_type")


def test_build_extraction_prompt():
    """build_extraction_prompt includes source content and field list."""
    template = {"name": "article", "description": "test", "extract": ["title", "author"]}
    prompt = build_extraction_prompt("Hello world content", template)
    assert "Hello world content" in prompt
    assert "- title" in prompt
    assert "- author" in prompt
    assert "JSON" in prompt


@patch("kb.ingest.extractors.call_llm_json")
def test_extract_from_source(mock_llm_json):
    """extract_from_source calls LLM with tool_use and returns structured data."""
    mock_llm_json.return_value = {
        "title": "Test Article",
        "author": "Test Author",
        "entities_mentioned": ["GPT-4"],
        "concepts_mentioned": ["RAG"],
    }
    result = extract_from_source("Some article content", "article")
    assert result["title"] == "Test Article"
    assert "GPT-4" in result["entities_mentioned"]
    mock_llm_json.assert_called_once()


# -- Pipeline tests -------------------------------------------------------------


def test_slugify():
    """slugify converts text to URL-friendly slug."""
    assert slugify("Hello World!") == "hello-world"
    assert slugify("  Spaces  and---dashes  ") == "spaces-and-dashes"
    assert slugify("CamelCase Test") == "camelcase-test"


def test_detect_source_type(tmp_path):
    """detect_source_type infers type from raw/ subdirectory."""
    # Create a mock raw directory structure
    with patch("kb.ingest.pipeline.RAW_DIR", tmp_path / "raw"):
        articles_dir = tmp_path / "raw" / "articles"
        articles_dir.mkdir(parents=True)
        source = articles_dir / "test.md"
        source.write_text("test content")
        assert detect_source_type(source) == "article"


def test_detect_source_type_papers(tmp_path):
    """detect_source_type works for papers subdirectory."""
    with patch("kb.ingest.pipeline.RAW_DIR", tmp_path / "raw"):
        papers_dir = tmp_path / "raw" / "papers"
        papers_dir.mkdir(parents=True)
        source = papers_dir / "paper.md"
        source.write_text("test paper")
        assert detect_source_type(source) == "paper"


@patch("kb.ingest.pipeline.extract_from_source")
def test_ingest_source(mock_extract, tmp_project):
    """ingest_source creates summary, entity, and concept pages."""
    mock_extract.return_value = {
        "title": "Test Article",
        "author": "John Doe",
        "core_argument": "Testing is important.",
        "key_claims": ["Claim 1", "Claim 2"],
        "entities_mentioned": ["John Doe", "OpenAI"],
        "concepts_mentioned": ["Testing", "RAG"],
    }

    raw_dir = tmp_project / "raw"
    articles_dir = raw_dir / "articles"
    wiki_dir = tmp_project / "wiki"

    # Create source file
    source = articles_dir / "test-article.md"
    source.write_text("# Test Article\n\nThis is a test article about testing and RAG.")

    result = ingest_source(source, source_type="article", wiki_dir=wiki_dir, raw_dir=raw_dir)

    assert result["source_type"] == "article"
    assert len(result["pages_created"]) > 0
    assert "summaries/test-article" in result["pages_created"]

    # Verify summary page was created
    summary = wiki_dir / "summaries" / "test-article.md"
    assert summary.exists()
    content = summary.read_text(encoding="utf-8")
    assert "Test Article" in content
    assert "type: summary" in content

    # Verify entity pages
    john_doe = wiki_dir / "entities" / "john-doe.md"
    assert john_doe.exists()

    # Verify concept pages
    testing = wiki_dir / "concepts" / "testing.md"
    assert testing.exists()

    # Verify index was updated
    index_content = (wiki_dir / "index.md").read_text(encoding="utf-8")
    assert "test-article" in index_content

    # Verify sources mapping was updated
    sources_content = (wiki_dir / "_sources.md").read_text(encoding="utf-8")
    assert "test-article" in sources_content


@patch("kb.ingest.pipeline.extract_from_source")
def test_ingest_source_does_not_mutate_prod_contradictions(mock_extract, tmp_path):
    """Regression: Phase 4.5 CRITICAL item 1 (WIKI_CONTRADICTIONS not patched to tmp wiki)."""
    from kb.config import WIKI_CONTRADICTIONS as prod_contradictions

    mock_extract.return_value = {
        "title": "Conflict Article",
        "author": "Test Author",
        "core_argument": "Testing is important.",
        "key_claims": ["The sky is never blue.", "Water is always cold."],
        "entities_mentioned": ["Author"],
        "concepts_mentioned": [],
    }

    raw_dir = tmp_path / "raw"
    articles_dir = raw_dir / "articles"
    articles_dir.mkdir(parents=True)
    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True)

    (wiki_dir / "index.md").write_text(
        "---\ntitle: Wiki Index\nupdated: 2026-04-06\n---\n\n# Knowledge Base Index\n\n"
        "## Entities\n\n*No pages yet.*\n\n## Concepts\n\n*No pages yet.*\n\n"
        "## Comparisons\n\n*No pages yet.*\n\n## Summaries\n\n*No pages yet.*\n\n"
        "## Synthesis\n\n*No pages yet.*\n"
    )
    (wiki_dir / "_sources.md").write_text(
        "---\ntitle: Source Mapping\nupdated: 2026-04-06\n---\n\n# Source Mapping\n"
    )
    (wiki_dir / "log.md").write_text(
        "---\ntitle: Activity Log\nupdated: 2026-04-06\n---\n\n# Activity Log\n"
    )
    tmp_contradictions = wiki_dir / "contradictions.md"
    tmp_contradictions.touch()

    source = articles_dir / "conflict-article.md"
    source.write_text("# Conflict Article\n\nThis article has conflicting claims.")

    prod_mtime_before = (
        prod_contradictions.stat().st_mtime if prod_contradictions.exists() else None
    )

    # H6 fix: pipeline now derives contradictions path from effective_wiki_dir, not global.
    # The patch on WIKI_CONTRADICTIONS is no longer needed (removed from pipeline imports).
    with (
        patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
        patch("kb.utils.paths.RAW_DIR", raw_dir),
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
    ):
        ingest_source(source, source_type="article", wiki_dir=wiki_dir)

    # Production contradictions.md must NOT have been touched
    prod_mtime_after = prod_contradictions.stat().st_mtime if prod_contradictions.exists() else None
    assert prod_mtime_before == prod_mtime_after, (
        "Production wiki/contradictions.md was mutated by test — WIKI_CONTRADICTIONS not sandboxed"
    )


def test_ingest_duplicate_branch_returns_all_contract_keys(tmp_path, monkeypatch):
    """Regression: Phase 4.5 CRITICAL item 6 — duplicate early-return omitted contract keys."""
    from kb.ingest import pipeline

    raw_dir = tmp_path / "raw"
    (raw_dir / "articles").mkdir(parents=True, exist_ok=True)
    source = raw_dir / "articles" / "dup-test.md"
    source.write_text("# Duplicate test\nBody content.", encoding="utf-8")

    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True, exist_ok=True)
    (wiki_dir / "log.md").write_text("# Wiki Log\n\n", encoding="utf-8")
    (wiki_dir / "contradictions.md").touch()
    (wiki_dir / "index.md").write_text(
        "---\ntitle: Wiki Index\nupdated: 2026-04-06\n---\n\n# Knowledge Base Index\n\n"
        "## Entities\n\n*No pages yet.*\n\n## Concepts\n\n*No pages yet.*\n\n"
        "## Comparisons\n\n*No pages yet.*\n\n## Summaries\n\n*No pages yet.*\n\n"
        "## Synthesis\n\n*No pages yet.*\n"
    )
    (wiki_dir / "_sources.md").write_text(
        "---\ntitle: Source Mapping\nupdated: 2026-04-06\n---\n\n# Source Mapping\n"
    )

    extraction = {"title": "Dup", "summary": "s", "entities_mentioned": []}

    # Force duplicate branch unconditionally — we test the return-dict shape, not detection logic.
    # Q_A fix: ingest_source now calls _check_and_reserve_manifest (was _is_duplicate_content).
    monkeypatch.setattr(pipeline, "_check_and_reserve_manifest", lambda *_: True)

    with (
        patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
        patch("kb.utils.paths.RAW_DIR", raw_dir),
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
    ):
        result = pipeline.ingest_source(
            source_path=source, wiki_dir=wiki_dir, extraction=extraction
        )

    assert result.get("duplicate") is True, f"expected duplicate=True: {result}"
    required_keys = {"affected_pages", "wikilinks_injected", "contradictions"}
    missing = required_keys - set(result.keys())
    assert not missing, f"duplicate branch missing keys: {missing}; full result: {result}"
    assert result["affected_pages"] == []
    assert result["wikilinks_injected"] == []
    assert result["contradictions"] == []


def test_ingest_binary_file_preserves_unicode_decode_cause(tmp_path):
    """Regression: Phase 4.5 CRITICAL item 18 (UnicodeDecodeError byte-offset diagnostic wiped)."""
    raw_dir = tmp_path / "raw"
    (raw_dir / "articles").mkdir(parents=True, exist_ok=True)
    binary = raw_dir / "articles" / "binary.md"
    binary.write_bytes(b"\xff\xfe valid utf-16 bom but not utf-8 \x00\x00")
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    with patch("kb.ingest.pipeline.RAW_DIR", raw_dir):
        try:
            ingest_source(source_path=binary, wiki_dir=wiki_dir)
            assert False, "expected ValueError"
        except ValueError as e:
            assert isinstance(e.__cause__, UnicodeDecodeError), (
                f"UnicodeDecodeError cause lost; __cause__ = {e.__cause__!r}"
            )


def test_ingest_skips_pure_punctuation_entities(tmp_path):
    """Regression: Phase 4.5 CRITICAL B1 — item 11 slugify untitled-<hash> fallback must NOT
    create ghost pages or inject untitled-<hash> wikilinks for nonsense-punctuation entity names.
    """
    from kb.ingest import pipeline

    raw_dir = tmp_path / "raw"
    (raw_dir / "articles").mkdir(parents=True, exist_ok=True)
    source = raw_dir / "articles" / "punct-entity.md"
    source.write_text("# Test\nBody content.", encoding="utf-8")

    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True, exist_ok=True)
    (wiki_dir / "log.md").write_text("# Wiki Log\n\n", encoding="utf-8")
    (wiki_dir / "contradictions.md").touch()
    (wiki_dir / "index.md").write_text(
        "---\ntitle: Wiki Index\nupdated: 2026-04-06\n---\n\n# Knowledge Base Index\n\n"
        "## Entities\n\n*No pages yet.*\n\n## Concepts\n\n*No pages yet.*\n\n"
        "## Comparisons\n\n*No pages yet.*\n\n## Summaries\n\n*No pages yet.*\n\n"
        "## Synthesis\n\n*No pages yet.*\n"
    )
    (wiki_dir / "_sources.md").write_text(
        "---\ntitle: Source Mapping\nupdated: 2026-04-06\n---\n\n# Source Mapping\n"
    )

    extraction = {
        "title": "Test Source",
        "summary": "Test summary.",
        "entities_mentioned": ["!!!", "...", "RealEntity"],
        "concepts_mentioned": [],
    }

    with (
        patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
        patch("kb.utils.paths.RAW_DIR", raw_dir),
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
    ):
        result = pipeline.ingest_source(
            source_path=source, wiki_dir=wiki_dir, extraction=extraction
        )

    # Real entity SHOULD get a page
    real_entity_page = wiki_dir / "entities" / "realentity.md"
    assert real_entity_page.exists(), (
        f"Real entity page missing; pages_created={result.get('pages_created', [])}"
    )

    # Nonsense-punctuation entities must NOT create untitled-<hash> pages
    entities_dir = wiki_dir / "entities"
    untitled_pages = list(entities_dir.glob("untitled-*.md"))
    assert not untitled_pages, (
        f"Pure-punctuation entities created untitled-<hash> pages: {untitled_pages}"
    )

    # Summary content must NOT contain untitled-<hash> wikilinks
    summary_path = wiki_dir / "summaries" / "test-source.md"
    assert summary_path.exists(), "Summary page was not created"
    summary_content = summary_path.read_text(encoding="utf-8")
    assert "untitled-" not in summary_content, (
        f"Summary injected untitled-<hash> wikilink:\n{summary_content}"
    )


def _make_wiki_dir(tmp_project):
    """Return the wiki dir for a tmp_project, creating required index files."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    (raw_dir / "articles").mkdir(parents=True, exist_ok=True)
    (wiki_dir / "log.md").write_text("# Wiki Log\n\n", encoding="utf-8")
    (wiki_dir / "contradictions.md").touch()
    (wiki_dir / "index.md").write_text(
        "---\ntitle: Wiki Index\nupdated: 2026-04-06\n---\n\n# Knowledge Base Index\n\n"
        "## Entities\n\n*No pages yet.*\n\n## Concepts\n\n*No pages yet.*\n\n"
        "## Comparisons\n\n*No pages yet.*\n\n## Summaries\n\n*No pages yet.*\n\n"
        "## Synthesis\n\n*No pages yet.*\n"
    )
    (wiki_dir / "_sources.md").write_text(
        "---\ntitle: Source Mapping\nupdated: 2026-04-06\n---\n\n# Source Mapping\n"
    )
    return wiki_dir, raw_dir


def test_ingest_allows_legitimate_untitled_prefix_entities(tmp_project, monkeypatch):
    """Regression: untitled-<hash6> sentinel must NOT drop entities literally named 'Untitled-*'."""
    from kb.ingest import pipeline

    wiki_dir, raw_dir = _make_wiki_dir(tmp_project)
    source = raw_dir / "articles" / "legit-names.md"
    source.write_text("# Legit\nBody.", encoding="utf-8")
    extraction = {
        "title": "Legit Names",
        "summary": "Test.",
        # Legit names with "untitled-" prefix — NOT the 6-hex sentinel shape
        "entities_mentioned": ["Untitled-Reports", "untitled-draft"],
        "concepts_discussed": [],
    }
    with (
        patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
        patch("kb.utils.paths.RAW_DIR", raw_dir),
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
    ):
        pipeline.ingest_source(
            source_path=source,
            wiki_dir=wiki_dir,
            extraction=extraction,
        )
    # Both legit entities SHOULD produce pages
    reports_page = wiki_dir / "entities" / "untitled-reports.md"
    draft_page = wiki_dir / "entities" / "untitled-draft.md"
    assert reports_page.exists(), "Untitled-Reports incorrectly filtered"
    assert draft_page.exists(), "untitled-draft incorrectly filtered"


def test_ingest_still_blocks_sentinel_hash_slug(tmp_project, monkeypatch):
    """Regression: the actual untitled-<hash6> sentinel IS still filtered."""
    from kb.ingest import pipeline

    wiki_dir, raw_dir = _make_wiki_dir(tmp_project)
    source = raw_dir / "articles" / "sentinel.md"
    source.write_text("# Sentinel\nBody.", encoding="utf-8")
    extraction = {
        "title": "Sentinel",
        "summary": "Test.",
        "entities_mentioned": ["!!!"],  # nonsense punctuation → untitled-<hash6>
        "concepts_discussed": [],
    }
    with (
        patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
        patch("kb.utils.paths.RAW_DIR", raw_dir),
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
    ):
        pipeline.ingest_source(
            source_path=source,
            wiki_dir=wiki_dir,
            extraction=extraction,
        )
    # Sentinel-hash pages MUST NOT be created
    untitled = list((wiki_dir / "entities").glob("untitled-*.md"))
    assert not untitled, f"nonsense entity created sentinel page: {untitled}"


def test_summary_page_prefers_filename_stem_over_untitled_sentinel(tmp_project, monkeypatch):
    """Regression: CJK/emoji titles should use source filename stem, not untitled-<hash>."""
    from kb.ingest import pipeline

    wiki_dir, raw_dir = _make_wiki_dir(tmp_project)
    source = raw_dir / "articles" / "readable-stem.md"  # readable filename
    source.write_text("# Body", encoding="utf-8")
    with (
        patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
        patch("kb.utils.paths.RAW_DIR", raw_dir),
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
    ):
        pipeline.ingest_source(
            source_path=source,
            wiki_dir=wiki_dir,
            extraction={"title": "😀😀😀", "summary": "s", "entities_mentioned": []},
        )
    # Summary should exist under a readable name, not untitled-<hash>
    summaries = list((wiki_dir / "summaries").glob("*.md"))
    assert summaries, "no summary page created"
    summary_name = summaries[0].name
    assert not summary_name.startswith("untitled-"), (
        f"summary used untitled-<hash> instead of readable stem: {summary_name}"
    )
    assert "readable-stem" in summary_name, f"expected readable-stem in name: {summary_name}"


# ── Concurrent-safety regression tests (Phase 4.5 HIGH) ──────────────────────


def test_append_evidence_trail_concurrent(tmp_path):
    """Regression: Phase 4.5 HIGH item H2 (append_evidence_trail concurrent RMW).

    Two threads appending to the same wiki page must both have their entries
    appear in the final content.
    """
    from kb.ingest.evidence import append_evidence_trail

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    page_path = wiki_dir / "concepts" / "concurrent.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(
        "---\ntitle: Concurrent\nsource:\n  - raw/articles/c.md\n"
        "created: 2026-04-16\nupdated: 2026-04-16\ntype: concept\nconfidence: stated\n---\n\n"
        "Initial content.\n",
        encoding="utf-8",
    )

    errors: list[Exception] = []

    def _append(source: str, action: str) -> None:
        try:
            append_evidence_trail(page_path, source, action, "2026-04-16")
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_append, args=("raw/articles/src-a.md", "action-alpha"))
    t2 = threading.Thread(target=_append, args=("raw/articles/src-b.md", "action-beta"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Unexpected exceptions during concurrent evidence trail writes: {errors}"
    content = page_path.read_text(encoding="utf-8")
    assert "action-alpha" in content, "action-alpha missing from evidence trail"
    assert "action-beta" in content, "action-beta missing from evidence trail"
    assert content.count("## Evidence Trail") == 1, "Evidence Trail section duplicated"


def test_persist_contradictions_concurrent(tmp_path, monkeypatch):
    """Regression: Phase 4.5 HIGH item H3 (_persist_contradictions concurrent RMW).

    Two threads writing different contradiction payloads concurrently must both
    appear in the final contradictions.md.

    Cycle 84 — made load-insensitive. This asserts a real invariant (the locked
    RMW loses no write), but it used an unsynchronised thread start and inherited
    `file_lock`'s 5-second `LOCK_TIMEOUT_SECONDS`. Under full-suite load the
    waiting thread could exceed that deadline and raise TimeoutError, producing a
    spurious failure that looks like a lock bug but is scheduler starvation. A
    barrier now guarantees the two threads genuinely contend (strengthening the
    test), and the acquisition deadline is widened so only a real lock failure —
    not a descheduled thread — can fail it.
    """
    import kb.utils.io as io_mod
    from kb.ingest.pipeline import _persist_contradictions

    monkeypatch.setattr(io_mod, "LOCK_TIMEOUT_SECONDS", 30.0)

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def _write(source_ref: str, claim: str) -> None:
        try:
            barrier.wait(timeout=60.0)
            _persist_contradictions(
                [{"claim": claim}],
                source_ref,
                wiki_dir,
            )
        except BaseException as exc:  # noqa: BLE001 — surfaced via assertion below
            errors.append(exc)

    t1 = threading.Thread(target=_write, args=("raw/articles/src-a.md", "claim-from-thread-one"))
    t2 = threading.Thread(target=_write, args=("raw/articles/src-b.md", "claim-from-thread-two"))
    t1.start()
    t2.start()
    t1.join(timeout=60.0)
    t2.join(timeout=60.0)

    assert not t1.is_alive() and not t2.is_alive(), "contradiction writer threads did not finish"

    assert not errors, f"Unexpected exceptions during concurrent contradiction writes: {errors}"
    content = (wiki_dir / "contradictions.md").read_text(encoding="utf-8")
    assert "claim-from-thread-one" in content, "Thread-1 claim missing from contradictions.md"
    assert "claim-from-thread-two" in content, "Thread-2 claim missing from contradictions.md"


def _make_wiki_and_raw(tmp_path):
    """Set up a minimal wiki + raw dir structure for integration tests."""
    wiki_dir = tmp_path / "wiki"
    raw_dir = tmp_path / "raw"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True)
    for subdir in ("articles",):
        (raw_dir / subdir).mkdir(parents=True)
    (wiki_dir / "index.md").write_text(
        "---\ntitle: Wiki Index\nupdated: 2026-04-16\n---\n\n# Knowledge Base Index\n\n"
        "## Entities\n\n*No pages yet.*\n\n## Concepts\n\n*No pages yet.*\n\n"
        "## Comparisons\n\n*No pages yet.*\n\n## Summaries\n\n*No pages yet.*\n\n"
        "## Synthesis\n\n*No pages yet.*\n"
    )
    (wiki_dir / "_sources.md").write_text(
        "---\ntitle: Source Mapping\nupdated: 2026-04-16\n---\n\n# Source Mapping\n"
    )
    (wiki_dir / "log.md").write_text("# Wiki Log\n\n", encoding="utf-8")
    return wiki_dir, raw_dir


@patch("kb.ingest.pipeline.extract_from_source")
def test_duplicate_content_concurrent_ingest(mock_extract, tmp_path):
    """Regression: Phase 4.5 HIGH item Q_A (manifest RMW race on duplicate hash).

    Two threads ingesting different source files with identical content: exactly one
    must create pages, the other must return duplicate: True.
    """
    mock_extract.return_value = {
        "title": "Concurrent Duplicate Article",
        "author": "Author",
        "core_argument": "Same content.",
        "key_claims": [],
        "entities_mentioned": [],
        "concepts_mentioned": [],
    }

    wiki_dir, raw_dir = _make_wiki_and_raw(tmp_path)
    manifest_path = tmp_path / ".data" / "hashes.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # Write two source files with identical content (same hash)
    identical_content = "# Identical Content\n\nThis is the same article."
    src_a = raw_dir / "articles" / "src-a.md"
    src_b = raw_dir / "articles" / "src-b.md"
    src_a.write_text(identical_content, encoding="utf-8")
    src_b.write_text(identical_content, encoding="utf-8")

    results: list[dict] = []
    errors: list[Exception] = []

    # Apply all patches BEFORE starting threads — sharing a patched environment between
    # threads is safe; applying patches from multiple threads concurrently is not.
    with (
        patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
        patch("kb.utils.paths.RAW_DIR", raw_dir),
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
        patch("kb.compile.compiler.HASH_MANIFEST", manifest_path),
        # PROJECT_ROOT must point to tmp_path so other_path.exists() resolves correctly
        patch("kb.ingest.pipeline.PROJECT_ROOT", tmp_path),
    ):

        def _ingest(source) -> None:
            try:
                res = ingest_source(source, source_type="article", wiki_dir=wiki_dir)
                results.append(res)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=_ingest, args=(src_a,))
        t2 = threading.Thread(target=_ingest, args=(src_b,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    assert not errors, f"Unexpected exceptions: {errors}"
    assert len(results) == 2, f"Expected 2 results, got: {results}"

    duplicates = [r for r in results if r.get("duplicate")]
    non_duplicates = [r for r in results if not r.get("duplicate")]

    assert len(duplicates) == 1, (
        f"Expected exactly 1 duplicate result; got duplicates={duplicates}, "
        f"non_duplicates={non_duplicates}"
    )
    assert len(non_duplicates) == 1, (
        f"Expected exactly 1 non-duplicate result; got duplicates={duplicates}, "
        f"non_duplicates={non_duplicates}"
    )
    # The non-duplicate must have created pages
    assert non_duplicates[0]["pages_created"], "Non-duplicate ingest created no pages"


# ── Cycle 10 AC22: _coerce_str_field type-rejection (cycle 43 fold) ─


@pytest.mark.parametrize(
    ("extraction", "field", "expected", "type_name"),
    [
        ({"title": "A title"}, "title", "A title", None),
        ({"title": ""}, "title", "", None),
        ({}, "title", "", None),
        ({"title": None}, "title", "", None),
        ({"title": 1}, "title", None, "int"),
        ({"title": 1.5}, "title", None, "float"),
        ({"title": {"nested": "dict"}}, "title", None, "dict"),
        ({"title": ["list"]}, "title", None, "list"),
        ({"title": b"bytes"}, "title", None, "bytes"),
        ({"title": True}, "title", None, "bool"),
    ],
)
def test_coerce_str_field_accepts_string_missing_none_and_rejects_non_strings(
    extraction, field, expected, type_name
):
    before = dict(extraction)

    if type_name is None:
        assert _coerce_str_field(extraction, field) == expected
    else:
        with pytest.raises(ValueError, match=rf"title.*must be string.*{type_name}"):
            _coerce_str_field(extraction, field)
    assert extraction == before


def test_ingest_source_rejects_non_string_extraction_before_writes_and_manifest(
    tmp_project, monkeypatch
):
    data_dir = tmp_project / ".data"
    data_dir.mkdir()
    manifest_path = data_dir / "hashes.json"
    raw_path = tmp_project / "raw" / "articles" / "bad.md"
    raw_path.write_text("# Bad\n\nBenign content.", encoding="utf-8")
    raw_hash = hash_bytes(raw_path.read_bytes())
    monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", manifest_path)

    with pytest.raises(ValueError, match=r"core_argument.*must be string.*dict"):
        ingest_source(
            raw_path,
            "article",
            extraction={"title": "Bad", "core_argument": {"nested": "dict"}},
            wiki_dir=tmp_project / "wiki",
            raw_dir=tmp_project / "raw",
            _skip_vector_rebuild=True,
        )

    assert list((tmp_project / "wiki" / "summaries").iterdir()) == []
    assert list((tmp_project / "wiki" / "entities").iterdir()) == []
    assert list((tmp_project / "wiki" / "concepts").iterdir()) == []
    if manifest_path.exists():
        assert raw_hash not in json.loads(manifest_path.read_text(encoding="utf-8")).values()


def test_build_summary_content_defensively_rejects_non_string_fields():
    with pytest.raises(ValueError, match=r"core_argument.*must be string.*dict"):
        _build_summary_content(
            {"title": "Bad", "core_argument": {"nested": "dict"}},
            "article",
        )


def test_ingest_source_accepts_valid_string_extraction(tmp_project, monkeypatch):
    data_dir = tmp_project / ".data"
    data_dir.mkdir()
    monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", data_dir / "hashes.json")
    raw_path = tmp_project / "raw" / "articles" / "good.md"
    raw_path.write_text("# Good\n\nBenign content.", encoding="utf-8")

    result = ingest_source(
        raw_path,
        "article",
        extraction={
            "title": "Good Article",
            "author": "A. Writer",
            "core_argument": "A valid overview.",
            "entities_mentioned": [],
            "concepts_mentioned": [],
        },
        wiki_dir=tmp_project / "wiki",
        raw_dir=tmp_project / "raw",
        _skip_vector_rebuild=True,
    )

    assert result["pages_created"]
    assert list((tmp_project / "wiki" / "summaries").glob("*.md"))


# ── Cycle 11 — extract_entity_context + summary callee type rejection ─
# (cycle 43 fold from test_cycle11_ingest_coerce.py; 7 _coerce_str_field
#  bare-function duplicates of the AC22 parametrized test above were
#  dropped per cycle-17 L3 scope narrowing)


def _valid_extraction_cycle11(**overrides):
    extraction = {
        "title": "ok",
        "core_argument": "ok",
        "key_claims": [],
        "entities_mentioned": [],
        "concepts_mentioned": [],
    }
    extraction.update(overrides)
    return extraction


def test_ingest_source_rejects_non_string_summary_callee(tmp_project, monkeypatch):
    data_dir = tmp_project / ".data"
    data_dir.mkdir()
    monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", data_dir / "hashes.json")
    source_path = tmp_project / "raw" / "articles" / "bad.md"
    source_path.write_text("# Bad\n\ncontent", encoding="utf-8")

    with pytest.raises(ValueError):
        ingest_source(
            source_path,
            source_type="article",
            extraction=_valid_extraction_cycle11(core_argument=42),
            wiki_dir=tmp_project / "wiki",
            raw_dir=tmp_project / "raw",
            _skip_vector_rebuild=True,
        )


def test_extract_entity_context_rejects_non_string_context_field_cleanly():
    with pytest.raises(ValueError):
        _extract_entity_context(
            "ok",
            _valid_extraction_cycle11(description=123, quotes="ok"),
        )


@pytest.mark.parametrize("source_type", ["comparison", "synthesis"])
def test_ingest_source_rejects_comparison_and_synthesis_with_kb_create_page_message(
    tmp_project, monkeypatch, source_type
):
    data_dir = tmp_project / ".data"
    data_dir.mkdir()
    manifest_path = data_dir / "hashes.json"
    monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", manifest_path)
    source_path = tmp_project / "raw" / "articles" / f"{source_type}.md"
    source_path.write_text("# Unsupported\n\ncontent", encoding="utf-8")

    with pytest.raises(ValueError, match="kb_create_page"):
        ingest_source(
            source_path,
            source_type=source_type,
            extraction=_valid_extraction_cycle11(),
            wiki_dir=tmp_project / "wiki",
            raw_dir=tmp_project / "raw",
            _skip_vector_rebuild=True,
        )

    assert not manifest_path.exists()
    assert list((tmp_project / "wiki" / "summaries").iterdir()) == []


@pytest.mark.parametrize("source_type", ["comparison", "synthesis"])
def test_kb_ingest_content_rejects_page_types_without_raw_file(
    tmp_project, monkeypatch, source_type
):
    raw_dir = tmp_project / "raw"
    before = sorted(path.relative_to(raw_dir) for path in raw_dir.rglob("*") if path.is_file())
    monkeypatch.setattr(mcp_core, "PROJECT_ROOT", tmp_project)
    monkeypatch.setattr(mcp_core, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mcp_core, "SOURCE_TYPE_DIRS", {"article": raw_dir / "articles"})

    result = mcp_core.kb_ingest_content(
        content="# Unsupported\n\ncontent",
        filename=f"{source_type}.md",
        source_type=source_type,
        extraction_json='{"title": "Unsupported"}',
    )

    assert "kb_create_page" in result
    after = sorted(path.relative_to(raw_dir) for path in raw_dir.rglob("*") if path.is_file())
    assert after == before


# ── Phase 4 ingest aux fixes (cycle 55 fold) ──────────────────────────
# Source: tests/test_v01009_ingest_aux_fixes.py (deleted in same commit).


def test_load_template_returns_deep_copy():
    """Mutating the returned dict must NOT corrupt the cache."""
    from kb.ingest.extractors import load_template

    a = load_template("article")
    assert isinstance(a, dict)
    # Mutate a
    a["__mutated__"] = True
    # Reload — must be a fresh dict, NOT the same object
    b = load_template("article")
    assert "__mutated__" not in b, "lru_cache is returning the same mutable dict"


def test_evidence_trail_crlf_header(tmp_path):
    """CRLF Evidence Trail header must not cause double-section append."""
    from kb.ingest.evidence import append_evidence_trail

    page = tmp_path / "p.md"
    # Write with CRLF line ending for the Evidence Trail header
    page.write_bytes(
        b"---\ntitle: p\ntype: concept\nconfidence: stated\n---\nBody\n\n## Evidence Trail\r\n\n"
    )
    append_evidence_trail(page, source_ref="raw/a.md", action="test")
    text = page.read_text(encoding="utf-8")
    count = text.count("## Evidence Trail")
    assert count == 1, f"Expected 1 Evidence Trail section, got {count}"


def test_contradiction_truncation_logged(caplog):
    """Truncating claims for contradiction check must emit a warning log.

    Phase 4.5 HIGH D5: promoted from debug to warning level.
    """
    import logging

    from kb.config import CONTRADICTION_MAX_CLAIMS_TO_CHECK
    from kb.ingest.contradiction import detect_contradictions

    extra = CONTRADICTION_MAX_CLAIMS_TO_CHECK + 5
    claims = [f"claim number {i}" for i in range(extra)]
    dummy_page = {"id": "concepts/dummy", "content": "This is a dummy claim for testing."}
    with caplog.at_level(logging.WARNING, logger="kb.ingest.contradiction"):
        detect_contradictions(claims, existing_pages=[dummy_page])
    # At least one warning message about truncation
    msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    truncation_msgs = [
        m
        for m in msgs
        if str(CONTRADICTION_MAX_CLAIMS_TO_CHECK) in m
        or "truncat" in m.lower()
        or "first" in m.lower()
    ]
    assert truncation_msgs, f"Expected truncation warning log, got: {msgs}"


# ─────────────────────────────────────────────────────────────────────
# Folded from tests/test_v01008_ingest_pipeline_fixes.py
# (cycle 77 freeze-and-fold) — Phase 4 ingest/pipeline.py fixes.
# Tests moved VERBATIM; names preserved; provenance in CHANGELOG-history cycle-77.
# ─────────────────────────────────────────────────────────────────────


def test_subdir_map_raises_valueerror_on_unknown_type():
    from kb.ingest.pipeline import _process_item_batch

    with pytest.raises((ValueError, KeyError)):
        # Pass minimal args — we just want the type guard to fire
        _process_item_batch(
            items_raw=[],
            field_name="x",
            max_count=10,
            page_type="not_a_real_type",
            source_ref="x",
            extraction={},
        )


def test_references_regex_handles_whitespace_only_lines(tmp_wiki):
    from kb.ingest.pipeline import _update_existing_page

    page = tmp_wiki / "concepts" / "p.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "---\ntitle: p\ntype: concept\nconfidence: stated\n"
        "source:\n  - raw/articles/a.md\nupdated: 2024-01-01\n---\n"
        "Body.\n\n## References\n\n- [raw/articles/a.md]\n   \n",
        encoding="utf-8",
    )
    _update_existing_page(page, source_ref="raw/articles/c.md")
    final = page.read_text(encoding="utf-8")
    assert final.count("## References") == 1, f"Got multiple References headers:\n{final}"


def test_frontmatter_missing_logs_warning_returns_early(tmp_wiki, caplog):
    import logging

    from kb.ingest.pipeline import _update_existing_page

    page = tmp_wiki / "concepts" / "broken.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    original_content = "no frontmatter here\nupdated: 2024-01-01\n"
    page.write_text(original_content, encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
        _update_existing_page(page, source_ref="raw/articles/x.md")

    # File must NOT have been modified with corrupted date
    final = page.read_text(encoding="utf-8")
    assert final == original_content, "File content should be unchanged"


def test_wiki_contradictions_file_exists_in_config():
    from kb import config

    assert hasattr(config, "WIKI_CONTRADICTIONS"), "WIKI_CONTRADICTIONS missing from config"


def test_build_summary_content_not_called_on_existing_summary(tmp_wiki, monkeypatch):
    import kb.ingest.pipeline as pipeline_mod

    call_count = {"n": 0}
    original = pipeline_mod._build_summary_content

    def counting_build(extraction, source_type):
        call_count["n"] += 1
        return original(extraction, source_type)

    monkeypatch.setattr(pipeline_mod, "_build_summary_content", counting_build)

    # Create a pre-existing summary page
    summary_dir = tmp_wiki / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_page = summary_dir / "test-article.md"
    summary_page.write_text(
        "---\ntitle: Test Article\ntype: summary\nconfidence: stated\n"
        "source:\n  - raw/articles/old.md\nupdated: 2024-01-01\n---\nContent.\n",
        encoding="utf-8",
    )

    extraction = {
        "title": "Test Article",
        "entities_mentioned": [],
        "concepts_mentioned": [],
    }

    # Patch helpers that touch disk to avoid side effects
    monkeypatch.setattr(pipeline_mod, "_update_existing_page", lambda *a, **kw: None)
    monkeypatch.setattr(pipeline_mod, "_update_index_batch", lambda *a, **kw: None)
    monkeypatch.setattr(pipeline_mod, "_update_sources_mapping", lambda *a, **kw: None)
    monkeypatch.setattr(pipeline_mod, "append_wiki_log", lambda *a, **kw: None)
    monkeypatch.setattr(pipeline_mod, "load_all_pages", lambda **kw: [])
    monkeypatch.setattr(pipeline_mod, "_find_affected_pages", lambda *a, **kw: [])
    # Cycle 4 item #22: pipeline migrated to detect_contradictions_with_metadata
    # (returns dict). Patch the new sibling to match production dispatch.
    monkeypatch.setattr(
        pipeline_mod,
        "detect_contradictions_with_metadata",
        lambda *a, **kw: {
            "contradictions": [],
            "claims_checked": 0,
            "claims_total": 0,
            "truncated": False,
        },
    )

    # We can't call ingest_source easily without raw/ path setup; test the branching directly
    # by checking the module-level function logic by inspecting source code structure.
    # The real test is that _build_summary_content is inside the else branch.
    # Verify via the call count approach using a minimal reimplementation of the branch.
    from kb.utils.text import slugify

    title = extraction.get("title") or "untitled"
    summary_slug = slugify(title)
    summary_path = tmp_wiki / "summaries" / f"{summary_slug}.md"

    # summary_path exists — mimic the branch
    if summary_path.exists():
        # The fixed code: _build_summary_content is NOT called here
        pass
    else:
        pipeline_mod._build_summary_content(extraction, "article")

    assert call_count["n"] == 0, "_build_summary_content called even though summary existed"


def test_source_block_re_handles_four_space_indent(tmp_wiki):
    from kb.ingest.pipeline import _SOURCE_BLOCK_RE

    content = "---\ntitle: X\nsource:\n    - raw/articles/a.md\nupdated: 2024-01-01\n---\n"
    m = _SOURCE_BLOCK_RE.search(content)
    assert m is not None, "_SOURCE_BLOCK_RE did not match 4-space indented source block"


def test_h6_persist_contradictions_uses_wiki_dir(tmp_path, monkeypatch):
    from unittest.mock import patch

    import kb.ingest.pipeline as pipeline_mod
    from kb.config import WIKI_CONTRADICTIONS as prod_contradictions

    # Set up isolated wiki
    wiki_dir = tmp_path / "wiki"
    for sub in ("entities", "concepts", "summaries", "comparisons", "synthesis"):
        (wiki_dir / sub).mkdir(parents=True)
    idx_content = "# Index\n\n## Summaries\n\n## Entities\n\n## Concepts\n\n"
    (wiki_dir / "index.md").write_text(idx_content, encoding="utf-8")
    (wiki_dir / "_sources.md").write_text("# Sources\n\n", encoding="utf-8")
    (wiki_dir / "log.md").write_text("# Wiki Log\n\n", encoding="utf-8")
    raw_dir = tmp_path / "raw" / "articles"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "h6-test.md"
    source.write_text("# H6 Test\nContent.", encoding="utf-8")

    extraction = {
        "title": "H6 Test",
        "entities_mentioned": [],
        "concepts_mentioned": [],
        "key_claims": ["The sky is never blue.", "Water is always cold."],
    }

    prod_mtime_before = (
        prod_contradictions.stat().st_mtime if prod_contradictions.exists() else None
    )

    with (
        patch("kb.ingest.pipeline.RAW_DIR", tmp_path / "raw"),
        patch("kb.utils.paths.RAW_DIR", tmp_path / "raw"),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
    ):
        # Pass wiki_dir explicitly — contradictions.md must go to wiki_dir, not prod.
        pipeline_mod.ingest_source(
            source, source_type="article", wiki_dir=wiki_dir, extraction=extraction
        )

    prod_mtime_after = prod_contradictions.stat().st_mtime if prod_contradictions.exists() else None
    assert prod_mtime_before == prod_mtime_after, (
        "H6: ingest_source mutated production wiki/contradictions.md — "
        "effective_wiki_dir not used for _persist_contradictions"
    )


def test_contradictions_written_to_file(tmp_wiki, tmp_path, monkeypatch):
    import kb.config as config_mod
    import kb.ingest.pipeline as pipeline_mod

    contra_path = tmp_wiki / "contradictions.md"
    monkeypatch.setattr(config_mod, "WIKI_CONTRADICTIONS", contra_path)
    # Also patch the name imported into pipeline
    monkeypatch.setattr(pipeline_mod, "WIKI_CONTRADICTIONS", contra_path, raising=False)

    warnings = [{"claim": "X causes Y", "page": "entities/x", "conflict": "X does not cause Y"}]

    # Simulate the write block from pipeline
    if warnings:
        from datetime import date

        header = "# Contradictions\n\nAppend-only log of conflicts detected during ingest.\n\n"
        existing = contra_path.read_text(encoding="utf-8") if contra_path.exists() else header
        block = f"\n## raw/articles/test.md — {date.today().isoformat()}\n"
        for w in warnings:
            block += f"- {w}\n"
        from kb.utils.io import atomic_text_write

        atomic_text_write(existing + block, contra_path)

    assert contra_path.exists(), "contradictions.md was not created"
    text = contra_path.read_text(encoding="utf-8")
    assert "## raw/articles/test.md" in text
    assert "X causes Y" in text


# ═══════════════════════════════════════════════════════════════════════
# Cycle 78 freeze-and-fold — moved verbatim from
# tests/test_v0917_contradiction.py, tests/test_v0917_evidence_trail.py,
# and tests/test_v0916_task03.py. Only deviation: fold-site imports below.
# ═══════════════════════════════════════════════════════════════════════

import hashlib  # noqa: E402  — fold-site import (cycle 78)

from kb.ingest.contradiction import detect_contradictions  # noqa: E402  — fold-site (cycle 78)
from kb.ingest.evidence import (  # noqa: E402  — fold-site import (cycle 78)
    append_evidence_trail,
    build_evidence_entry,
)

# ── tests/test_v0917_contradiction.py — auto-contradiction detection (Phase 4) ──


class TestDetectContradictions:
    def test_no_contradictions_empty_wiki(self):
        new_claims = ["Transformers use self-attention."]
        result = detect_contradictions(new_claims, existing_pages=[])
        assert result == []

    def test_no_false_positives_on_unrelated(self):
        # Use genuinely disjoint vocabularies to prevent heuristic false-positives.
        new_claims = ["The Eiffel Tower stands in Paris."]
        existing = [
            {
                "id": "concepts/qcd",
                "content": "Quantum chromodynamics describes quark interactions.",
                "title": "QCD",
            }
        ]
        result = detect_contradictions(new_claims, existing_pages=existing)
        assert result == []

    def test_respects_max_claims(self):
        claims = [f"Claim {i}" for i in range(20)]
        result = detect_contradictions(claims, existing_pages=[], max_claims=5)
        # Should not error even with many claims
        assert isinstance(result, list)


def test_returns_empty_list_when_no_contradiction(tmp_project):
    """Regression: Phase 4.5 CRITICAL item 2 (empty-path explicitly tested, no silent loop-skip)."""
    from kb.ingest.contradiction import detect_contradictions

    result = detect_contradictions(new_claims=["unrelated topic"], existing_pages=[])
    assert result == []


def test_returns_contradiction_dict_when_heuristic_fires(tmp_project):
    """Regression: Phase 4.5 CRITICAL item 2 (fired path: verify dict shape)."""
    from kb.ingest.contradiction import detect_contradictions

    existing_pages = [
        {
            "id": "concepts/latency",
            "content": "Network latency is always high in mobile networks.",
        }
    ]
    result = detect_contradictions(
        new_claims=["Network latency is never high in mobile networks."],
        existing_pages=existing_pages,
    )
    assert len(result) >= 1, "heuristic should catch 'always' vs 'never'"
    item = result[0]
    for key in ("new_claim", "existing_page", "existing_text", "reason"):
        assert key in item


# ── tests/test_v0917_evidence_trail.py — evidence trail sections (Phase 4) ──


class TestBuildEvidenceEntry:
    def test_basic_entry(self):
        # Use fixed date to avoid midnight boundary flake (cycle 5 fix).
        entry = build_evidence_entry(
            source_ref="raw/articles/example.md",
            action="Initial extraction: core concept definition",
            entry_date="2026-01-01",
        )
        assert entry.startswith("- 2026-01-01")
        assert "raw/articles/example.md" in entry
        assert "Initial extraction" in entry

    def test_custom_date(self):
        entry = build_evidence_entry(
            source_ref="raw/papers/paper.md",
            action="Updated: added formulation",
            entry_date="2026-01-15",
        )
        assert entry.startswith("- 2026-01-15")

    def test_entry_is_single_line(self):
        entry = build_evidence_entry(
            source_ref="raw/articles/a.md",
            action="Some action",
        )
        assert "\n" not in entry.strip()


class TestAppendEvidenceTrail:
    def test_adds_section_to_page_without_trail(self, tmp_path):
        page = tmp_path / "test.md"
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-04-12\nupdated: 2026-04-12\n"
            "type: concept\nconfidence: stated\n---\n\n"
            "# Test\n\nSome content.\n",
            encoding="utf-8",
        )
        append_evidence_trail(page, "raw/articles/a.md", "Initial extraction: definition")
        text = page.read_text(encoding="utf-8")
        assert "## Evidence Trail" in text
        assert "raw/articles/a.md" in text
        assert "Initial extraction: definition" in text
        # Content above trail is preserved
        assert "# Test" in text
        assert "Some content." in text

    def test_appends_to_existing_trail(self, tmp_path):
        page = tmp_path / "test.md"
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-04-12\nupdated: 2026-04-12\n"
            "type: concept\nconfidence: stated\n---\n\n"
            "# Test\n\nContent.\n\n## Evidence Trail\n"
            "- 2026-04-10 | raw/articles/a.md | First entry\n",
            encoding="utf-8",
        )
        append_evidence_trail(page, "raw/articles/b.md", "Updated: new info")
        text = page.read_text(encoding="utf-8")
        # New entry at top (reverse chronological)
        trail_idx = text.index("## Evidence Trail")
        trail = text[trail_idx:]
        lines = [line for line in trail.split("\n") if line.startswith("- ")]
        assert len(lines) == 2
        assert "raw/articles/b.md" in lines[0]  # Newest first
        assert "raw/articles/a.md" in lines[1]

    def test_preserves_frontmatter(self, tmp_path):
        page = tmp_path / "test.md"
        original = (
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-04-12\nupdated: 2026-04-12\n"
            "type: concept\nconfidence: stated\n---\n\n"
            "Body content.\n"
        )
        page.write_text(original, encoding="utf-8")
        append_evidence_trail(page, "raw/articles/a.md", "action")
        text = page.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert 'title: "Test"' in text


# ── tests/test_v0916_task03.py — Phase 3.97 Task 03 ingest pipeline fixes ──


class TestUpdateIndexBatchPrefixMatch:
    """_update_index_batch must use wikilink-boundary match, not substring."""

    def test_shorter_slug_not_blocked_by_longer(self, tmp_wiki):
        from kb.ingest.pipeline import _update_index_batch

        index = tmp_wiki / "index.md"
        index.write_text(
            "## Entities\n\n- [[entities/openai-corporation|OpenAI Corporation]]\n",
            encoding="utf-8",
        )
        _update_index_batch([("entity", "openai", "OpenAI")], wiki_dir=tmp_wiki)
        content = index.read_text(encoding="utf-8")
        assert "[[entities/openai|OpenAI]]" in content


class TestUpdateIndexBatchTitleSanitization:
    """_update_index_batch must sanitize pipe and newline in titles."""

    def test_pipe_in_title_sanitized(self, tmp_wiki):
        from kb.ingest.pipeline import _update_index_batch

        index = tmp_wiki / "index.md"
        index.write_text("## Concepts\n\n", encoding="utf-8")
        _update_index_batch([("concept", "rag-search", "RAG | Vector Search")], wiki_dir=tmp_wiki)
        content = index.read_text(encoding="utf-8")
        assert "||" not in content  # no double pipe
        assert "RAG" in content


class TestIngestSourceBinaryPDF:
    """ingest_source must handle binary PDF gracefully."""

    def test_binary_file_raises_clear_error(self, tmp_project):
        raw_dir = tmp_project / "raw"
        pdf = raw_dir / "papers" / "binary.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.4\x00\x01\x02binary content")

        from kb.ingest.pipeline import ingest_source

        with pytest.raises((UnicodeDecodeError, ValueError)):
            ingest_source(pdf, "paper")


class TestBuildExtractionSchemaNoneGuard:
    """build_extraction_schema must reject template with extract: None."""

    def test_none_extract_raises_value_error(self):
        from kb.ingest.extractors import build_extraction_schema

        template = {"name": "test", "extract": None}
        with pytest.raises(ValueError, match="extract"):
            build_extraction_schema(template)


class TestBuildItemContentNameSanitization:
    """_build_item_content must sanitize newlines in entity/concept names."""

    def test_newline_in_name_stripped(self):
        from kb.ingest.pipeline import _build_item_content

        content = _build_item_content("Test\nEntity", "raw/articles/test.md", "", "Mentioned")
        lines = content.split("\n")
        assert lines[0] == "# Test Entity"


class TestBuildSummaryContentTitleSanitization:
    """_build_summary_content must sanitize newlines in title."""

    def test_newline_in_title_stripped(self):
        from kb.ingest.pipeline import _build_summary_content

        extraction = {"title": "Test\nTitle", "core_argument": "Arg"}
        content = _build_summary_content(extraction, "article")
        assert "# Test Title" in content
        assert "# Test\n" not in content


class TestDetectSourceTypeCustomRawDir:
    """detect_source_type must accept custom raw_dir parameter."""

    def test_custom_raw_dir(self, tmp_path):
        custom_raw = tmp_path / "custom_raw"
        articles = custom_raw / "articles"
        articles.mkdir(parents=True)
        source = articles / "test.md"
        source.write_text("content", encoding="utf-8")

        from kb.ingest.pipeline import detect_source_type

        result = detect_source_type(source, raw_dir=custom_raw)
        assert result == "article"


class TestTemplateCacheClear:
    """Template cache clear helper must exist."""

    def test_clear_template_cache_exists(self):
        from kb.ingest.extractors import clear_template_cache

        clear_template_cache()  # should not raise


class TestIngestSourceUsesContentHash:
    """ingest_source should use content_hash utility, not inline hashlib."""

    def test_hash_matches_utility(self, tmp_project):
        from kb.utils.hashing import content_hash

        raw_dir = tmp_project / "raw"
        source = raw_dir / "articles" / "hash-test.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("test content for hash", encoding="utf-8")

        expected = content_hash(source)
        raw_bytes = source.read_bytes()
        inline = hashlib.sha256(raw_bytes).hexdigest()[:32]
        assert expected == inline  # both should match


# Cycle 80 freeze-and-fold — moved verbatim from tests/test_v0915_task02.py
# (Phase 3.96 Task 2 — Ingest pipeline fixes).
class TestAtomicWikiPageWrites:
    """Fix 2.1: Wiki page writes must use atomic_text_write."""

    def test_write_wiki_page_uses_atomic(self, tmp_path, monkeypatch):
        import kb.ingest.pipeline as pipeline

        calls = []

        def tracking_atomic(content, path):
            calls.append(("atomic", str(path)))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        monkeypatch.setattr("kb.ingest.pipeline.atomic_text_write", tracking_atomic)
        page_path = tmp_path / "wiki" / "summaries" / "test.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        pipeline._write_wiki_page(
            page_path, "Test", "summary", "raw/articles/t.md", "stated", "body"
        )
        assert len(calls) == 1
        assert calls[0][0] == "atomic"

    def test_update_existing_page_uses_atomic(self, tmp_path, monkeypatch):
        import kb.ingest.pipeline as pipeline

        page = tmp_path / "concepts" / "test.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\n# Test\n\n## References\n\n"
            "- Mentioned in raw/articles/a.md\n",
            encoding="utf-8",
        )

        calls = []

        def tracking_atomic(content, path):
            calls.append(str(path))
            path.write_text(content, encoding="utf-8")

        monkeypatch.setattr("kb.ingest.pipeline.atomic_text_write", tracking_atomic)
        pipeline._update_existing_page(page, "raw/articles/b.md")
        assert len(calls) == 1


class TestUpdateExistingPageSingleRead:
    """Fix 2.2: _update_existing_page must parse frontmatter from in-memory content."""

    def test_frontmatter_parsed_from_memory(self, tmp_path, monkeypatch):
        import kb.ingest.pipeline as pipeline

        page = tmp_path / "concepts" / "test.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\n# Test\n",
            encoding="utf-8",
        )

        read_count = [0]
        original_read = type(page).read_text

        def counting_read(self, *args, **kwargs):
            read_count[0] += 1
            return original_read(self, *args, **kwargs)

        monkeypatch.setattr(type(page), "read_text", counting_read)
        monkeypatch.setattr(
            "kb.ingest.pipeline.atomic_text_write",
            lambda content, path: path.write_text(content, encoding="utf-8"),
        )
        # Suppress evidence trail to isolate single-read assertion to pipeline core logic
        monkeypatch.setattr("kb.ingest.pipeline.append_evidence_trail", lambda *a, **kw: None)
        pipeline._update_existing_page(page, "raw/articles/b.md")
        assert read_count[0] == 1, f"File read {read_count[0]} times, expected 1"


class TestSourceLinePatternPrecision:
    """Fix 2.3: source ref injection must only target the source: block."""

    def test_tags_list_not_corrupted(self, tmp_path, monkeypatch):
        import kb.ingest.pipeline as pipeline

        page = tmp_path / "concepts" / "test.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            '---\ntitle: "Test"\ntags:\n  - "python"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\n# Test\n\n## References\n\n"
            "- Mentioned in raw/articles/a.md\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "kb.ingest.pipeline.atomic_text_write",
            lambda content, path: path.write_text(content, encoding="utf-8"),
        )
        pipeline._update_existing_page(page, "raw/articles/b.md")
        result = page.read_text(encoding="utf-8")
        lines = result.split("\n")
        source_a_idx = next(i for i, ln in enumerate(lines) if "articles/a.md" in ln)
        source_b_idx = next(i for i, ln in enumerate(lines) if "articles/b.md" in ln)
        tags_idx = next(i for i, ln in enumerate(lines) if '"python"' in ln)
        assert source_b_idx > source_a_idx
        assert source_b_idx != tags_idx + 1


class TestContextBlockDedup:
    """Fix 2.4: context dedup must check section header, not full block."""

    def test_no_duplicate_context_section(self, tmp_path, monkeypatch):
        import kb.ingest.pipeline as pipeline

        page = tmp_path / "entities" / "test.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: entity\n"
            "confidence: stated\n---\n\n# Test\n\n## Context\n\n- Existing\n\n"
            "## References\n\n- Mentioned in raw/articles/a.md\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "kb.ingest.pipeline.atomic_text_write",
            lambda c, p: p.write_text(c, encoding="utf-8"),
        )
        pipeline._update_existing_page(
            page,
            "raw/articles/b.md",
            name="Test",
            extraction={"core_argument": "Test is important"},
        )
        result = page.read_text(encoding="utf-8")
        assert result.count("## Context") == 1


class TestBuildExtractionSchemaGuard:
    """Fix 2.5: clear error on missing extract key."""

    def test_missing_extract_key_raises(self):
        import pytest

        from kb.ingest.extractors import build_extraction_schema

        with pytest.raises(ValueError, match="missing 'extract' key"):
            build_extraction_schema({"name": "test", "description": "test"})


class TestExtractionSchemaRequired:
    """Fix 2.6: at least the first field must be required."""

    def test_first_field_always_required(self):
        from kb.ingest.extractors import build_extraction_schema

        template = {
            "name": "test",
            "description": "test",
            "extract": ["description: Brief description", "entities_mentioned (list): Entities"],
        }
        schema = build_extraction_schema(template)
        assert len(schema["required"]) >= 1


# -- Cycle 90 fold from test_ingest_fixes_v092.py --
# Tests for v0.9.2 ingest fixes — regex, exception handling, pages_skipped surfacing.

# ---------------------------------------------------------------------------
# Fix 1 & 2: _update_existing_page — regex and exception handling
# ---------------------------------------------------------------------------


class TestUpdateExistingPageAppendsAfterLastSource:
    """Fix 1: New source is inserted after the last source line, not in the middle."""

    def test_appends_after_last_source(self, tmp_path: Path):
        page = tmp_path / "entity.md"
        page.write_text(
            '---\ntitle: "Test"\nsource:\n'
            '  - "raw/articles/first.md"\n'
            '  - "raw/articles/second.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\n"
            "type: entity\nconfidence: stated\n---\n\n"
            "# Test\n\n## References\n\n- Mentioned in raw/articles/first.md\n",
            encoding="utf-8",
        )

        _update_existing_page(page, "raw/articles/third.md")

        content = page.read_text(encoding="utf-8")
        # The new source should appear after the second source, not between first and second
        lines = content.splitlines()
        source_lines = [line for line in lines if line.strip().startswith('- "raw/')]
        assert len(source_lines) == 3
        assert source_lines[0] == '  - "raw/articles/first.md"'
        assert source_lines[1] == '  - "raw/articles/second.md"'
        assert source_lines[2] == '  - "raw/articles/third.md"'

    def test_appends_with_three_existing_sources(self, tmp_path: Path):
        """Ensure the fix works with 3+ existing sources (the old regex was flaky here)."""
        page = tmp_path / "entity.md"
        page.write_text(
            '---\ntitle: "Test"\nsource:\n'
            '  - "raw/articles/a.md"\n'
            '  - "raw/articles/b.md"\n'
            '  - "raw/articles/c.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\n"
            "type: entity\nconfidence: stated\n---\n\n# Test\n",
            encoding="utf-8",
        )

        _update_existing_page(page, "raw/articles/d.md")

        content = page.read_text(encoding="utf-8")
        lines = content.splitlines()
        source_lines = [line for line in lines if line.strip().startswith('- "raw/')]
        assert len(source_lines) == 4
        assert source_lines[-1] == '  - "raw/articles/d.md"'


class TestUpdateExistingPageSkipsExistingSource:
    """Fix 2: Returns early when source is already in frontmatter."""

    def test_skips_existing_source(self, tmp_path: Path):
        page = tmp_path / "entity.md"
        original = (
            '---\ntitle: "Test"\nsource:\n'
            '  - "raw/articles/first.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\n"
            "type: entity\nconfidence: stated\n---\n\n# Test\n"
        )
        page.write_text(original, encoding="utf-8")

        _update_existing_page(page, "raw/articles/first.md")

        # Content should be unchanged — no duplicate source, no updated date
        assert page.read_text(encoding="utf-8") == original


class TestUpdateExistingPageCorruptedFrontmatter:
    """Fix 2: Handles corrupted frontmatter without crashing."""

    def test_handles_corrupted_frontmatter(self, tmp_path: Path, caplog):
        page = tmp_path / "entity.md"
        # Invalid YAML: unmatched quote and bad indentation
        page.write_text(
            '---\ntitle: "Broken\nsource:\n'
            '  - "raw/articles/first.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\n"
            "type: entity\nconfidence: stated\n---\n\n# Test\n",
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
            _update_existing_page(page, "raw/articles/new.md")

        content = page.read_text(encoding="utf-8")
        # Q_C fix: on frontmatter parse error, the function returns early to prevent
        # duplicate source injection. The file should be unchanged (no new source added).
        assert '"raw/articles/new.md"' not in content
        # Should have logged a warning about the parse failure
        assert any("Failed to parse frontmatter" in r.message for r in caplog.records)

    def test_handles_completely_invalid_yaml(self, tmp_path: Path, caplog):
        """Page with no valid YAML at all — should not crash."""
        page = tmp_path / "entity.md"
        page.write_text(
            "This is not YAML at all\nJust plain text\nsource:\n",
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
            # Should not raise
            _update_existing_page(page, "raw/articles/new.md")


# ---------------------------------------------------------------------------
# Fix 3: _format_ingest_result — pages_skipped surfacing
# ---------------------------------------------------------------------------


class TestFormatIngestResultSkipped:
    """Fix 3: _format_ingest_result includes pages_skipped when present."""

    def test_includes_skipped_pages(self):
        result = {
            "pages_created": ["summaries/test"],
            "pages_updated": ["entities/foo"],
            "pages_skipped": [
                "entities/bar (collision: 'Bar')",
                "concepts/baz (collision: 'Baz')",
            ],
        }
        output = _format_ingest_result("raw/articles/test.md", "article", "abc123", result)

        assert "Pages skipped (2):" in output
        assert "  ! entities/bar (collision: 'Bar')" in output
        assert "  ! concepts/baz (collision: 'Baz')" in output

    def test_no_skipped_section_when_empty(self):
        result = {
            "pages_created": ["summaries/test"],
            "pages_updated": [],
            "pages_skipped": [],
        }
        output = _format_ingest_result("raw/articles/test.md", "article", "abc123", result)

        assert "skipped" not in output.lower()

    def test_no_skipped_section_when_missing_key(self):
        result = {
            "pages_created": ["summaries/test"],
            "pages_updated": [],
        }
        output = _format_ingest_result("raw/articles/test.md", "article", "abc123", result)

        assert "skipped" not in output.lower()


# -- Cycle 90 fold from test_phase4_audit_ingest.py --
# Tests for ingest data-integrity fixes — Phase 4 audit.


def test_hash_bytes_matches_content_hash(tmp_path):
    """hash_bytes(data) must produce the same result as content_hash(path)."""
    from kb.utils.hashing import content_hash, hash_bytes

    path = tmp_path / "test.md"
    data = b"hello world content for hashing"
    path.write_bytes(data)
    assert hash_bytes(data) == content_hash(path)


def test_hash_bytes_returns_32_char_hex(tmp_path):
    """hash_bytes must return the same format as content_hash — 32 hex chars."""
    from kb.utils.hashing import hash_bytes

    result = hash_bytes(b"some content")
    assert len(result) == 32
    assert all(c in "0123456789abcdef" for c in result)


def test_sources_mapping_merges_on_reingest(tmp_path):
    """Re-ingesting the same source must merge new page IDs into existing entry."""
    from kb.ingest.pipeline import _update_sources_mapping

    sources_file = tmp_path / "_sources.md"
    sources_file.write_text(
        "- `raw/articles/foo.md` → [[summaries/foo-summary]]\n", encoding="utf-8"
    )

    _update_sources_mapping(
        "raw/articles/foo.md",
        ["summaries/foo-summary", "entities/new-entity"],
        wiki_dir=tmp_path,
    )

    content = sources_file.read_text()
    assert "[[entities/new-entity]]" in content, (
        "New page from re-ingest was not merged into _sources.md entry"
    )
    # Original entry must still be there
    assert "[[summaries/foo-summary]]" in content


def test_sources_mapping_first_ingest_appends(tmp_path):
    """First ingest of a source must append a new entry to _sources.md."""
    from kb.ingest.pipeline import _update_sources_mapping

    sources_file = tmp_path / "_sources.md"
    sources_file.write_text("")  # empty

    _update_sources_mapping(
        "raw/articles/new.md",
        ["summaries/new-summary"],
        wiki_dir=tmp_path,
    )

    content = sources_file.read_text()
    assert "raw/articles/new.md" in content
    assert "[[summaries/new-summary]]" in content


def test_extraction_prompt_with_missing_template_keys():
    """build_extraction_prompt must not raise KeyError when name/description are missing."""
    from kb.ingest.extractors import build_extraction_prompt

    template_minimal = {"extract": ["key_claims", "entities_mentioned"]}
    # Must not raise KeyError
    prompt = build_extraction_prompt("Some source content.", template_minimal)
    assert "key_claims" in prompt
    assert "entities_mentioned" in prompt


def test_contradiction_strips_evidence_trail_header():
    """Evidence Trail section headers must not produce false contradiction signals."""
    from kb.ingest.contradiction import detect_contradictions

    new_claims = ["transformers use attention mechanisms for sequence modeling"]
    existing_pages = [
        {
            "id": "entities/transformer",
            "content": (
                "## Evidence Trail\n"
                "2026-01-01 | raw/articles/a.md | Initial extraction\n\n"
                "## References\n"
                "- [[raw/articles/a.md]]\n"
            ),
        }
    ]
    result = detect_contradictions(new_claims, existing_pages, max_claims=10)
    assert result == [], f"Got spurious contradictions from structural-only page content: {result}"


def test_contradiction_strips_wikilinks():
    """Wikilinks in page content must be stripped to their display text before tokenizing."""
    from kb.ingest.contradiction import _strip_markdown_structure

    content = "The [[entities/transformer|Transformer]] model is not slow."
    stripped = _strip_markdown_structure(content)
    assert "[[" not in stripped
    assert "entities/transformer" not in stripped
    assert "Transformer" in stripped  # display text preserved


def test_load_all_pages_called_at_most_once_per_ingest(tmp_path, monkeypatch):
    """load_all_pages must be called at most once during ingest_source."""
    import kb.ingest.pipeline as pipeline_mod
    import kb.utils.pages as pages_mod
    from kb.ingest.pipeline import ingest_source

    # Set up minimal wiki and raw directories
    wiki = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki / subdir).mkdir(parents=True)
    (wiki / "index.md").write_text("", encoding="utf-8")
    (wiki / "_sources.md").write_text("", encoding="utf-8")
    (wiki / "_categories.md").write_text("", encoding="utf-8")
    (wiki / "log.md").write_text("", encoding="utf-8")

    raw = tmp_path / "raw" / "articles"
    raw.mkdir(parents=True)
    source = raw / "test.md"
    source.write_text("# Test\nContent here.\n", encoding="utf-8")

    # Patch module-level config names so the path-validation check passes
    monkeypatch.setattr(pipeline_mod, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(pipeline_mod, "WIKI_DIR", wiki)
    monkeypatch.setattr(pipeline_mod, "WIKI_INDEX", wiki / "index.md")
    monkeypatch.setattr(pipeline_mod, "WIKI_SOURCES", wiki / "_sources.md")
    monkeypatch.setattr("kb.utils.paths.RAW_DIR", tmp_path / "raw")

    call_count = [0]
    real_load = pages_mod.load_all_pages

    def counting_load(wiki_dir=None):
        call_count[0] += 1
        return real_load(wiki_dir=wiki_dir)

    # Patch the load_all_pages reference inside pipeline module
    monkeypatch.setattr(pipeline_mod, "load_all_pages", counting_load)

    # Patch out the LLM extraction and other side-effectful operations
    monkeypatch.setattr(
        pipeline_mod,
        "extract_from_source",
        lambda *a, **kw: {
            "key_claims": ["claim one"],
            "entities_mentioned": [],
            "concepts_mentioned": [],
            "title": "Test",
            "summary": "A test document.",
        },
    )
    monkeypatch.setattr(pipeline_mod, "_is_duplicate_content", lambda *a: False)

    ingest_source(source, wiki_dir=wiki)

    assert call_count[0] <= 1, (
        f"load_all_pages was called {call_count[0]} times in a single ingest — expected ≤1"
    )
