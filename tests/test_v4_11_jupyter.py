"""Tests for kb.query.formats.jupyter adapter."""

from __future__ import annotations

import json

import pytest

from kb.query.formats.jupyter import render_jupyter


@pytest.fixture
def sample():
    return {
        "question": "What is RAG?",
        "answer": "RAG is Retrieval Augmented Generation.",
        "citations": [{"type": "wiki", "path": "concepts/rag", "context": "..."}],
        "source_pages": ["concepts/rag"],
        "context_pages": [],
    }


def test_jupyter_is_valid_json(sample):
    out = render_jupyter(sample)
    nb = json.loads(out)
    assert nb["nbformat"] == 4
    assert "cells" in nb


def test_jupyter_validates_with_nbformat(sample):
    import nbformat as nbf

    out = render_jupyter(sample)
    nb = nbf.reads(out, as_version=4)
    nbf.validate(nb)  # raises on invalid schema


def test_jupyter_has_kernelspec(sample):
    out = render_jupyter(sample)
    nb = json.loads(out)
    ks = nb["metadata"].get("kernelspec")
    assert ks is not None
    assert ks.get("name") == "python3"
    assert ks.get("language") == "python"


def test_jupyter_metadata_trusted_not_true(sample):
    """Never set metadata.trusted=True — it would auto-execute code cells."""
    out = render_jupyter(sample)
    nb = json.loads(out)
    assert nb["metadata"].get("trusted") is not True


def _concat_cell_source(cell) -> str:
    src = cell.get("source", "")
    return "".join(src) if isinstance(src, list) else src


def test_jupyter_includes_question(sample):
    out = render_jupyter(sample)
    nb = json.loads(out)
    joined = "\n".join(_concat_cell_source(c) for c in nb["cells"])
    assert "What is RAG?" in joined


def test_jupyter_includes_answer(sample):
    out = render_jupyter(sample)
    nb = json.loads(out)
    joined = "\n".join(_concat_cell_source(c) for c in nb["cells"])
    assert "RAG is Retrieval Augmented Generation." in joined


def test_jupyter_kb_metadata(sample):
    out = render_jupyter(sample)
    nb = json.loads(out)
    kb_meta = nb["metadata"].get("kb_query")
    assert kb_meta is not None
    assert kb_meta["query"] == "What is RAG?"
    assert "generated_at" in kb_meta


def test_jupyter_code_cell_question_json_encoded():
    """Hostile question in code cell must be json.dumps'd — script must stay
    parseable as valid Python AND the encoded literal must round-trip via eval."""
    import ast

    hostile = {
        "question": '"""; import os; os.system("rm -rf /"); """',
        "answer": "a",
        "citations": [],
        "source_pages": [],
    }
    out = render_jupyter(hostile)
    nb = json.loads(out)
    code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert len(code_cells) >= 1
    code_src = _concat_cell_source(code_cells[0])
    # Must parse as valid Python — if interpolated raw, the triple-quote in the
    # question would break the surrounding string and cause SyntaxError.
    tree = ast.parse(code_src)
    # The literal assignment must round-trip the hostile payload via ast.literal_eval
    # (which only evaluates literals — safe, never runs injection).
    question_val = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "QUESTION" for t in node.targets
        ):
            question_val = ast.literal_eval(node.value)
            break
    assert question_val == hostile["question"]
    # Assignment uses JSON-style double-quoted form
    assert 'QUESTION = "' in code_src


def test_jupyter_rejects_oversize():
    from kb.config import MAX_OUTPUT_CHARS

    oversize = {
        "question": "q",
        "answer": "x" * (MAX_OUTPUT_CHARS + 1),
        "citations": [],
        "source_pages": [],
    }
    with pytest.raises(ValueError, match="MAX_OUTPUT_CHARS"):
        render_jupyter(oversize)
