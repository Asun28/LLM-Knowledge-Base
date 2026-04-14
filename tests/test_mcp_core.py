"""Tests for MCP core tools — kb_save_source, kb_ingest_content, kb_compile_scan."""

import json
from unittest.mock import patch

import kb.config
from kb.mcp.core import kb_compile_scan, kb_ingest_content, kb_save_source


def _patch_source_type_dirs(monkeypatch, tmp_path):
    """Patch SOURCE_TYPE_DIRS so tools write to tmp directories."""
    tmp_dirs = {}
    for stype in kb.config.SOURCE_TYPE_DIRS:
        d = tmp_path / "raw" / f"{stype}s"
        d.mkdir(parents=True, exist_ok=True)
        tmp_dirs[stype] = d
    monkeypatch.setattr(kb.config, "SOURCE_TYPE_DIRS", tmp_dirs)
    monkeypatch.setattr("kb.mcp.core.SOURCE_TYPE_DIRS", tmp_dirs)
    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("kb.mcp.core.PROJECT_ROOT", tmp_path)
    return tmp_dirs


# ── kb_save_source ───────────────────────────────────────────────


def test_kb_save_source_creates_file(tmp_path, monkeypatch):
    """kb_save_source writes content to the correct raw/ subdirectory."""
    dirs = _patch_source_type_dirs(monkeypatch, tmp_path)

    result = kb_save_source(
        content="This is a test article about LLMs.",
        filename="test-llm-article",
        source_type="article",
    )

    expected_path = dirs["article"] / "test-llm-article.md"
    assert expected_path.exists()
    text = expected_path.read_text(encoding="utf-8")
    assert "This is a test article about LLMs." in text
    assert "Saved:" in result
    assert "test-llm-article.md" in result
    assert "To ingest:" in result


def test_kb_save_source_with_url(tmp_path, monkeypatch):
    """kb_save_source prepends a YAML header when a URL is provided."""
    dirs = _patch_source_type_dirs(monkeypatch, tmp_path)

    result = kb_save_source(
        content="Article body text.",
        filename="url-article",
        source_type="article",
        url="https://example.com/article",
    )

    file_path = dirs["article"] / "url-article.md"
    assert file_path.exists()
    text = file_path.read_text(encoding="utf-8")
    assert 'url: "https://example.com/article"' in text
    assert "fetched:" in text
    assert "Article body text." in text
    # The header adds chars, so the char count should include them
    assert "Saved:" in result


def test_kb_save_source_invalid_type(tmp_path, monkeypatch):
    """kb_save_source returns an error for unknown source_type."""
    _patch_source_type_dirs(monkeypatch, tmp_path)

    result = kb_save_source(
        content="Some content.",
        filename="bad-type",
        source_type="unknown_type",
    )

    assert "Error:" in result
    assert "Unknown source_type" in result
    assert "unknown_type" in result


def test_kb_save_source_slugifies_filename(tmp_path, monkeypatch):
    """kb_save_source normalizes filenames using slugify."""
    dirs = _patch_source_type_dirs(monkeypatch, tmp_path)

    kb_save_source(
        content="Content.",
        filename="My Article Title!",
        source_type="article",
    )

    # slugify should produce a lowercase, hyphenated slug
    files = list(dirs["article"].glob("*.md"))
    assert len(files) == 1
    assert files[0].name == "my-article-title.md"


def test_kb_save_source_paper_type(tmp_path, monkeypatch):
    """kb_save_source writes to the paper subdirectory for source_type='paper'."""
    dirs = _patch_source_type_dirs(monkeypatch, tmp_path)

    kb_save_source(
        content="Paper abstract and findings.",
        filename="attention-is-all-you-need",
        source_type="paper",
    )

    expected_path = dirs["paper"] / "attention-is-all-you-need.md"
    assert expected_path.exists()


# ── kb_ingest_content ────────────────────────────────────────────


