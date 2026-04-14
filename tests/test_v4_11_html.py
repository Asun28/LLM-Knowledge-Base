"""Tests for kb.query.formats.html adapter."""

from __future__ import annotations

import pytest

from kb.query.formats.html import render_html


@pytest.fixture
def sample():
    return {
        "question": "What is RAG?",
        "answer": "RAG is...\n\nSecond paragraph.",
        "citations": [
            {"type": "wiki", "path": "concepts/rag", "context": "..."},
            {"type": "raw", "path": "raw/articles/foo.md", "context": "..."},
        ],
        "source_pages": ["concepts/rag"],
    }


def test_html_well_formed(sample):
    out = render_html(sample)
    assert out.startswith("<!DOCTYPE html>")
    assert "<html" in out and "</html>" in out
    assert "<head>" in out and "</head>" in out
    assert "<body>" in out and "</body>" in out


def test_html_meta_tags_provenance(sample):
    out = render_html(sample)
    assert 'name="kb-query"' in out
    assert 'name="kb-generated-at"' in out
    assert 'name="kb-version"' in out


def test_html_escapes_xss_in_question():
    hostile = {
        "question": "<script>alert('xss')</script>",
        "answer": "ok",
        "citations": [],
        "source_pages": [],
    }
    out = render_html(hostile)
    # Raw script must be absent; escaped version present
    assert "<script>alert" not in out
    assert "&lt;script&gt;" in out


def test_html_escapes_xss_in_answer():
    hostile = {
        "question": "q",
        "answer": "<img src=x onerror=alert(1)>",
        "citations": [],
        "source_pages": [],
    }
    out = render_html(hostile)
    assert "<img src=x onerror" not in out
    assert "&lt;img" in out


def test_html_escapes_xss_in_citation_path():
    hostile = {
        "question": "q",
        "answer": "a",
        "citations": [
            {"type": "wiki", "path": "concepts/<script>", "context": "..."},
        ],
        "source_pages": [],
    }
    out = render_html(hostile)
    # Must not contain raw <script> literal from the path
    # (it appears only in escaped form)
    without_escaped = out.replace("&lt;script&gt;", "")
    assert "<script>" not in without_escaped


def test_html_relative_wiki_links(sample):
    out = render_html(sample)
    assert "./wiki/concepts/rag.md" in out
    assert "<code>raw/articles/foo.md</code>" in out


def test_html_answer_line_breaks_preserved(sample):
    sample["answer"] = "Line 1.\n\nLine 2."
    out = render_html(sample)
    assert "Line 1." in out
    assert "Line 2." in out


def test_html_no_citations_handled(sample):
    sample["citations"] = []
    out = render_html(sample)
    assert "No sources cited" in out


def test_html_kb_version_dynamic(sample):
    import kb

    out = render_html(sample)
    assert f'content="{kb.__version__}"' in out


def test_html_inline_css_no_external_assets(sample):
    out = render_html(sample)
    assert "<style>" in out
    assert 'href="http' not in out
    assert 'src="http' not in out


def test_html_escapes_ampersand_in_path():
    hostile = {
        "question": "q",
        "answer": "a",
        "citations": [{"type": "wiki", "path": "concepts/foo&bar", "context": "..."}],
        "source_pages": [],
    }
    out = render_html(hostile)
    # Ampersand must be escaped inside the href and anchor text
    assert "foo&bar" not in out or "foo&amp;bar" in out


def test_html_rejects_oversize():
    from kb.config import MAX_OUTPUT_CHARS

    oversize = {
        "question": "q",
        "answer": "x" * (MAX_OUTPUT_CHARS + 1),
        "citations": [],
        "source_pages": [],
    }
    with pytest.raises(ValueError, match="MAX_OUTPUT_CHARS"):
        render_html(oversize)
