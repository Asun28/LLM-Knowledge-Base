"""Tests for the ingest pipeline."""

from unittest.mock import patch

import pytest

from kb.ingest.extractors import build_extraction_prompt, extract_from_source, load_template
from kb.ingest.pipeline import detect_source_type, ingest_source
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
def test_ingest_source(mock_extract, tmp_path):
    """ingest_source creates summary, entity, and concept pages."""
    mock_extract.return_value = {
        "title": "Test Article",
        "author": "John Doe",
        "core_argument": "Testing is important.",
        "key_claims": ["Claim 1", "Claim 2"],
        "entities_mentioned": ["John Doe", "OpenAI"],
        "concepts_mentioned": ["Testing", "RAG"],
    }

    # Set up temporary directory structure
    raw_dir = tmp_path / "raw"
    articles_dir = raw_dir / "articles"
    articles_dir.mkdir(parents=True)
    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True)

    # Create index files
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

    # Create source file
    source = articles_dir / "test-article.md"
    source.write_text("# Test Article\n\nThis is a test article about testing and RAG.")

    # Create contradictions file so the patch target exists
    (wiki_dir / "contradictions.md").touch()

    # H6 fix: WIKI_CONTRADICTIONS removed from pipeline; path derived from effective_wiki_dir.
    with (
        patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
        patch("kb.utils.paths.RAW_DIR", raw_dir),
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
    ):
        result = ingest_source(source, source_type="article", wiki_dir=wiki_dir)

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
    monkeypatch.setattr(pipeline, "_is_duplicate_content", lambda *_: True)

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
            source_path=source, wiki_dir=wiki_dir, extraction=extraction,
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
            source_path=source, wiki_dir=wiki_dir, extraction=extraction,
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
            source_path=source, wiki_dir=wiki_dir,
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
