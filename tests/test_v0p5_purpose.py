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


# ── Cycle 17 AC14 — purpose threads into query_wiki synthesis prompt ───────


def test_cycle17_ac14_query_wiki_threads_purpose_to_synthesis_prompt(tmp_path, monkeypatch):
    """AC14 — purpose.md text threads into the synthesis prompt via query_wiki.

    Cycle 6 shipped a rewriter-side test pinning KB_FOCUS reaches rewrite_query.
    Cycle 17 AC14 closes the query-side gap: on the API / hybrid-synthesis
    path, `query_wiki(wiki_dir=tmp)` must pass `purpose.md` content through
    to the synthesizer's call_llm invocation.
    """
    import kb.utils.pages as pages_module
    from kb.query import engine as query_engine

    tmp_wiki = tmp_path / "wiki"
    tmp_wiki.mkdir()
    marker = "CYCLE17_AC14_PURPOSE_MARKER_deadbeef"
    (tmp_wiki / "purpose.md").write_text(
        f"# KB Purpose\n\n{marker}\n\nFocus on cycle 17 regression coverage.\n",
        encoding="utf-8",
    )
    # Seed one page so search_pages returns a non-empty result — the synthesis
    # path only fires when there's something to synthesise.
    (tmp_wiki / "entities").mkdir()
    (tmp_wiki / "entities" / "seeder.md").write_text(
        "---\ntitle: Seeder\ntype: entity\nconfidence: stated\n"
        "source:\n  - raw/articles/seeder.md\n---\n\nContent about seeder.",
        encoding="utf-8",
    )

    # Clear the LRU cache on load_purpose so the new purpose.md is read.
    pages_module.load_purpose.cache_clear()

    captured_prompts: list[str] = []

    def spy_call_llm(prompt, tier="write", **kwargs):
        captured_prompts.append(prompt)
        return "synthesised answer"

    monkeypatch.setattr(query_engine, "call_llm", spy_call_llm)

    # Invoke the API synthesis branch by passing the wiki_dir.
    # query_wiki in API mode calls load_purpose(wiki_dir) then threads the
    # returned text into the synthesis prompt via call_llm.
    try:
        query_engine.query_wiki("What is the seeder?", wiki_dir=tmp_wiki)
    except Exception:
        # Any LLM-path exception is OK — we only care that call_llm was
        # invoked with the marker in its prompt.
        pass

    # Assert the marker reached the synthesis prompt.
    assert captured_prompts, "AC14: call_llm never invoked under query_wiki(wiki_dir=tmp)"
    joined = "\n".join(captured_prompts)
    assert marker in joined, (
        f"AC14 regression: purpose.md marker {marker!r} did not thread into "
        f"the synthesis prompt. Captured prompts:\n{joined[:2000]}"
    )


def test_cycle17_ac18_load_purpose_ignores_kb_project_root_env(tmp_path, monkeypatch):
    """AC18 regression pin — load_purpose(wiki_dir=tmp) ignores KB_PROJECT_ROOT env.

    Cycle 4 item #28 already removed the PROJECT_ROOT fallback from
    load_purpose. This test pins the invariant so a future refactor that
    re-introduces a `KB_PROJECT_ROOT` env-var fallback inside `load_purpose`
    triggers a red-line test failure.
    """
    import kb.utils.pages as pages_module

    # Set the env var to a directory that contains a DIFFERENT purpose.md.
    elsewhere = tmp_path / "elsewhere" / "wiki"
    elsewhere.mkdir(parents=True)
    (elsewhere / "purpose.md").write_text("POISON_PURPOSE_FROM_ENV", encoding="utf-8")
    monkeypatch.setenv("KB_PROJECT_ROOT", str(tmp_path / "elsewhere"))

    # Real tmp_wiki that the caller passes.
    tmp_wiki = tmp_path / "real_wiki"
    tmp_wiki.mkdir()
    expected = "REAL_CALLER_PROVIDED_PURPOSE"
    (tmp_wiki / "purpose.md").write_text(expected, encoding="utf-8")

    pages_module.load_purpose.cache_clear()
    result = pages_module.load_purpose(tmp_wiki)
    assert result == expected, (
        f"AC18 regression: load_purpose returned {result!r} instead of the "
        f"caller-provided content {expected!r}. A KB_PROJECT_ROOT-based "
        f"fallback may have been re-introduced — check utils/pages.py::load_purpose."
    )
    # Also verify the poisoned path was NOT read.
    assert "POISON_PURPOSE_FROM_ENV" not in (result or "")
