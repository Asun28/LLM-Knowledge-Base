"""Tests for kb.query.formats.common — slug, path, provenance, size guard."""

from __future__ import annotations

import re

import pytest

from kb.query.formats.common import (
    MAX_OUTPUT_CHARS,
    WINDOWS_RESERVED,
    build_provenance,
    output_path_for,
    safe_slug,
    validate_payload_size,
)


# ---- safe_slug ----

def test_safe_slug_plain():
    assert safe_slug("What is RAG?") == "what-is-rag"


def test_safe_slug_empty_fallback():
    assert safe_slug("") == "untitled"
    assert safe_slug("?!?") == "untitled"
    assert safe_slug("🔥🔥🔥") == "untitled"


def test_safe_slug_length_cap():
    long_text = "a" * 500
    slug = safe_slug(long_text)
    assert len(slug) <= 80


def test_safe_slug_windows_reserved():
    for name in ("con", "prn", "aux", "nul", "com1", "com9", "lpt1", "lpt9"):
        result = safe_slug(name)
        assert result not in WINDOWS_RESERVED
        assert result.endswith("_0")


def test_safe_slug_windows_reserved_in_phrase_is_safe():
    # "What is NUL" slugifies to "what-is-nul" which is not a reserved base name —
    # reserved-check is on dot-parts only
    result = safe_slug("What is NUL?")
    assert result == "what-is-nul"
    # Confirm no spurious _0 suffix appended
    assert not result.endswith("_0")


# ---- output_path_for ----

def test_output_path_for_creates_directory(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = output_path_for("What is RAG?", "markdown")
    assert path.parent.exists()
    assert path.parent.name == "outputs"


def test_output_path_for_extensions(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    assert output_path_for("q", "markdown").suffix == ".md"
    assert output_path_for("q", "marp").suffix == ".md"
    assert output_path_for("q", "html").suffix == ".html"
    assert output_path_for("q", "chart").suffix == ".py"
    assert output_path_for("q", "jupyter").suffix == ".ipynb"


def test_output_path_for_timestamp_format(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = output_path_for("What is RAG?", "markdown")
    # Filename: YYYY-MM-DD-HHMMSS-ffffff-what-is-rag.md
    stem = path.stem
    assert re.match(r"^\d{4}-\d{2}-\d{2}-\d{6}-\d{6}-", stem), f"bad stem: {stem}"


def test_output_path_for_unique_paths(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    p1 = output_path_for("collision-test", "markdown")
    p1.write_text("x", encoding="utf-8")
    p2 = output_path_for("collision-test", "markdown")
    # Stems differ by microseconds — different paths
    assert p1 != p2


def test_output_path_for_invalid_format(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    with pytest.raises(KeyError):
        output_path_for("q", "pdf")


# ---- build_provenance ----

def test_build_provenance_minimal():
    result = {
        "question": "What is RAG?",
        "answer": "RAG is...",
        "citations": [],
        "source_pages": [],
        "context_pages": [],
    }
    prov = build_provenance(result)
    assert prov["type"] == "query_output"
    assert prov["query"] == "What is RAG?"
    assert "generated_at" in prov
    assert prov["kb_version"]
    assert prov["source_pages"] == []
    assert prov["citations"] == []


def test_build_provenance_preserves_original_question():
    result = {"question": "orig?", "answer": "x", "citations": [], "source_pages": []}
    assert build_provenance(result)["query"] == "orig?"


def test_build_provenance_kb_version_dynamic():
    """kb_version must come from kb.__version__, not a hardcoded string."""
    import kb
    result = {"question": "q", "answer": "a", "citations": [], "source_pages": []}
    assert build_provenance(result)["kb_version"] == kb.__version__


# ---- validate_payload_size ----

def test_validate_payload_size_ok():
    validate_payload_size({"answer": "a" * 1000})  # no raise


def test_validate_payload_size_rejects_oversize():
    with pytest.raises(ValueError, match="MAX_OUTPUT_CHARS"):
        validate_payload_size({"answer": "a" * (MAX_OUTPUT_CHARS + 1)})


def test_validate_payload_size_empty_ok():
    validate_payload_size({"answer": ""})
    validate_payload_size({})
