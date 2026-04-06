"""Tests for v0.9.0 hardening — path traversal rejection, citation regex fix,
slug collision tracking, JSON fence hardening, MCP error handling,
max_results bounds, MCP instructions update, SDK retry fix, wikilink normalization."""

from unittest.mock import patch

# ── 1. Path Traversal Rejection ──────────────────────────────────


def test_validate_page_id_rejects_dot_dot():
    """_validate_page_id rejects '..' in page_id."""
    from kb.mcp.app import _validate_page_id

    result = _validate_page_id("../../etc/passwd")
    assert result is not None
    assert "Invalid" in result


def test_validate_page_id_rejects_absolute_path():
    """_validate_page_id rejects page_id starting with '/'."""
    from kb.mcp.app import _validate_page_id

    result = _validate_page_id("/etc/passwd")
    assert result is not None
    assert "Invalid" in result


def test_validate_page_id_rejects_backslash_start():
    """_validate_page_id rejects page_id starting with '\\'."""
    from kb.mcp.app import _validate_page_id

    result = _validate_page_id("\\windows\\system32")
    assert result is not None
    assert "Invalid" in result


def test_validate_page_id_allows_valid(tmp_path):
    """_validate_page_id allows normal page IDs when page exists."""
    from kb.mcp.app import _validate_page_id

    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "rag.md").write_text("content")

    with patch("kb.mcp.app.WIKI_DIR", wiki):
        result = _validate_page_id("concepts/rag")
    assert result is None


def test_validate_page_id_not_found(tmp_path):
    """_validate_page_id returns 'not found' for valid but missing page IDs."""
    from kb.mcp.app import _validate_page_id

    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)

    with patch("kb.mcp.app.WIKI_DIR", wiki):
        result = _validate_page_id("concepts/nonexistent")
    assert result is not None
    assert "not found" in result.lower()


def test_kb_read_page_rejects_traversal(tmp_path):
    """kb_read_page rejects path traversal attempts."""
    from kb.mcp.browse import kb_read_page

    wiki = tmp_path / "wiki"
    wiki.mkdir(parents=True)
    with patch("kb.mcp.browse.WIKI_DIR", wiki):
        result = kb_read_page("../../../etc/passwd")
    assert "Error" in result or "Invalid" in result


def test_kb_read_page_rejects_absolute(tmp_path):
    """kb_read_page rejects absolute path attempts."""
    from kb.mcp.browse import kb_read_page

    wiki = tmp_path / "wiki"
    wiki.mkdir(parents=True)
    with patch("kb.mcp.browse.WIKI_DIR", wiki):
        result = kb_read_page("/etc/passwd")
    assert "Error" in result or "Invalid" in result


def test_kb_create_page_rejects_traversal(tmp_path):
    """kb_create_page rejects '..' in page_id."""
    from kb.mcp.quality import kb_create_page

    wiki = tmp_path / "wiki"
    wiki.mkdir(parents=True)
    with patch("kb.mcp.quality.WIKI_DIR", wiki):
        result = kb_create_page(
            "../evil/page", "Evil", "content", "concept"
        )
    assert "Error" in result
    assert "Invalid" in result


# ── 2. Citation Regex Fix ────────────────────────────────────────


def test_citation_regex_matches_underscores():
    """Citation pattern now matches page IDs with underscores."""
    from kb.query.citations import extract_citations

    text = "As noted in [source: concepts/machine_learning], this is important."
    cites = extract_citations(text)
    assert len(cites) == 1
    assert cites[0]["path"] == "concepts/machine_learning"


def test_citation_regex_matches_nested_underscores():
    """Citation pattern matches deeply nested underscore paths."""
    from kb.query.citations import extract_citations

    text = "See [ref: raw/articles/deep_learning_intro.md] for details."
    cites = extract_citations(text)
    assert len(cites) == 1
    assert cites[0]["path"] == "raw/articles/deep_learning_intro.md"


def test_citation_regex_still_matches_hyphens():
    """Citation pattern still works with hyphenated paths (regression test)."""
    from kb.query.citations import extract_citations

    text = "[source: concepts/rag-vs-fine-tuning]"
    cites = extract_citations(text)
    assert len(cites) == 1
    assert cites[0]["path"] == "concepts/rag-vs-fine-tuning"


