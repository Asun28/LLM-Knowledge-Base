"""Tests for ingest data-integrity fixes — Phase 4 audit."""


def test_hash_bytes_matches_content_hash(tmp_path):
    """hash_bytes(data) must produce the same result as content_hash(path)."""
    from kb.utils.hashing import content_hash, hash_bytes

    path = tmp_path / "test.md"
    data = b"hello world content for hashing"
    path.write_bytes(data)
    assert hash_bytes(data) == content_hash(path)


def test_hash_bytes_returns_32_char_hex(tmp_path):
    """hash_bytes must return the same format as content_hash — 32 hex chars."""
    from kb.utils.hashing import hash_bytes

    result = hash_bytes(b"some content")
    assert len(result) == 32
    assert all(c in "0123456789abcdef" for c in result)


def test_sources_mapping_merges_on_reingest(tmp_path):
    """Re-ingesting the same source must merge new page IDs into existing entry."""
    from kb.ingest.pipeline import _update_sources_mapping

    sources_file = tmp_path / "_sources.md"
    sources_file.write_text(
        "- `raw/articles/foo.md` → [[summaries/foo-summary]]\n", encoding="utf-8"
    )

    _update_sources_mapping(
        "raw/articles/foo.md",
        ["summaries/foo-summary", "entities/new-entity"],
        wiki_dir=tmp_path,
    )

    content = sources_file.read_text()
    assert "[[entities/new-entity]]" in content, (
        "New page from re-ingest was not merged into _sources.md entry"
    )
    # Original entry must still be there
    assert "[[summaries/foo-summary]]" in content


def test_sources_mapping_first_ingest_appends(tmp_path):
    """First ingest of a source must append a new entry to _sources.md."""
    from kb.ingest.pipeline import _update_sources_mapping

    sources_file = tmp_path / "_sources.md"
    sources_file.write_text("")  # empty

    _update_sources_mapping(
        "raw/articles/new.md",
        ["summaries/new-summary"],
        wiki_dir=tmp_path,
    )

    content = sources_file.read_text()
    assert "raw/articles/new.md" in content
    assert "[[summaries/new-summary]]" in content


def test_extraction_prompt_with_missing_template_keys():
    """build_extraction_prompt must not raise KeyError when name/description are missing."""
    from kb.ingest.extractors import build_extraction_prompt

    template_minimal = {"extract": ["key_claims", "entities_mentioned"]}
    # Must not raise KeyError
    prompt = build_extraction_prompt("Some source content.", template_minimal)
    assert "key_claims" in prompt
    assert "entities_mentioned" in prompt


def test_contradiction_strips_evidence_trail_header():
    """Evidence Trail section headers must not produce false contradiction signals."""
    from kb.ingest.contradiction import detect_contradictions

    new_claims = ["transformers use attention mechanisms for sequence modeling"]
    existing_pages = [
        {
            "id": "entities/transformer",
            "content": (
                "## Evidence Trail\n"
                "2026-01-01 | raw/articles/a.md | Initial extraction\n\n"
                "## References\n"
                "- [[raw/articles/a.md]]\n"
            ),
        }
    ]
    result = detect_contradictions(new_claims, existing_pages, max_claims=10)
    assert result == [], f"Got spurious contradictions from structural-only page content: {result}"


def test_contradiction_strips_wikilinks():
    """Wikilinks in page content must be stripped to their display text before tokenizing."""
    from kb.ingest.contradiction import _strip_markdown_structure

    content = "The [[entities/transformer|Transformer]] model is not slow."
    stripped = _strip_markdown_structure(content)
    assert "[[" not in stripped
    assert "entities/transformer" not in stripped
    assert "Transformer" in stripped  # display text preserved


def test_load_all_pages_called_at_most_once_per_ingest(tmp_path, monkeypatch):
    """load_all_pages must be called at most once during ingest_source."""
    import kb.ingest.pipeline as pipeline_mod
    import kb.utils.pages as pages_mod
    from kb.ingest.pipeline import ingest_source

    # Set up minimal wiki and raw directories
    wiki = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki / subdir).mkdir(parents=True)
    (wiki / "index.md").write_text("", encoding="utf-8")
    (wiki / "_sources.md").write_text("", encoding="utf-8")
    (wiki / "_categories.md").write_text("", encoding="utf-8")
    (wiki / "log.md").write_text("", encoding="utf-8")

    raw = tmp_path / "raw" / "articles"
    raw.mkdir(parents=True)
    source = raw / "test.md"
    source.write_text("# Test\nContent here.\n", encoding="utf-8")

    # Patch module-level config names so the path-validation check passes
    monkeypatch.setattr(pipeline_mod, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(pipeline_mod, "WIKI_DIR", wiki)
    monkeypatch.setattr(pipeline_mod, "WIKI_INDEX", wiki / "index.md")
    monkeypatch.setattr(pipeline_mod, "WIKI_SOURCES", wiki / "_sources.md")
    monkeypatch.setattr("kb.utils.paths.RAW_DIR", tmp_path / "raw")

    call_count = [0]
    real_load = pages_mod.load_all_pages

    def counting_load(wiki_dir=None):
        call_count[0] += 1
        return real_load(wiki_dir=wiki_dir)

    # Patch the load_all_pages reference inside pipeline module
    monkeypatch.setattr(pipeline_mod, "load_all_pages", counting_load)

    # Patch out the LLM extraction and other side-effectful operations
    monkeypatch.setattr(
        pipeline_mod,
        "extract_from_source",
        lambda *a, **kw: {
            "key_claims": ["claim one"],
            "entities_mentioned": [],
            "concepts_mentioned": [],
            "title": "Test",
            "summary": "A test document.",
        },
    )
    monkeypatch.setattr(pipeline_mod, "_is_duplicate_content", lambda *a: False)

    ingest_source(source, wiki_dir=wiki)

    assert call_count[0] <= 1, (
        f"load_all_pages was called {call_count[0]} times in a single ingest — expected ≤1"
    )
