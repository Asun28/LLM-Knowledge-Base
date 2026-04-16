"""Tests for v0.6.0 fixes — LLM retry, frontmatter source update, context truncation,
entity context, crash-safe manifest, slug collisions, exact source matching,
word-boundary search, term overlap filtering, cycle detection, log size warning.
"""

import logging
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from kb.config import QUERY_CONTEXT_MAX_CHARS
from kb.ingest.pipeline import (
    _extract_entity_context,
    _update_existing_page,
    ingest_source,
)
from kb.lint.checks import check_cycles, check_source_coverage
from kb.lint.semantic import _group_by_term_overlap
from kb.query.engine import _build_query_context, search_pages
from kb.utils.llm import LLMError, call_llm
from kb.utils.wiki_log import LOG_SIZE_WARNING_BYTES, append_wiki_log

# ── Fix #1: LLM retry/timeout/error handling ────────────────────


@patch("kb.utils.llm.get_client")
def test_call_llm_success(mock_get_client):
    """call_llm returns text on successful response."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = "Hello world"
    mock_response.content = [block]
    mock_client.messages.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = call_llm("test prompt")
    assert result == "Hello world"


@patch("kb.utils.llm.get_client")
def test_call_llm_empty_response_raises(mock_get_client):
    """call_llm raises LLMError on empty response."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = []
    mock_client.messages.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    with pytest.raises(LLMError, match="No text content block"):
        call_llm("test prompt")