def test_citation_regex_mixed_underscore_hyphen():
    """Citation pattern matches paths with both underscores and hyphens."""
    from kb.query.citations import extract_citations

    text = "[source: entities/open_ai-gpt]"
    cites = extract_citations(text)
    assert len(cites) == 1
    assert cites[0]["path"] == "entities/open_ai-gpt"


# ── 3. Slug Collision Tracking ───────────────────────────────────


def test_ingest_tracks_skipped_slug_collisions(tmp_path):
    """ingest_source returns pages_skipped for slug collisions."""
    from kb.ingest.pipeline import ingest_source

    # Set up project structure
    wiki = tmp_path / "wiki"
    for sub in ("summaries", "entities", "concepts"):
        (wiki / sub).mkdir(parents=True)
    raw = tmp_path / "raw" / "articles"
    raw.mkdir(parents=True)
    source = raw / "test.md"
    source.write_text("Test content about collisions")

    # Create index files
    (wiki / "index.md").write_text(
        "# Index\n\n## Summaries\n\n## Entities\n\n## Concepts\n\n"
        "## Comparisons\n\n## Synthesis\n\n"
    )
    (wiki / "_sources.md").write_text("# Sources\n\n")
    (wiki / "log.md").write_text("# Log\n\n")

    # Extraction with slug collisions: "GPT 4" and "GPT-4" both → "gpt-4"
    extraction = {
        "title": "Collision Test",
        "entities_mentioned": ["GPT 4", "GPT-4"],
        "concepts_mentioned": ["Fine Tuning", "Fine-Tuning"],
    }

    with (
        patch("kb.ingest.pipeline.WIKI_DIR", wiki),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki / "_sources.md"),
        patch("kb.utils.wiki_log.WIKI_LOG", wiki / "log.md"),
        patch("kb.ingest.pipeline.RAW_DIR", tmp_path / "raw"),
    ):
        result = ingest_source(source, "article", extraction=extraction)

    assert "pages_skipped" in result
    assert len(result["pages_skipped"]) == 2  # One entity + one concept collision
    assert any("gpt-4" in s for s in result["pages_skipped"])
    assert any("fine-tuning" in s for s in result["pages_skipped"])


def test_ingest_no_skipped_without_collisions(tmp_path):
    """ingest_source returns empty pages_skipped when no collisions."""
    from kb.ingest.pipeline import ingest_source

    wiki = tmp_path / "wiki"
    for sub in ("summaries", "entities", "concepts"):
        (wiki / sub).mkdir(parents=True)
    raw = tmp_path / "raw" / "articles"
    raw.mkdir(parents=True)
    source = raw / "test.md"
    source.write_text("Test content")

    (wiki / "index.md").write_text(
        "# Index\n\n## Summaries\n\n## Entities\n\n## Concepts\n\n"
        "## Comparisons\n\n## Synthesis\n\n"
    )
    (wiki / "_sources.md").write_text("# Sources\n\n")
    (wiki / "log.md").write_text("# Log\n\n")

    extraction = {
        "title": "No Collision",
        "entities_mentioned": ["OpenAI", "Google"],
        "concepts_mentioned": ["RAG", "LLM"],
    }

    with (
        patch("kb.ingest.pipeline.WIKI_DIR", wiki),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki / "_sources.md"),
        patch("kb.utils.wiki_log.WIKI_LOG", wiki / "log.md"),
        patch("kb.ingest.pipeline.RAW_DIR", tmp_path / "raw"),
    ):
        result = ingest_source(source, "article", extraction=extraction)

    assert result["pages_skipped"] == []


# ── 4. JSON Fence Hardening ──────────────────────────────────────


def test_fence_strip_normal():
    """Standard ```json ... ``` fencing is stripped."""
    from kb.ingest.extractors import extract_from_source

    response_text = '```json\n{"title": "Test"}\n```'
    with patch("kb.ingest.extractors.call_llm", return_value=response_text):
        result = extract_from_source("content", "article")
    assert result["title"] == "Test"


def test_fence_strip_no_newline():
    """Single-line ```json{...}``` without newline is handled."""
    from kb.ingest.extractors import extract_from_source

    response_text = '```json{"title": "Test"}```'
    with patch("kb.ingest.extractors.call_llm", return_value=response_text):
        result = extract_from_source("content", "article")
    assert result["title"] == "Test"


