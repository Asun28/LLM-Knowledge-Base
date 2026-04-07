"""Tests for v0.9.3 fixes — manifest safety, kb_compile tool, MAX_SEARCH_RESULTS config."""

from unittest.mock import patch

from kb.compile.compiler import compile_wiki, load_manifest
from kb.mcp.core import kb_compile

# ── Fix 1: Manifest not saved when ingest raises ─────────────────


def test_compile_manifest_not_saved_on_error(tmp_path):
    """When ingest_source raises, the manifest must NOT record that source."""
    # Create a raw source file
    raw_dir = tmp_path / "raw"
    articles_dir = raw_dir / "articles"
    articles_dir.mkdir(parents=True)
    source = articles_dir / "test-fail.md"
    source.write_text("# Test Article\nContent here.")

    # Create wiki dir structure
    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True)
    (wiki_dir / "log.md").write_text("# Log\n")

    manifest_path = tmp_path / "hashes.json"

    with (
        patch("kb.compile.compiler.ingest_source", side_effect=RuntimeError("LLM failed")),
        patch("kb.compile.compiler.RAW_DIR", raw_dir),
        patch("kb.compile.compiler.SOURCE_TYPE_DIRS", {"article": articles_dir}),
        patch("kb.compile.compiler.append_wiki_log"),
    ):
        result = compile_wiki(incremental=False, raw_dir=raw_dir, manifest_path=manifest_path)

    assert len(result["errors"]) == 1
    assert "LLM failed" in result["errors"][0]["error"]
    manifest = load_manifest(manifest_path)
    # The source should NOT be in the manifest since ingest failed
    source_keys = [k for k in manifest if not k.startswith("_template/")]
    assert not any("test-fail.md" in k for k in source_keys)


def test_compile_manifest_saved_on_success(tmp_path):
    """When ingest_source succeeds, the manifest MUST record the source hash."""
    # Create a raw source file
    raw_dir = tmp_path / "raw"
    articles_dir = raw_dir / "articles"
    articles_dir.mkdir(parents=True)
    source = articles_dir / "test-ok.md"
    source.write_text("# Test Article\nContent here.")

    # Create wiki dir structure
    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True)
    (wiki_dir / "log.md").write_text("# Log\n")

    manifest_path = tmp_path / "hashes.json"

    mock_result = {
        "source_path": str(source),
        "source_type": "article",
        "content_hash": "abc123",
        "pages_created": ["summaries/test-ok"],
        "pages_updated": [],
        "pages_skipped": [],
    }

    with (
        patch("kb.compile.compiler.ingest_source", return_value=mock_result),
        patch("kb.compile.compiler.RAW_DIR", raw_dir),
        patch("kb.compile.compiler.SOURCE_TYPE_DIRS", {"article": articles_dir}),
        patch("kb.compile.compiler.append_wiki_log"),
    ):
        result = compile_wiki(incremental=False, raw_dir=raw_dir, manifest_path=manifest_path)

    assert result["sources_processed"] == 1
    assert result["pages_created"] == ["summaries/test-ok"]
    manifest = load_manifest(manifest_path)
    source_keys = [k for k in manifest if not k.startswith("_template/")]
    assert any("test-ok.md" in k for k in source_keys)


# ── Fix 2: kb_compile MCP tool ──────────────────────────────────


def test_kb_compile_tool_exists():
    """kb_compile is importable from kb.mcp.core."""
    from kb.mcp.core import kb_compile as imported_fn

    assert callable(imported_fn)


def test_kb_compile_incremental():
    """kb_compile returns formatted output for a successful incremental compile."""
    mock_result = {
        "mode": "incremental",
        "sources_processed": 2,
        "pages_created": ["summaries/alpha", "entities/beta"],
        "pages_updated": ["concepts/gamma"],
        "errors": [],
    }

    with patch("kb.compile.compiler.compile_wiki", return_value=mock_result):
        output = kb_compile(incremental=True)

    assert "Compile Complete (incremental)" in output
    assert "Sources processed:** 2" in output
    assert "Pages created:** 2" in output
    assert "Pages updated:** 1" in output
    assert "summaries/alpha" in output
    assert "entities/beta" in output
    assert "concepts/gamma" in output


