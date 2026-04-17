"""Tests for compile, linker, graph, and evolve correctness fixes — Phase 4 audit."""

from unittest.mock import patch


def test_manifest_pruning_keeps_unchanged_source(tmp_path):
    """Sources that exist on disk but were not processed must NOT be pruned."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    # An unchanged source file — exists on disk but NOT in sources_to_process
    kept_source = raw_dir / "articles" / "kept.md"
    kept_source.parent.mkdir(parents=True)
    kept_source.write_text("# Kept source\n")

    manifest_before = {
        "raw/articles/kept.md": "abc123",
        "raw/articles/gone.md": "def456",  # This one doesn't exist on disk
        "_template/article": "xyz",
    }

    # In full mode, compile_wiki calls scan_raw_sources() — return empty so no ingest runs.
    # load_manifest is called twice: once in the loop (no-op) and once at pruning time.
    # We return a fresh copy each time so the pruning logic has a real manifest to work with.
    with patch("kb.compile.compiler.scan_raw_sources", return_value=[]):
        with patch(
            "kb.compile.compiler.load_manifest",
            side_effect=lambda *a, **kw: dict(manifest_before),
        ):
            with patch("kb.compile.compiler.save_manifest") as mock_save:
                with patch("kb.compile.compiler._template_hashes", return_value={}):
                    from kb.compile.compiler import compile_wiki

                    compile_wiki(incremental=False, wiki_dir=wiki_dir, raw_dir=raw_dir)

    assert mock_save.called, "save_manifest should have been called in full mode"
    final_manifest = mock_save.call_args_list[-1][0][0]
    assert "raw/articles/kept.md" in final_manifest, (
        "Source that exists on disk was incorrectly pruned from manifest"
    )
    assert "raw/articles/gone.md" not in final_manifest, (
        "Source that no longer exists on disk was NOT pruned"
    )


def test_linker_source_id_is_lowercased(tmp_wiki):
    """resolve_wikilinks broken-link source IDs must be lowercased."""
    from kb.compile.linker import resolve_wikilinks

    # Create a page in a path that would yield a mixed-case page_id
    # (page_id lowercases the result — verify source_id in broken list is also lowercased)
    page = tmp_wiki / "entities" / "MyEntity.md"
    page.write_text(
        "---\ntitle: MyEntity\ntype: entity\nconfidence: stated\n---\n[[entities/nonexistent]]\n"
    )

    result = resolve_wikilinks(wiki_dir=tmp_wiki)
    for entry in result["broken"]:
        assert entry["source"] == entry["source"].lower(), (
            f"source_id {entry['source']!r} is not lowercased"
        )


def test_bare_slug_wikilink_creates_graph_edge(tmp_wiki):
    """Bare-slug wikilinks [[foo]] must produce graph edges to entities/foo."""
    from kb.graph.builder import build_graph

    # Entity page: entities/foo
    (tmp_wiki / "entities" / "foo.md").write_text(
        "---\ntitle: Foo\ntype: entity\nconfidence: stated\n---\ncontent\n"
    )
    # Concept page linking to [[foo]] (bare slug, no subdir/)
    (tmp_wiki / "concepts" / "bar.md").write_text(
        "---\ntitle: Bar\ntype: concept\nconfidence: stated\n---\n[[foo]]\n"
    )

    graph = build_graph(wiki_dir=tmp_wiki)
    assert graph.has_edge("concepts/bar", "entities/foo"), (
        "Bare-slug [[foo]] from concepts/bar did not produce an edge to entities/foo"
    )


def test_evolve_word_normalization_strips_markdown_tokens(tmp_path):
    """Words like **transformer** must be normalized to transformer, not kept as-is."""
    from kb.evolve.analyzer import find_connection_opportunities

    page_a = tmp_path / "a.md"
    page_b = tmp_path / "b.md"
    # Both pages share `transformer` but page_a has it wrapped in markdown
    page_a.write_text("**transformer** attention mechanism deep neural network learning\n")
    page_b.write_text("transformer architecture self attention neural network processing\n")

    with patch("kb.evolve.analyzer.scan_wiki_pages", return_value=[page_a, page_b]):
        with patch("kb.evolve.analyzer.page_id", side_effect=lambda p, wd: p.stem):
            opportunities = find_connection_opportunities(wiki_dir=tmp_path)

    # After normalization, **transformer** → transformer, so terms must not contain **
    for opp in opportunities:
        for term in opp.get("shared_terms", []):
            assert "**" not in term, f"Markdown token not stripped from shared term: {term!r}"