def test_fence_strip_bare_backticks():
    """Bare ``` ... ``` without json label is handled."""
    from kb.ingest.extractors import extract_from_source

    response_text = '```\n{"title": "Test"}\n```'
    with patch("kb.ingest.extractors.call_llm", return_value=response_text):
        result = extract_from_source("content", "article")
    assert result["title"] == "Test"


def test_fence_strip_no_fence():
    """Plain JSON without fences works."""
    from kb.ingest.extractors import extract_from_source

    response_text = '{"title": "Test"}'
    with patch("kb.ingest.extractors.call_llm", return_value=response_text):
        result = extract_from_source("content", "article")
    assert result["title"] == "Test"


def test_fence_strip_single_line_bare():
    """Single-line ```{...}``` without json label."""
    from kb.ingest.extractors import extract_from_source

    response_text = '```{"title": "Test"}```'
    with patch("kb.ingest.extractors.call_llm", return_value=response_text):
        result = extract_from_source("content", "article")
    assert result["title"] == "Test"


# ── 5. MCP Error Handling ────────────────────────────────────────


def test_kb_stats_returns_error_on_failure(tmp_path):
    """kb_stats returns error string instead of crashing."""
    from kb.mcp.browse import kb_stats

    with patch("kb.evolve.analyzer.analyze_coverage", side_effect=RuntimeError("graph corrupted")):
        result = kb_stats()
    assert "Error" in result
    assert "graph corrupted" in result


def test_kb_lint_returns_error_on_failure():
    """kb_lint returns error string instead of crashing."""
    from kb.mcp.health import kb_lint

    with patch("kb.lint.runner.run_all_checks", side_effect=RuntimeError("check failed")):
        result = kb_lint()
    assert "Error" in result
    assert "check failed" in result


def test_kb_evolve_returns_error_on_failure():
    """kb_evolve returns error string instead of crashing."""
    from kb.mcp.health import kb_evolve

    with patch(
        "kb.evolve.analyzer.generate_evolution_report",
        side_effect=RuntimeError("analysis failed"),
    ):
        result = kb_evolve()
    assert "Error" in result
    assert "analysis failed" in result


def test_kb_compile_scan_returns_error_on_failure():
    """kb_compile_scan returns error string instead of crashing."""
    from kb.mcp.core import kb_compile_scan

    with patch(
        "kb.compile.compiler.find_changed_sources",
        side_effect=RuntimeError("manifest corrupted"),
    ):
        result = kb_compile_scan()
    assert "Error" in result
    assert "manifest corrupted" in result


def test_kb_lint_consistency_returns_error_on_failure():
    """kb_lint_consistency returns error string on crash."""
    from kb.mcp.quality import kb_lint_consistency

    with patch(
        "kb.lint.semantic.build_consistency_context",
        side_effect=RuntimeError("context build failed"),
    ):
        result = kb_lint_consistency("concepts/a,concepts/b")
    assert "Error" in result


def test_kb_affected_pages_returns_error_on_failure():
    """kb_affected_pages returns error string on crash."""
    from kb.mcp.quality import kb_affected_pages

    with patch(
        "kb.compile.linker.build_backlinks",
        side_effect=RuntimeError("linker failed"),
    ):
        result = kb_affected_pages("concepts/rag")
    assert "Error" in result


# ── 6. max_results Bounds ────────────────────────────────────────


def test_kb_query_clamps_max_results_low(tmp_path):
    """kb_query clamps max_results to minimum 1."""
    from kb.mcp.core import kb_query

    with patch("kb.query.engine.search_pages", return_value=[]) as mock:
        kb_query("test question", max_results=-5)
    mock.assert_called_once_with("test question", max_results=1)


def test_kb_query_clamps_max_results_high(tmp_path):
    """kb_query clamps max_results to maximum 100."""
    from kb.mcp.core import kb_query

    with patch("kb.query.engine.search_pages", return_value=[]) as mock:
        kb_query("test question", max_results=9999)
    mock.assert_called_once_with("test question", max_results=100)


def test_kb_search_clamps_max_results_low():
    """kb_search clamps max_results to minimum 1."""
    from kb.mcp.browse import kb_search

    with patch("kb.query.engine.search_pages", return_value=[]) as mock:
        kb_search("test", max_results=0)
    mock.assert_called_once_with("test", max_results=1)