def test_kb_ingest_content_creates_source_and_pages(tmp_path, monkeypatch):
    """kb_ingest_content saves the file and calls ingest_source to create pages."""
    dirs = _patch_source_type_dirs(monkeypatch, tmp_path)

    mock_result = {
        "source_path": str(dirs["article"] / "test-one-shot.md"),
        "source_type": "article",
        "content_hash": "abc123",
        "pages_created": ["summaries/test-one-shot", "entities/openai"],
        "pages_updated": [],
        "pages_skipped": [],
    }

    extraction = {
        "title": "Test One-Shot Article",
        "entities_mentioned": ["OpenAI"],
        "concepts_mentioned": ["LLM"],
    }

    with patch("kb.mcp.core.ingest_source", return_value=mock_result) as mock_ingest:
        result = kb_ingest_content(
            content="Full article content here.",
            filename="test-one-shot",
            source_type="article",
            extraction_json=json.dumps(extraction),
        )

    # File should be saved to disk
    saved_path = dirs["article"] / "test-one-shot.md"
    assert saved_path.exists()
    assert "Full article content here." in saved_path.read_text(encoding="utf-8")

    # ingest_source should have been called with the saved path
    mock_ingest.assert_called_once()
    call_args = mock_ingest.call_args
    assert call_args[0][0] == saved_path
    assert call_args[0][1] == "article"
    assert call_args[1]["extraction"] == extraction

    # Result should contain both save and ingest info
    assert "Saved source:" in result
    assert "test-one-shot.md" in result
    assert "Ingested:" in result
    assert "summaries/test-one-shot" in result
    assert "entities/openai" in result


def test_kb_ingest_content_invalid_json(tmp_path, monkeypatch):
    """kb_ingest_content returns error for malformed extraction_json."""
    _patch_source_type_dirs(monkeypatch, tmp_path)

    result = kb_ingest_content(
        content="Content.",
        filename="bad-json",
        source_type="article",
        extraction_json="not valid json {{{",
    )

    assert "Error:" in result
    assert "Invalid extraction JSON" in result


def test_kb_ingest_content_missing_title(tmp_path, monkeypatch):
    """kb_ingest_content returns error when extraction lacks title/name."""
    _patch_source_type_dirs(monkeypatch, tmp_path)

    extraction = {
        "entities_mentioned": ["OpenAI"],
        "concepts_mentioned": ["LLM"],
    }

    result = kb_ingest_content(
        content="Content.",
        filename="no-title",
        source_type="article",
        extraction_json=json.dumps(extraction),
    )

    assert "Error:" in result
    assert "title" in result.lower()


def test_kb_ingest_content_with_url(tmp_path, monkeypatch):
    """kb_ingest_content adds URL metadata header when url is provided."""
    dirs = _patch_source_type_dirs(monkeypatch, tmp_path)

    mock_result = {
        "source_path": str(dirs["article"] / "url-article.md"),
        "source_type": "article",
        "content_hash": "def456",
        "pages_created": ["summaries/url-article"],
        "pages_updated": [],
        "pages_skipped": [],
    }

    extraction = {
        "title": "URL Article",
        "entities_mentioned": [],
        "concepts_mentioned": [],
    }

    with patch("kb.mcp.core.ingest_source", return_value=mock_result):
        result = kb_ingest_content(
            content="Article from URL.",
            filename="url-article",
            source_type="article",
            extraction_json=json.dumps(extraction),
            url="https://example.com/source",
        )

    saved_path = dirs["article"] / "url-article.md"
    text = saved_path.read_text(encoding="utf-8")
    assert 'url: "https://example.com/source"' in text
    assert "fetched:" in text
    assert "Article from URL." in text
    assert "Saved source:" in result


def test_kb_ingest_content_invalid_source_type(tmp_path, monkeypatch):
    """kb_ingest_content returns error for unknown source_type."""
    _patch_source_type_dirs(monkeypatch, tmp_path)

    result = kb_ingest_content(
        content="Content.",
        filename="bad-type",
        source_type="invalid_type",
        extraction_json='{"title": "Test"}',
    )

    assert "Error:" in result
    assert "Unknown source_type" in result
    assert "invalid_type" in result


def test_kb_ingest_content_extraction_not_dict(tmp_path, monkeypatch):
    """kb_ingest_content returns error when extraction_json is not an object."""
    _patch_source_type_dirs(monkeypatch, tmp_path)

    result = kb_ingest_content(
        content="Content.",
        filename="not-dict",
        source_type="article",
        extraction_json='["a", "b"]',
    )

    assert "Error:" in result
    assert "JSON object" in result


# ── kb_compile_scan ──────────────────────────────────────────────


def test_kb_compile_scan_no_changes():
    """kb_compile_scan returns 'up to date' when no changed sources."""
    with patch("kb.compile.compiler.find_changed_sources", return_value=([], [])):
        result = kb_compile_scan(incremental=True)

    assert "up to date" in result.lower()


