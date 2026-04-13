"""Tests for wiki/purpose.md KB focus document feature."""

import pytest

from kb.utils.pages import load_purpose
from kb.ingest.extractors import build_extraction_prompt


# ── load_purpose() ──────────────────────────────────────────────────────────

def test_load_purpose_missing(tmp_path):
    """Returns None when purpose.md does not exist."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    assert load_purpose(wiki_dir) is None


def test_load_purpose_returns_content(tmp_path):
    """Returns stripped content when purpose.md exists."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "purpose.md").write_text("# KB Purpose\n\nGoals: test.\n", encoding="utf-8")
    result = load_purpose(wiki_dir)
    assert result == "# KB Purpose\n\nGoals: test."


def test_load_purpose_empty_file(tmp_path):
    """Returns None when purpose.md exists but is empty."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "purpose.md").write_text("   \n", encoding="utf-8")
    assert load_purpose(wiki_dir) is None


# ── build_extraction_prompt() ───────────────────────────────────────────────

def test_extraction_prompt_includes_purpose():
    """Purpose text is injected into extraction prompt when provided."""
    template = {
        "name": "article",
        "description": "A web article",
        "extract": ["title: string", "key_claims: list of strings"],
    }
    prompt = build_extraction_prompt("Some content.", template, purpose="Focus on LLM systems.")
    assert "KB FOCUS" in prompt
    assert "Focus on LLM systems." in prompt


def test_extraction_prompt_no_purpose():
    """Extraction prompt has no KB FOCUS section when purpose is None."""
    template = {
        "name": "article",
        "description": "A web article",
        "extract": ["title: string"],
    }
    prompt = build_extraction_prompt("Some content.", template, purpose=None)
    assert "KB FOCUS" not in prompt


def test_extraction_prompt_purpose_before_source_type():
    """Purpose section appears before 'Source type:' in the prompt."""
    template = {
        "name": "article",
        "description": "A web article",
        "extract": ["title: string"],
    }
    prompt = build_extraction_prompt("Some content.", template, purpose="Goal: test.")
    focus_idx = prompt.index("KB FOCUS")
    source_type_idx = prompt.index("Source type:")
    assert focus_idx < source_type_idx