def test_kb_search_clamps_max_results_high():
    """kb_search clamps max_results to maximum 100."""
    from kb.mcp.browse import kb_search

    with patch("kb.query.engine.search_pages", return_value=[]) as mock:
        kb_search("test", max_results=500)
    mock.assert_called_once_with("test", max_results=100)


def test_kb_query_normal_max_results():
    """kb_query passes through valid max_results unchanged."""
    from kb.mcp.core import kb_query

    with patch("kb.query.engine.search_pages", return_value=[]) as mock:
        kb_query("test question", max_results=25)
    mock.assert_called_once_with("test question", max_results=25)


# ── 7. MCP Instructions Update ──────────────────────────────────


def test_mcp_instructions_include_phase2_tools():
    """MCP server instructions mention Phase 2 quality tools."""
    from kb.mcp.app import mcp

    instructions = mcp.instructions
    assert "kb_review_page" in instructions
    assert "kb_refine_page" in instructions
    assert "kb_lint_deep" in instructions
    assert "kb_query_feedback" in instructions
    assert "kb_reliability_map" in instructions
    assert "kb_affected_pages" in instructions
    assert "kb_save_lint_verdict" in instructions
    assert "kb_create_page" in instructions


# ── 8. Format Ingest Result with pages_skipped ───────────────────


def test_format_ingest_result_handles_missing_skipped():
    """_format_ingest_result works with result dicts lacking pages_skipped."""
    from kb.mcp.app import _format_ingest_result

    result = {
        "pages_created": ["summaries/test"],
        "pages_updated": [],
    }
    text = _format_ingest_result("raw/articles/test.md", "article", "abc123", result)
    assert "summaries/test" in text


# ── 9. SDK Retry Fix (Context7) ──────────────────────────────────


def test_anthropic_client_disables_sdk_retries():
    """Anthropic client has max_retries=0 to avoid double retry."""
    import kb.utils.llm as llm_mod
    from kb.utils.llm import get_client

    old_client = llm_mod._client
    llm_mod._client = None
    try:
        client = get_client()
        assert client.max_retries == 0
    finally:
        llm_mod._client = old_client


# ── 10. Wikilink Normalization Consistency (Context7) ─────────────


def test_extract_wikilinks_already_strips_md():
    """extract_wikilinks strips .md suffix — linker/graph should not double-strip."""
    from kb.utils.markdown import extract_wikilinks

    text = "See [[concepts/rag.md]] and [[entities/openai]]"
    links = extract_wikilinks(text)
    assert "concepts/rag" in links
    assert "entities/openai" in links
    # Verify .md is already stripped (no double stripping needed)
    assert all(not link.endswith(".md") for link in links)


def test_extract_wikilinks_lowercases():
    """extract_wikilinks lowercases targets for case-insensitive matching."""
    from kb.utils.markdown import extract_wikilinks

    text = "See [[Concepts/RAG]] and [[Entities/OpenAI]]"
    links = extract_wikilinks(text)
    assert "concepts/rag" in links
    assert "entities/openai" in links


def test_linker_resolve_uses_normalized_links(tmp_wiki, create_wiki_page):
    """Linker resolves wikilinks correctly with normalized (lowered, no .md) IDs."""
    from kb.compile.linker import resolve_wikilinks

    create_wiki_page("concepts/rag", wiki_dir=tmp_wiki, content="See [[entities/openai]]")
    create_wiki_page("entities/openai", wiki_dir=tmp_wiki, content="An entity.")

    result = resolve_wikilinks(tmp_wiki)
    assert result["resolved"] == 1
    assert result["broken"] == []


def test_graph_edges_match_normalized_links(tmp_wiki, create_wiki_page):
    """Graph builder creates edges using normalized wikilink targets."""
    from kb.graph.builder import build_graph

    create_wiki_page("concepts/rag", wiki_dir=tmp_wiki, content="See [[concepts/llm]]")
    create_wiki_page("concepts/llm", wiki_dir=tmp_wiki, content="An LLM concept.")

    graph = build_graph(tmp_wiki)
    assert graph.has_edge("concepts/rag", "concepts/llm")
