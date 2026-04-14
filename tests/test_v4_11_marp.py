"""Tests for kb.query.formats.marp adapter."""

from __future__ import annotations

import pytest

from kb.query.formats.marp import _split_into_slides, render_marp


@pytest.fixture
def simple_result():
    return {
        "question": "What is RAG?",
        "answer": "RAG means Retrieval Augmented Generation.\n\nIt combines retrieval with LLMs.",
        "citations": [{"type": "wiki", "path": "concepts/rag", "context": "..."}],
        "source_pages": ["concepts/rag"],
    }


def test_marp_has_marp_directive(simple_result):
    out = render_marp(simple_result)
    assert "marp: true" in out
    assert out.startswith("---\n")


def test_marp_slide_separators(simple_result):
    out = render_marp(simple_result)
    separators = [line for line in out.split("\n") if line.strip() == "---"]
    # frontmatter (2) + Question/Answer/Sources separators (≥3) ≥ 5
    assert len(separators) >= 5


def test_marp_has_sources_slide(simple_result):
    out = render_marp(simple_result)
    assert "# Sources" in out
    assert "[[concepts/rag]]" in out


def test_marp_question_slide(simple_result):
    out = render_marp(simple_result)
    assert "# Question" in out
    assert "What is RAG?" in out


def test_marp_splits_long_answer_on_paragraphs():
    answer = "\n\n".join(["Paragraph " + str(i) + " " + ("x" * 300) for i in range(5)])
    slides = _split_into_slides(answer, max_chars=800)
    assert len(slides) >= 2


def test_marp_preserves_fenced_code_block():
    """Code blocks with blank lines inside must NOT be split."""
    code_block = "```python\ndef foo():\n\n    return 42\n```"
    answer = "Before code.\n\n" + code_block + "\n\nAfter code. " + ("x" * 500)
    slides = _split_into_slides(answer, max_chars=300)
    fence_slides = [s for s in slides if "```python" in s]
    assert len(fence_slides) == 1
    assert "def foo():" in fence_slides[0]
    assert "return 42" in fence_slides[0]
    # Opening + closing fence on same slide
    assert fence_slides[0].count("```") == 2


def test_marp_handles_single_long_paragraph():
    """A single paragraph >800 chars is kept whole — no mid-word break."""
    answer = "a" * 2000  # no blank lines = single segment
    slides = _split_into_slides(answer, max_chars=800)
    assert len(slides) == 1
    assert len(slides[0]) == 2000


def test_marp_empty_answer_produces_single_slide():
    slides = _split_into_slides("")
    assert slides == [""]


def test_marp_splits_on_plain_paragraphs():
    answer = "\n\n".join([f"p{i} " + ("x" * 300) for i in range(6)])
    slides = _split_into_slides(answer, max_chars=800)
    assert len(slides) >= 2


def test_marp_rejects_oversize():
    from kb.config import MAX_OUTPUT_CHARS

    oversize = {
        "question": "q",
        "answer": "x" * (MAX_OUTPUT_CHARS + 1),
        "citations": [],
        "source_pages": [],
    }
    with pytest.raises(ValueError, match="MAX_OUTPUT_CHARS"):
        render_marp(oversize)