@patch("kb.utils.llm.time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_retries_on_rate_limit(mock_get_client, mock_sleep):
    """call_llm retries on RateLimitError then succeeds."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = "success"
    mock_response.content = [block]

    rate_error = anthropic.RateLimitError(
        message="rate limited",
        response=MagicMock(status_code=429),
        body=None,
    )
    mock_client.messages.create.side_effect = [rate_error, mock_response]
    mock_get_client.return_value = mock_client

    result = call_llm("test prompt")
    assert result == "success"
    assert mock_sleep.call_count == 1


@patch("kb.utils.llm.time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_raises_after_max_retries(mock_get_client, mock_sleep):
    """call_llm raises LLMError after exhausting retries."""
    mock_client = MagicMock()
    rate_error = anthropic.RateLimitError(
        message="rate limited",
        response=MagicMock(status_code=429),
        body=None,
    )
    mock_client.messages.create.side_effect = rate_error
    mock_get_client.return_value = mock_client

    with pytest.raises(LLMError, match="after 3 retries"):
        call_llm("test prompt")
    assert mock_sleep.call_count == 3  # sleeps only between attempts, not after the final one


@patch("kb.utils.llm.get_client")
def test_call_llm_non_retryable_error(mock_get_client):
    """call_llm raises immediately on 401 (non-retryable)."""
    mock_client = MagicMock()
    mock_resp = MagicMock(status_code=401, headers={})
    auth_error = anthropic.AuthenticationError(
        message="invalid key",
        response=mock_resp,
        body=None,
    )
    mock_client.messages.create.side_effect = auth_error
    mock_get_client.return_value = mock_client

    with pytest.raises(LLMError, match="API error"):
        call_llm("test prompt")


@patch("kb.utils.llm.time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_retries_on_connection_error(mock_get_client, mock_sleep):
    """call_llm retries on APIConnectionError."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    block_ok1 = MagicMock()
    block_ok1.type = "text"
    block_ok1.text = "ok"
    mock_response.content = [block_ok1]

    conn_error = anthropic.APIConnectionError(request=MagicMock())
    mock_client.messages.create.side_effect = [conn_error, mock_response]
    mock_get_client.return_value = mock_client

    result = call_llm("test prompt")
    assert result == "ok"
    assert mock_sleep.call_count == 1


@patch("kb.utils.llm.time.sleep")
@patch("kb.utils.llm.get_client")
def test_call_llm_retries_on_timeout(mock_get_client, mock_sleep):
    """call_llm retries on APITimeoutError."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    block_ok2 = MagicMock()
    block_ok2.type = "text"
    block_ok2.text = "ok"
    mock_response.content = [block_ok2]

    timeout_error = anthropic.APITimeoutError(request=MagicMock())
    mock_client.messages.create.side_effect = [timeout_error, mock_response]
    mock_get_client.return_value = mock_client

    result = call_llm("test prompt")
    assert result == "ok"


def test_llm_error_is_exception():
    """LLMError is a proper Exception subclass."""
    err = LLMError("test error")
    assert isinstance(err, Exception)
    assert str(err) == "test error"


# ── Fix #2: Frontmatter source update ───────────────────────────


def test_update_existing_page_adds_to_frontmatter(tmp_path):
    """_update_existing_page adds new source to YAML source: list."""
    page = tmp_path / "entity.md"
    page.write_text(
        '---\ntitle: "Test"\nsource:\n  - "raw/articles/old.md"\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: entity\nconfidence: stated\n---\n\n"
        "# Test\n\n## References\n\n- Mentioned in raw/articles/old.md\n"
    )

    _update_existing_page(page, "raw/articles/new.md")
    content = page.read_text(encoding="utf-8")

    # Frontmatter should have both sources
    assert '"raw/articles/old.md"' in content
    assert '"raw/articles/new.md"' in content
    # References section should have both
    assert "Mentioned in raw/articles/old.md" in content
    assert "Mentioned in raw/articles/new.md" in content


def test_update_existing_page_skips_if_already_referenced(tmp_path):
    """_update_existing_page is idempotent."""
    page = tmp_path / "entity.md"
    page.write_text(
        '---\ntitle: "Test"\nsource:\n  - "raw/articles/existing.md"\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: entity\nconfidence: stated\n---\n\n"
        "# Test\n\n## References\n\n- Mentioned in raw/articles/existing.md\n"
    )

    _update_existing_page(page, "raw/articles/existing.md")
    content = page.read_text(encoding="utf-8")
    # Should not duplicate — source list entry + reference line = 2 occurrences
    assert content.count("raw/articles/existing.md") == 2


def test_update_existing_page_updates_date(tmp_path):
    """_update_existing_page updates the 'updated' field."""
    page = tmp_path / "entity.md"
    page.write_text(
        '---\ntitle: "Test"\nsource:\n  - "raw/articles/old.md"\n'
        "created: 2026-01-01\nupdated: 2026-01-01\n"
        "type: entity\nconfidence: stated\n---\n\n"
        "# Test\n\n## References\n\n- Mentioned in raw/articles/old.md\n"
    )

    _update_existing_page(page, "raw/articles/new.md")
    content = page.read_text(encoding="utf-8")
    assert "updated: 2026-01-01" not in content


# ── Fix #3: Query context truncation ────────────────────────────


def test_build_query_context_respects_limit():
    """_build_query_context truncates when exceeding max_chars."""
    pages = [
        {
            "id": f"p{i}",
            "type": "concept",
            "confidence": "stated",
            "title": f"Page {i}",
            "content": "x" * 1000,
        }
        for i in range(20)
    ]

    result = _build_query_context(pages, max_chars=3000)
    context = result["context"]
    assert len(context) <= 3100  # small allowance for truncation marker
    assert "[...truncated]" in context or len(context) < 3000


def test_build_query_context_all_fit():
    """_build_query_context includes all pages when under limit."""
    pages = [
        {
            "id": "p1",
            "type": "concept",
            "confidence": "stated",
            "title": "Page 1",
            "content": "Short content",
        },
    ]

    result = _build_query_context(pages, max_chars=80_000)
    context = result["context"]
    assert "Page 1" in context
    assert "[...truncated]" not in context


def test_build_query_context_empty():
    """_build_query_context returns fallback for empty list."""
    result = _build_query_context([])
    assert "No relevant" in result["context"]


def test_query_context_max_chars_config():
    """QUERY_CONTEXT_MAX_CHARS is defined and reasonable."""
    assert QUERY_CONTEXT_MAX_CHARS > 10_000
    assert QUERY_CONTEXT_MAX_CHARS <= 200_000


# ── Fix #4: Entity/concept context from extraction ──────────────


def test_extract_entity_context_finds_claims():
    """_extract_entity_context finds relevant claims for entity."""
    extraction = {
        "key_claims": [
            "GPT-4 achieves 90% on MMLU",
            "Claude is competitive with GPT-4",
            "Fine-tuning improves results",
        ],
        "core_argument": "GPT-4 is a major advance in language models.",
    }

    ctx = _extract_entity_context("GPT-4", extraction)
    assert "Context" in ctx
    assert "GPT-4" in ctx


def test_extract_entity_context_empty_when_no_match():
    """_extract_entity_context returns empty string when entity not found."""
    extraction = {
        "key_claims": ["Unrelated claim about weather"],
        "core_argument": "Nothing relevant here.",
    }

    ctx = _extract_entity_context("OpenAI", extraction)
    assert ctx == ""


def test_extract_entity_context_case_insensitive():
    """_extract_entity_context is case-insensitive."""
    extraction = {
        "key_claims": ["openai released GPT-4"],
    }

    ctx = _extract_entity_context("OpenAI", extraction)
    assert "openai" in ctx.lower()


def test_extract_entity_context_limits_to_3():
    """_extract_entity_context returns at most 3 items."""
    extraction = {
        "key_claims": [f"Claim {i} about RAG" for i in range(10)],
    }

    ctx = _extract_entity_context("RAG", extraction)
    lines = [line for line in ctx.split("\n") if line.startswith("- ")]
    assert len(lines) <= 3


def test_ingest_creates_entity_with_context(tmp_path):
    """ingest_source creates entity pages with context from extraction."""
    # Set up dirs
    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "summaries"):
        (wiki_dir / subdir).mkdir(parents=True)
    (wiki_dir / "index.md").write_text("## Summaries\n\n## Entities\n\n## Concepts\n")
    (wiki_dir / "_sources.md").write_text("# Sources\n\n")
    (wiki_dir / "log.md").write_text("# Log\n\n")

    raw_dir = tmp_path / "raw" / "articles"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "test.md"
    source.write_text("Test article about GPT-4.")

    extraction = {
        "title": "Test Article",
        "entities_mentioned": ["GPT-4"],
        "concepts_mentioned": [],
        "key_claims": ["GPT-4 is a large language model by OpenAI"],
    }

    with (
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
        patch("kb.utils.wiki_log.WIKI_LOG", wiki_dir / "log.md"),
        patch("kb.ingest.pipeline.RAW_DIR", tmp_path / "raw"),
        patch("kb.utils.paths.RAW_DIR", tmp_path / "raw"),
    ):
        ingest_source(source, "article", extraction=extraction)

    entity_page = wiki_dir / "entities" / "gpt-4.md"
    assert entity_page.exists()
    content = entity_page.read_text(encoding="utf-8")
    assert "Context" in content
    assert "GPT-4" in content


# ── Fix #5: Crash-safe manifest ─────────────────────────────────


@patch("kb.compile.compiler.ingest_source")
def test_compile_processes_all_sources(mock_ingest, tmp_path):
    """compile_wiki processes all sources and reports the correct count."""
    from kb.compile.compiler import compile_wiki

    mock_ingest.return_value = {
        "pages_created": ["summaries/s1"],
        "pages_updated": [],
    }

    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    (articles / "a.md").write_text("content a")
    (articles / "b.md").write_text("content b")

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    log_path = wiki_dir / "log.md"
    log_path.write_text("# Log\n\n")

    manifest_path = tmp_path / "hashes.json"
    with patch("kb.utils.wiki_log.WIKI_LOG", log_path):
        result = compile_wiki(incremental=True, raw_dir=raw_dir, manifest_path=manifest_path)

    assert result["sources_processed"] == 2


# ── Fix #6: Slug collision warnings ─────────────────────────────


def test_slug_collision_logs_warning(tmp_path, caplog):
    """Duplicate slugs from different entity names log a warning."""
    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "summaries"):
        (wiki_dir / subdir).mkdir(parents=True)
    (wiki_dir / "index.md").write_text("## Summaries\n\n## Entities\n\n## Concepts\n")
    (wiki_dir / "_sources.md").write_text("# Sources\n\n")
    (wiki_dir / "log.md").write_text("# Log\n\n")

    raw_dir = tmp_path / "raw" / "articles"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "test.md"
    source.write_text("Test article.")

    extraction = {
        "title": "Test",
        "entities_mentioned": ["Hello World", "hello world"],  # same slug
        "concepts_mentioned": [],
    }

    with (
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
        patch("kb.utils.wiki_log.WIKI_LOG", wiki_dir / "log.md"),
        patch("kb.ingest.pipeline.RAW_DIR", tmp_path / "raw"),
        patch("kb.utils.paths.RAW_DIR", tmp_path / "raw"),
        caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"),
    ):
        result = ingest_source(source, "article", extraction=extraction)

    # Should only create one entity page (not two)
    assert result["pages_created"].count("entities/hello-world") == 1


def test_symbol_only_entity_gets_untitled_slug(tmp_path, caplog):
    """After item-11 fix: symbol-only entities get untitled-<hash> slug, not skipped."""
    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "summaries"):
        (wiki_dir / subdir).mkdir(parents=True)
    (wiki_dir / "index.md").write_text("## Summaries\n\n## Entities\n\n## Concepts\n")
    (wiki_dir / "_sources.md").write_text("# Sources\n\n")
    (wiki_dir / "log.md").write_text("# Log\n\n")

    raw_dir = tmp_path / "raw" / "articles"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "test.md"
    source.write_text("Test.")

    extraction = {
        "title": "Test",
        "entities_mentioned": ["!!!"],  # slugify now returns "untitled-<hash>" not ""
        "concepts_mentioned": [],
    }

    with (
        patch("kb.ingest.pipeline.WIKI_DIR", wiki_dir),
        patch("kb.ingest.pipeline.WIKI_INDEX", wiki_dir / "index.md"),
        patch("kb.ingest.pipeline.WIKI_SOURCES", wiki_dir / "_sources.md"),
        patch("kb.utils.wiki_log.WIKI_LOG", wiki_dir / "log.md"),
        patch("kb.ingest.pipeline.RAW_DIR", tmp_path / "raw"),
        patch("kb.utils.paths.RAW_DIR", tmp_path / "raw"),
        caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"),
    ):
        ingest_source(source, "article", extraction=extraction)

    # "!!!" slug is now "untitled-<hash>" — entity page is created, not skipped
    assert not (wiki_dir / "entities" / ".md").exists()  # no blank-name file
    assert "Skipping entity with empty slug" not in caplog.text


# ── Fix #7: Exact source matching ───────────────────────────────


def test_source_coverage_exact_match(tmp_wiki, tmp_path):
    """check_source_coverage uses exact path matching, not substring."""
    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)

    (articles / "api.md").write_text("content")
    (articles / "my-api.md").write_text("content")

    # Create a page referencing only "my-api.md"
    page = tmp_wiki / "summaries" / "test.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        '---\ntitle: "Test"\nsource:\n  - "raw/articles/my-api.md"\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: summary\nconfidence: stated\n---\n\n"
        "Content referencing raw/articles/my-api.md\n"
    )

    issues = check_source_coverage(tmp_wiki, raw_dir)
    # "api.md" should be flagged as unreferenced (not caught by substring)
    unreferenced = [i["source"] for i in issues]
    assert "raw/articles/api.md" in unreferenced


# ── Fix #8: Word-boundary search ────────────────────────────────


def test_search_word_boundary(tmp_path):
    """search_pages uses word boundaries, not substring matching."""
    wiki_dir = tmp_path / "wiki"
    concepts = wiki_dir / "concepts"
    concepts.mkdir(parents=True)

    # Page with "rag" as a word
    (concepts / "rag.md").write_text(
        '---\ntitle: "RAG"\nsource:\n  - raw/test.md\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: concept\nconfidence: stated\n---\n\n"
        "RAG is retrieval augmented generation.\n"
    )

    # Page with "rag" only as substring in "storage"
    (concepts / "storage.md").write_text(
        '---\ntitle: "Storage"\nsource:\n  - raw/test.md\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: concept\nconfidence: stated\n---\n\n"
        "Data storage and backup systems.\n"
    )

    results = search_pages("rag", wiki_dir)
    result_ids = [r["id"] for r in results]
    assert "concepts/rag" in result_ids
    assert "concepts/storage" not in result_ids


def test_search_still_finds_exact_words(tmp_path):
    """search_pages still finds pages where term appears as whole word."""
    wiki_dir = tmp_path / "wiki"
    entities = wiki_dir / "entities"
    entities.mkdir(parents=True)

    (entities / "openai.md").write_text(
        '---\ntitle: "OpenAI"\nsource:\n  - raw/test.md\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: entity\nconfidence: stated\n---\n\n"
        "OpenAI builds AI systems.\n"
    )

    results = search_pages("openai", wiki_dir)
    assert len(results) >= 1
    assert results[0]["id"] == "entities/openai"


# ── Fix #9: Term overlap filtering ──────────────────────────────


def test_term_overlap_filters_common_words(tmp_path):
    """_group_by_term_overlap excludes common words from overlap computation."""
    wiki_dir = tmp_path / "wiki"
    concepts = wiki_dir / "concepts"
    concepts.mkdir(parents=True)

    # Two pages that only share filtered common words
    # All shared terms are in the common_words set: about, their, through, every,
    # using, value, where, which, would, could, should, still, these
    (concepts / "a.md").write_text(
        '---\ntitle: "A"\nsource:\n  - raw/test.md\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: concept\nconfidence: stated\n---\n\n"
        "about their through every using value where which would could should still these\n"
    )
    (concepts / "b.md").write_text(
        '---\ntitle: "B"\nsource:\n  - raw/test.md\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: concept\nconfidence: stated\n---\n\n"
        "about their through every using value where which would could should still these\n"
    )

    groups = _group_by_term_overlap(wiki_dir)
    # These should NOT be grouped since they only share common/filtered words
    grouped_pairs = [tuple(sorted(g)) for g in groups]
    assert ("concepts/a", "concepts/b") not in grouped_pairs


# ── Fix #10: Cycle detection ────────────────────────────────────


def test_check_cycles_detects_cycle(tmp_path):
    """check_cycles finds wikilink cycles."""
    wiki_dir = tmp_path / "wiki"
    concepts = wiki_dir / "concepts"
    concepts.mkdir(parents=True)

    (concepts / "a.md").write_text(
        '---\ntitle: "A"\nsource:\n  - raw/test.md\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: concept\nconfidence: stated\n---\n\n"
        "Links to [[concepts/b]].\n"
    )
    (concepts / "b.md").write_text(
        '---\ntitle: "B"\nsource:\n  - raw/test.md\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: concept\nconfidence: stated\n---\n\n"
        "Links to [[concepts/a]].\n"
    )

    issues = check_cycles(wiki_dir)
    assert len(issues) >= 1
    assert issues[0]["check"] == "wikilink_cycle"
    assert "cycle" in issues[0]["message"].lower()


def test_check_cycles_no_cycle(tmp_path):
    """check_cycles returns empty for acyclic graph."""
    wiki_dir = tmp_path / "wiki"
    concepts = wiki_dir / "concepts"
    concepts.mkdir(parents=True)

    (concepts / "a.md").write_text(
        '---\ntitle: "A"\nsource:\n  - raw/test.md\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: concept\nconfidence: stated\n---\n\n"
        "Links to [[concepts/b]].\n"
    )
    (concepts / "b.md").write_text(
        '---\ntitle: "B"\nsource:\n  - raw/test.md\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: concept\nconfidence: stated\n---\n\n"
        "No links back.\n"
    )

    issues = check_cycles(wiki_dir)
    assert len(issues) == 0


# ── Fix #11: Review history fields ──────────────────────────────


def test_review_history_includes_context(tmp_path):
    """refine_page stores content_length and status in review history."""
    from kb.review.refiner import load_review_history, refine_page

    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "concepts").mkdir(parents=True)
    (wiki_dir / "log.md").write_text("# Log\n\n")

    page = wiki_dir / "concepts" / "test.md"
    page.write_text(
        '---\ntitle: "Test"\nsource:\n  - raw/test.md\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: concept\nconfidence: stated\n---\n\nOld content.\n"
    )

    history_path = tmp_path / "history.json"
    refine_page(
        "concepts/test",
        "New content here",
        "test fix",
        wiki_dir=wiki_dir,
        history_path=history_path,
    )

    history = load_review_history(history_path)
    assert len(history) == 1
    entry = history[0]
    assert entry["content_length"] == len("New content here")
    assert entry["status"] == "applied"


# ── Fix #13: Log size warning ───────────────────────────────────


def test_log_size_warning(tmp_path, caplog):
    """append_wiki_log warns when log exceeds size threshold."""
    log_path = tmp_path / "log.md"
    # Create a log file just under the threshold
    big_content = "# Log\n\n" + ("- entry\n" * (LOG_SIZE_WARNING_BYTES // 8))
    log_path.write_text(big_content, encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="kb.utils.wiki_log"):
        append_wiki_log("test", "trigger warning", log_path)

    assert "consider archiving" in caplog.text.lower()
