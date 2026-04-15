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

    # Patch config paths to use temp directory
    with (
        patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
        patch("kb.utils.paths.RAW_DIR", raw_dir),
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
        patch("kb.utils.wiki_log.WIKI_LOG", wiki_dir / "log.md"),
        # fix item 1: sandbox WIKI_CONTRADICTIONS so prod file is not mutated
        patch("kb.ingest.pipeline.WIKI_CONTRADICTIONS", wiki_dir / "contradictions.md"),
    ):
        result = ingest_source(source, source_type="article")

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

    with (
        patch("kb.ingest.pipeline.RAW_DIR", raw_dir),
        patch("kb.utils.paths.RAW_DIR", raw_dir),
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
        patch("kb.utils.wiki_log.WIKI_LOG", wiki_dir / "log.md"),
        patch("kb.ingest.pipeline.WIKI_CONTRADICTIONS", tmp_contradictions),  # fix item 1
    ):
        ingest_source(source, source_type="article")

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
        patch("kb.utils.wiki_log.WIKI_LOG", wiki_dir / "log.md"),
        patch("kb.ingest.pipeline.WIKI_CONTRADICTIONS", wiki_dir / "contradictions.md"),
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
