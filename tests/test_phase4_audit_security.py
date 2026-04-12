"""Tests for HIGH-severity MCP security fixes — Phase 4 audit."""
import pytest
from unittest.mock import patch
from kb.mcp.app import _validate_page_id
from kb.config import MAX_INGEST_CONTENT_CHARS


def test_validate_page_id_rejects_null_byte():
    err = _validate_page_id("concepts/foo\x00bar", check_exists=False)
    assert err is not None
    assert "null" in err.lower() or "invalid" in err.lower()


def test_validate_page_id_rejects_null_byte_only():
    err = _validate_page_id("\x00", check_exists=False)
    assert err is not None


def test_validate_page_id_still_rejects_traversal():
    """Existing behaviour must not be broken by the null-byte fix."""
    err = _validate_page_id("../etc/passwd", check_exists=False)
    assert err is not None


def test_kb_refine_page_rejects_oversized_content(tmp_path):
    from kb.mcp.quality import kb_refine_page
    page_path = tmp_path / "concepts" / "test-page.md"
    page_path.parent.mkdir(parents=True)
    page_path.write_text("---\ntitle: Test\ntype: concept\nconfidence: stated\n---\nBody\n")
    with patch("kb.mcp.app.WIKI_DIR", tmp_path), patch("kb.mcp.quality.WIKI_DIR", tmp_path):
        oversized = "x" * (MAX_INGEST_CONTENT_CHARS + 1)
        result = kb_refine_page("concepts/test-page", oversized)
    assert "Error" in result
    assert "large" in result.lower() or str(MAX_INGEST_CONTENT_CHARS) in result


def test_kb_refine_page_accepts_valid_content(tmp_path):
    from kb.mcp.quality import kb_refine_page
    page_path = tmp_path / "concepts" / "test-page.md"
    page_path.parent.mkdir(parents=True)
    page_path.write_text("---\ntitle: Test\ntype: concept\nconfidence: stated\n---\nBody\n")
    with patch("kb.mcp.app.WIKI_DIR", tmp_path), patch("kb.mcp.quality.WIKI_DIR", tmp_path):
        result = kb_refine_page("concepts/test-page", "Valid short content.")
    # Must not return an oversized error
    assert "too large" not in result.lower()


def test_kb_create_page_rejects_oversized_content(tmp_path):
    from kb.mcp.quality import kb_create_page
    with patch("kb.mcp.app.WIKI_DIR", tmp_path), patch("kb.mcp.quality.WIKI_DIR", tmp_path):
        oversized = "x" * (MAX_INGEST_CONTENT_CHARS + 1)
        result = kb_create_page("concepts/test-new", "Title", oversized)
    assert "Error" in result
    assert "large" in result.lower() or str(MAX_INGEST_CONTENT_CHARS) in result
