"""Tests for wiki/purpose.md KB focus document feature."""

from kb.ingest.extractors import build_extraction_prompt
from kb.utils.pages import load_purpose

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


def test_h8_load_purpose_reads_from_wiki_dir_not_production(tmp_path):
    """Regression: Phase 4.5 HIGH item H8 (load_purpose always read production wiki/purpose.md)."""
    from kb.config import WIKI_DIR as prod_wiki_dir

    tmp_wiki = tmp_path / "wiki"
    tmp_wiki.mkdir()
    (tmp_wiki / "purpose.md").write_text("# Test Purpose\n\nThis is the test KB.", encoding="utf-8")

    # Should read from tmp_wiki, not from the production WIKI_DIR
    result = load_purpose(tmp_wiki)
    assert result is not None
    assert "Test Purpose" in result

    # Production purpose.md should NOT have been read (we'd get its content instead)
    prod_purpose = prod_wiki_dir / "purpose.md"
    if prod_purpose.exists():
        prod_content = prod_purpose.read_text(encoding="utf-8").strip()
        assert result != prod_content or "Test Purpose" in prod_content, (
            "H8: load_purpose(wiki_dir) returned production purpose.md instead of tmp_wiki"
        )


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