def test_kb_compile_scan_reports_new_sources(tmp_path, monkeypatch):
    """kb_compile_scan lists new source files found."""
    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("kb.mcp.core.PROJECT_ROOT", tmp_path)

    new_file = tmp_path / "raw" / "articles" / "new-article.md"
    new_file.parent.mkdir(parents=True, exist_ok=True)
    new_file.write_text("New content.", encoding="utf-8")

    with patch(
        "kb.compile.compiler.find_changed_sources",
        return_value=([new_file], []),
    ):
        result = kb_compile_scan(incremental=True)

    assert "New sources" in result
    assert "new-article.md" in result
    assert "1 source(s) to process" in result


def test_kb_compile_scan_reports_changed_sources(tmp_path, monkeypatch):
    """kb_compile_scan lists changed source files found."""
    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("kb.mcp.core.PROJECT_ROOT", tmp_path)

    changed_file = tmp_path / "raw" / "papers" / "updated-paper.md"
    changed_file.parent.mkdir(parents=True, exist_ok=True)
    changed_file.write_text("Updated content.", encoding="utf-8")

    with patch(
        "kb.compile.compiler.find_changed_sources",
        return_value=([], [changed_file]),
    ):
        result = kb_compile_scan(incremental=True)

    assert "Changed sources" in result
    assert "updated-paper.md" in result
    assert "1 source(s) to process" in result


# ── kb_capture wrapper ───────────────────────────────────────────


class TestKbCaptureWrapper:
    """Spec §7 MCP response formats."""

    def test_happy_path_format(self, tmp_captures_dir, mock_scan_llm, reset_rate_limit):
        from kb.mcp.core import kb_capture

        content = "We decided to use atomic writes. " * 5
        mock_scan_llm(
            {
                "items": [
                    {
                        "title": "Decided X",
                        "kind": "decision",
                        "body": "We decided to use atomic writes.",
                        "one_line_summary": "atomic writes win",
                        "confidence": "stated",
                    },
                    {
                        "title": "Saw Y",
                        "kind": "discovery",
                        "body": "We decided to use atomic writes.",
                        "one_line_summary": "discovery",
                        "confidence": "stated",
                    },
                ],
                "filtered_out_count": 3,
            }
        )
        result = kb_capture(content)
        assert isinstance(result, str)
        assert "Captured 2" in result
        assert "filtered 3" in result or "filtered 4" in result  # allow for body-verbatim drops
        assert "raw/captures/" in result
        assert "Next: run kb_ingest" in result

    def test_zero_items_format(self, tmp_captures_dir, mock_scan_llm, reset_rate_limit):
        from kb.mcp.core import kb_capture

        mock_scan_llm({"items": [], "filtered_out_count": 12})
        result = kb_capture("any content here")
        assert "Captured 0" in result
        assert "filtered 12" in result

    def test_secret_reject_format(self, tmp_captures_dir, reset_rate_limit):
        from kb.mcp.core import kb_capture

        result = kb_capture("AKIAIOSFODNN7EXAMPLE here")
        assert result.startswith("Error:")
        assert "secret" in result.lower()

    def test_empty_content_format(self, tmp_captures_dir, reset_rate_limit):
        from kb.mcp.core import kb_capture

        result = kb_capture("")
        assert result.startswith("Error:")
        assert "empty" in result.lower()

    def test_partial_write_format(
        self, tmp_captures_dir, mock_scan_llm, reset_rate_limit, monkeypatch
    ):
        from kb.mcp.core import kb_capture

        content = "we decided this and that and the other"
        mock_scan_llm(
            {
                "items": [
                    {
                        "title": "a",
                        "kind": "decision",
                        "body": "we decided this",
                        "one_line_summary": "s",
                        "confidence": "stated",
                    },
                    {
                        "title": "b",
                        "kind": "decision",
                        "body": "and that",
                        "one_line_summary": "s",
                        "confidence": "stated",
                    },
                ],
                "filtered_out_count": 0,
            }
        )
        from kb.capture import _exclusive_atomic_write as orig_write

        call_count = [0]

        def fail_second(path, c):
            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError(28, "No space left on device")
            return orig_write(path, c)

        monkeypatch.setattr("kb.capture._exclusive_atomic_write", fail_second)
        result = kb_capture(content)
        assert "Captured 1" in result
        assert "Error:" in result
        assert "No space left" in result
