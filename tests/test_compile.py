"""Tests for the compile module."""

from pathlib import Path
from unittest.mock import patch

from kb.compile.compiler import (
    compile_wiki,
    find_changed_sources,
    load_manifest,
    save_manifest,
    scan_raw_sources,
)
from kb.compile.linker import build_backlinks, resolve_wikilinks

# ── Compiler tests ──────────────────────────────────────────────


def test_load_manifest_empty(tmp_path):
    """load_manifest returns empty dict when file doesn't exist."""
    result = load_manifest(tmp_path / "nonexistent.json")
    assert result == {}


def test_save_and_load_manifest(tmp_path):
    """save_manifest + load_manifest round-trips correctly."""
    manifest_path = tmp_path / "hashes.json"
    manifest = {"raw/articles/test.md": "abc123def456"}
    save_manifest(manifest, manifest_path)
    loaded = load_manifest(manifest_path)
    assert loaded == manifest


def test_scan_raw_sources(tmp_path):
    """scan_raw_sources finds markdown files in raw subdirectories."""
    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    (articles / "test1.md").write_text("content 1")
    (articles / "test2.md").write_text("content 2")
    (articles / ".gitkeep").write_text("")

    papers = raw_dir / "papers"
    papers.mkdir(parents=True)
    (papers / "paper1.md").write_text("paper content")

    sources = scan_raw_sources(raw_dir)
    assert len(sources) == 3
    names = [s.name for s in sources]
    assert "test1.md" in names
    assert "test2.md" in names
    assert "paper1.md" in names
    assert ".gitkeep" not in names


def test_scan_raw_sources_empty(tmp_path):
    """scan_raw_sources returns empty list for empty raw directory."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    sources = scan_raw_sources(raw_dir)
    assert sources == []


def test_find_changed_sources(tmp_path):
    """find_changed_sources detects new and modified files."""
    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    (articles / "existing.md").write_text("original content")
    (articles / "new.md").write_text("new content")

    manifest_path = tmp_path / "hashes.json"
    # Manifest uses canonical relative paths (raw/articles/existing.md)
    manifest = {"raw/articles/existing.md": "oldhash12345678"}
    save_manifest(manifest, manifest_path)

    new, changed = find_changed_sources(raw_dir, manifest_path)
    assert len(new) == 1
    assert new[0].name == "new.md"
    assert len(changed) == 1
    assert changed[0].name == "existing.md"


@patch("kb.compile.compiler.ingest_source")
def test_compile_wiki_incremental(mock_ingest, tmp_path):
    """compile_wiki in incremental mode only processes new/changed sources."""
    mock_ingest.return_value = {
        "source_path": "test",
        "source_type": "article",
        "content_hash": "abc123",
        "pages_created": ["summaries/test"],
        "pages_updated": [],
    }

    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    (articles / "test.md").write_text("test content")

    manifest_path = tmp_path / "hashes.json"
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    log_path = wiki_dir / "log.md"
    log_path.write_text("---\ntitle: Log\nupdated: 2026-04-06\n---\n\n# Log\n")

    with patch("kb.utils.wiki_log.WIKI_LOG", log_path):
        result = compile_wiki(incremental=True, raw_dir=raw_dir, manifest_path=manifest_path)

    assert result["mode"] == "incremental"
    assert result["sources_processed"] == 1
    assert "summaries/test" in result["pages_created"]
    mock_ingest.assert_called_once()

    # Manifest should be saved
    assert manifest_path.exists()


@patch("kb.compile.compiler.ingest_source")
def test_compile_wiki_full(mock_ingest, tmp_path):
    """compile_wiki in full mode processes all sources."""
    mock_ingest.return_value = {
        "source_path": "test",
        "source_type": "article",
        "content_hash": "abc123",
        "pages_created": ["summaries/test"],
        "pages_updated": [],
    }

    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    (articles / "test.md").write_text("test content")

    manifest_path = tmp_path / "hashes.json"
    # Even with existing manifest, full recompiles everything
    save_manifest({"old": "hash"}, manifest_path)

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    log_path = wiki_dir / "log.md"
    log_path.write_text("---\ntitle: Log\nupdated: 2026-04-06\n---\n\n# Log\n")

    with patch("kb.utils.wiki_log.WIKI_LOG", log_path):
        result = compile_wiki(incremental=False, raw_dir=raw_dir, manifest_path=manifest_path)

    assert result["mode"] == "full"
    assert result["sources_processed"] == 1


# ── Linker tests ────────────────────────────────────────────────


def _create_page(path: Path, title: str, content: str, page_type: str = "concept") -> None:
    """Helper to create a wiki page with frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        f'---\ntitle: "{title}"\nsource:\n  - raw/articles/test.md\n'
        f"created: 2026-04-06\nupdated: 2026-04-06\ntype: {page_type}\n"
        f"confidence: stated\n---\n\n"
    )
    path.write_text(fm + content, encoding="utf-8")


def test_resolve_wikilinks(tmp_wiki):
    """resolve_wikilinks finds resolved and broken links."""
    _create_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "Links to [[concepts/llm]] and [[entities/nonexistent]].",
    )
    _create_page(tmp_wiki / "concepts" / "llm.md", "LLM", "LLM content.")
    result = resolve_wikilinks(tmp_wiki)
    assert result["total_links"] == 2
    assert result["resolved"] == 1
    assert len(result["broken"]) == 1
    assert result["broken"][0]["target"] == "entities/nonexistent"


def test_resolve_wikilinks_all_valid(tmp_wiki):
    """resolve_wikilinks reports all resolved when no broken links."""
    _create_page(tmp_wiki / "concepts" / "rag.md", "RAG", "Links to [[concepts/llm]].")
    _create_page(tmp_wiki / "concepts" / "llm.md", "LLM", "Links to [[concepts/rag]].")
    result = resolve_wikilinks(tmp_wiki)
    assert result["total_links"] == 2
    assert result["resolved"] == 2
    assert result["broken"] == []


def test_build_backlinks(tmp_wiki):
    """build_backlinks creates reverse link index."""
    _create_page(
        tmp_wiki / "summaries" / "article1.md",
        "Article 1",
        "Mentions [[concepts/rag]] and [[entities/openai]].",
        page_type="summary",
    )
    _create_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "RAG is linked from summaries.",
    )
    _create_page(
        tmp_wiki / "entities" / "openai.md",
        "OpenAI",
        "OpenAI content.",
        page_type="entity",
    )
    backlinks = build_backlinks(tmp_wiki)
    assert "concepts/rag" in backlinks
    assert "summaries/article1" in backlinks["concepts/rag"]
    assert "entities/openai" in backlinks
    assert "summaries/article1" in backlinks["entities/openai"]


def test_build_backlinks_empty(tmp_wiki):
    """build_backlinks returns empty dict for empty wiki."""
    backlinks = build_backlinks(tmp_wiki)
    assert backlinks == {}
