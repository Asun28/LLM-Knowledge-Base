"""Tests for kb.query.formats.markdown adapter."""

from __future__ import annotations

import pytest
import yaml

from kb.query.formats.markdown import render_markdown


@pytest.fixture
def sample_result():
    return {
        "question": "What is compile-not-retrieve?",
        "answer": "Compile-not-retrieve is a philosophy where...",
        "citations": [
            {"type": "wiki", "path": "concepts/compile-not-retrieve", "context": "..."},
            {"type": "wiki", "path": "entities/karpathy", "context": "..."},
        ],
        "source_pages": ["concepts/compile-not-retrieve", "entities/karpathy"],
        "context_pages": ["concepts/compile-not-retrieve"],
    }


def test_markdown_has_frontmatter(sample_result):
    out = render_markdown(sample_result)
    assert out.startswith("---\n")
    parts = out.split("---\n", 2)
    assert len(parts) >= 3
    fm = yaml.safe_load(parts[1])
    assert fm["type"] == "query_output"
    assert fm["format"] == "markdown"
    assert fm["query"] == "What is compile-not-retrieve?"
    assert "generated_at" in fm


def test_markdown_embeds_answer(sample_result):
    out = render_markdown(sample_result)
    assert "Compile-not-retrieve is a philosophy where..." in out


def test_markdown_renders_wiki_sources(sample_result):
    out = render_markdown(sample_result)
    assert "[[concepts/compile-not-retrieve]]" in out
    assert "[[entities/karpathy]]" in out


def test_markdown_h1_is_question(sample_result):
    out = render_markdown(sample_result)
    assert "# What is compile-not-retrieve?" in out


def test_markdown_no_citations(sample_result):
    sample_result["citations"] = []
    out = render_markdown(sample_result)
    assert "**Sources:**" not in out


def test_markdown_kb_version_from_module(sample_result):
    import kb

    out = render_markdown(sample_result)
    parts = out.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    assert fm["kb_version"] == kb.__version__


def test_markdown_handles_quotes_in_question(sample_result):
    sample_result["question"] = 'What about "quoted" text?'
    out = render_markdown(sample_result)
    parts = out.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    assert fm["query"] == 'What about "quoted" text?'


def test_markdown_rejects_oversize():
    from kb.config import MAX_OUTPUT_CHARS

    oversize = {
        "question": "q",
        "answer": "x" * (MAX_OUTPUT_CHARS + 1),
        "citations": [],
        "source_pages": [],
    }
    with pytest.raises(ValueError, match="MAX_OUTPUT_CHARS"):
        render_markdown(oversize)
