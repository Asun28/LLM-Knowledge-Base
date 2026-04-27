"""Tests for the ingest pipeline."""

import json
import threading
from unittest.mock import patch

import pytest

from kb.ingest.extractors import build_extraction_prompt, extract_from_source, load_template
from kb.ingest.pipeline import (
    _build_summary_content,
    _coerce_str_field,
    _extract_entity_context,
    detect_source_type,
    ingest_source,
)
from kb.mcp import core as mcp_core
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


def test_persist_contradictions_concurrent(tmp_path):
    """Regression: Phase 4.5 HIGH item H3 (_persist_contradictions concurrent RMW).

    Two threads writing different contradiction payloads concurrently must both
    appear in the final contradictions.md.
    """
    from kb.ingest.pipeline import _persist_contradictions

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    errors: list[Exception] = []

    def _write(source_ref: str, claim: str) -> None:
        try:
            _persist_contradictions(
                [{"claim": claim}],
                source_ref,
                wiki_dir,
            )
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_write, args=("raw/articles/src-a.md", "claim-from-thread-one"))
    t2 = threading.Thread(target=_write, args=("raw/articles/src-b.md", "claim-from-thread-two"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

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


# ── Cycle 10 AC22 — _coerce_str_field type-rejection contract (folded from test_cycle10_extraction_validation.py) ─


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