def test_kb_compile_full_mode():
    """kb_compile returns formatted output for a full compile."""
    mock_result = {
        "mode": "full",
        "sources_processed": 3,
        "pages_created": ["summaries/one", "summaries/two", "summaries/three"],
        "pages_updated": [],
        "errors": [],
    }

    with patch("kb.compile.compiler.compile_wiki", return_value=mock_result):
        output = kb_compile(incremental=False)

    assert "Compile Complete (full)" in output
    assert "Sources processed:** 3" in output
    assert "Pages created:** 3" in output


def test_kb_compile_with_errors():
    """kb_compile includes error details in output."""
    mock_result = {
        "mode": "incremental",
        "sources_processed": 1,
        "pages_created": ["summaries/ok"],
        "pages_updated": [],
        "errors": [{"source": "raw/articles/bad.md", "error": "Parse failure"}],
    }

    with patch("kb.compile.compiler.compile_wiki", return_value=mock_result):
        output = kb_compile(incremental=True)

    assert "Errors (1)" in output
    assert "raw/articles/bad.md" in output
    assert "Parse failure" in output


def test_kb_compile_error_handling():
    """kb_compile returns error string when compile_wiki raises."""
    with patch("kb.compile.compiler.compile_wiki", side_effect=RuntimeError("DB locked")):
        output = kb_compile(incremental=True)

    assert output.startswith("Error running compile:")
    assert "DB locked" in output


def test_kb_compile_empty_results():
    """kb_compile handles zero sources gracefully."""
    mock_result = {
        "mode": "incremental",
        "sources_processed": 0,
        "pages_created": [],
        "pages_updated": [],
        "errors": [],
    }

    with patch("kb.compile.compiler.compile_wiki", return_value=mock_result):
        output = kb_compile(incremental=True)

    assert "Compile Complete (incremental)" in output
    assert "Sources processed:** 0" in output
    assert "Created" not in output
    assert "Updated" not in output


# ── Fix 3: MAX_SEARCH_RESULTS config constant ───────────────────


def test_max_search_results_config():
    """MAX_SEARCH_RESULTS is importable from kb.config and equals 100."""
    from kb.config import MAX_SEARCH_RESULTS

    assert MAX_SEARCH_RESULTS == 100


def test_max_search_results_used_in_kb_query():
    """kb_query uses MAX_SEARCH_RESULTS from config for clamping."""
    from kb.mcp.core import kb_query

    # Verify the function uses MAX_SEARCH_RESULTS by checking that it caps at 100
    # We mock search_pages to capture the max_results value passed
    with patch("kb.query.engine.search_pages", return_value=[]) as mock_search:
        kb_query("test question", max_results=200)
        call_args = mock_search.call_args
        assert call_args[1]["max_results"] == 100

    with patch("kb.query.engine.search_pages", return_value=[]) as mock_search:
        kb_query("test question", max_results=0)
        call_args = mock_search.call_args
        assert call_args[1]["max_results"] == 1


def test_max_search_results_used_in_kb_search():
    """kb_search uses MAX_SEARCH_RESULTS from config for clamping."""
    from kb.mcp.browse import kb_search

    with patch("kb.query.engine.search_pages", return_value=[]) as mock_search:
        kb_search("test query", max_results=999)
        call_args = mock_search.call_args
        assert call_args[1]["max_results"] == 100

    with patch("kb.query.engine.search_pages", return_value=[]) as mock_search:
        kb_search("test query", max_results=-5)
        call_args = mock_search.call_args
        assert call_args[1]["max_results"] == 1
