"""Tests for the compile module."""

from pathlib import Path
from unittest.mock import patch

from kb.compile.compiler import (
    compile_wiki,
    find_changed_sources,
    load_manifest,
    save_manifest,
    scan_raw_sources,
)
from kb.compile.linker import build_backlinks, resolve_wikilinks

# ── Compiler tests ──────────────────────────────────────────────


def test_load_manifest_empty(tmp_path):
    """load_manifest returns empty dict when file doesn't exist."""
    result = load_manifest(tmp_path / "nonexistent.json")
    assert result == {}


def test_save_and_load_manifest(tmp_path):
    """save_manifest + load_manifest round-trips correctly."""
    manifest_path = tmp_path / "hashes.json"
    manifest = {"raw/articles/test.md": "abc123def456"}
    save_manifest(manifest, manifest_path)
    loaded = load_manifest(manifest_path)
    assert loaded == manifest


def test_scan_raw_sources(tmp_path):
    """scan_raw_sources finds markdown files in raw subdirectories."""
    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    (articles / "test1.md").write_text("content 1")
    (articles / "test2.md").write_text("content 2")
    (articles / ".gitkeep").write_text("")

    papers = raw_dir / "papers"
    papers.mkdir(parents=True)
    (papers / "paper1.md").write_text("paper content")

    sources = scan_raw_sources(raw_dir)
    assert len(sources) == 3
    names = [s.name for s in sources]
    assert "test1.md" in names
    assert "test2.md" in names
    assert "paper1.md" in names
    assert ".gitkeep" not in names


def test_scan_raw_sources_empty(tmp_path):
    """scan_raw_sources returns empty list for empty raw directory."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    sources = scan_raw_sources(raw_dir)
    assert sources == []


def test_find_changed_sources(tmp_path):
    """find_changed_sources detects new and modified files."""
    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    (articles / "existing.md").write_text("original content")
    (articles / "new.md").write_text("new content")

    manifest_path = tmp_path / "hashes.json"
    # Manifest uses canonical relative paths (raw/articles/existing.md)
    manifest = {"raw/articles/existing.md": "oldhash12345678"}
    save_manifest(manifest, manifest_path)

    new, changed = find_changed_sources(raw_dir, manifest_path)
    assert len(new) == 1
    assert new[0].name == "new.md"
    assert len(changed) == 1
    assert changed[0].name == "existing.md"


@patch("kb.compile.compiler.ingest_source")
def test_compile_wiki_incremental(mock_ingest, tmp_path):
    """compile_wiki in incremental mode only processes new/changed sources."""
    mock_ingest.return_value = {
        "source_path": "test",
        "source_type": "article",
        "content_hash": "abc123",
        "pages_created": ["summaries/test"],
        "pages_updated": [],
    }

    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    (articles / "test.md").write_text("test content")

    manifest_path = tmp_path / "hashes.json"
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    log_path = wiki_dir / "log.md"
    log_path.write_text("---\ntitle: Log\nupdated: 2026-04-06\n---\n\n# Log\n")

    result = compile_wiki(
        incremental=True, raw_dir=raw_dir, manifest_path=manifest_path, wiki_dir=wiki_dir
    )

    assert result["mode"] == "incremental"
    assert result["sources_processed"] == 1
    assert "summaries/test" in result["pages_created"]
    mock_ingest.assert_called_once()

    # Manifest should be saved
    assert manifest_path.exists()


@patch("kb.compile.compiler.ingest_source")
def test_compile_wiki_full(mock_ingest, tmp_path):
    """compile_wiki in full mode processes all sources."""
    mock_ingest.return_value = {
        "source_path": "test",
        "source_type": "article",
        "content_hash": "abc123",
        "pages_created": ["summaries/test"],
        "pages_updated": [],
    }

    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    (articles / "test.md").write_text("test content")

    manifest_path = tmp_path / "hashes.json"
    # Even with existing manifest, full recompiles everything
    save_manifest({"old": "hash"}, manifest_path)

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    log_path = wiki_dir / "log.md"
    log_path.write_text("---\ntitle: Log\nupdated: 2026-04-06\n---\n\n# Log\n")

    result = compile_wiki(
        incremental=False, raw_dir=raw_dir, manifest_path=manifest_path, wiki_dir=wiki_dir
    )

    assert result["mode"] == "full"
    assert result["sources_processed"] == 1


def test_detect_source_drift_does_not_mutate_manifest_when_sources_deleted(tmp_path):
    """Behaviour-based regression for the cycle 4 R1 Codex MAJOR 3 fix
    (upgraded from the docstring-grep test per C40-L3).

    Contract: detect_source_drift is fully read-only on the manifest. When
    a manifest entry references a now-deleted raw source, the function must
    REPORT the deletion (in `deleted_sources`) without persisting any change
    to the manifest file. The persistence happens only on the next
    compile_wiki run with save_hashes=True.

    Reverting the cycle-4 fix (re-enabling `elif deleted_keys: save_manifest(...)`
    in find_changed_sources) flips the post-call manifest content, failing
    this test. The previous docstring-grep test passed under that revert.
    """
    import json

    from kb.compile.compiler import detect_source_drift

    # Set up tmp wiki + raw + manifest. Manifest has TWO entries:
    # - "articles/alive.md" referencing a real on-disk file
    # - "articles/deleted.md" referencing a now-missing file (the deletion
    #   case the function is supposed to surface read-only)
    raw_dir = tmp_path / "raw" / "articles"
    raw_dir.mkdir(parents=True)
    alive = raw_dir / "alive.md"
    alive.write_text("# Alive\n", encoding="utf-8")

    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True)

    manifest_path = tmp_path / ".data" / "hashes.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_before = {
        "articles/alive.md": "abc123",
        "articles/deleted.md": "def456",
    }
    manifest_path.write_text(json.dumps(manifest_before, sort_keys=True), encoding="utf-8")
    bytes_before = manifest_path.read_bytes()

    result = detect_source_drift(
        raw_dir=tmp_path / "raw",
        wiki_dir=wiki_dir,
        manifest_path=manifest_path,
    )

    # Manifest content + bytes are byte-identical post-call
    bytes_after = manifest_path.read_bytes()
    assert bytes_after == bytes_before, "detect_source_drift must not mutate manifest"
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest_before

    # And the deleted entry IS surfaced in the result (function is doing its job)
    assert "articles/deleted.md" in result["deleted_sources"]


# ── Linker tests ────────────────────────────────────────────────


def _create_page(path: Path, title: str, content: str, page_type: str = "concept") -> None:
    """Helper to create a wiki page with frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        f'---\ntitle: "{title}"\nsource:\n  - raw/articles/test.md\n'
        f"created: 2026-04-06\nupdated: 2026-04-06\ntype: {page_type}\n"
        f"confidence: stated\n---\n\n"
    )
    path.write_text(fm + content, encoding="utf-8")


def test_resolve_wikilinks(tmp_wiki):
    """resolve_wikilinks finds resolved and broken links."""
    _create_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "Links to [[concepts/llm]] and [[entities/nonexistent]].",
    )
    _create_page(tmp_wiki / "concepts" / "llm.md", "LLM", "LLM content.")
    result = resolve_wikilinks(tmp_wiki)
    assert result["total_links"] == 2
    assert result["resolved"] == 1
    assert len(result["broken"]) == 1
    assert result["broken"][0]["target"] == "entities/nonexistent"


def test_resolve_wikilinks_all_valid(tmp_wiki):
    """resolve_wikilinks reports all resolved when no broken links."""
    _create_page(tmp_wiki / "concepts" / "rag.md", "RAG", "Links to [[concepts/llm]].")
    _create_page(tmp_wiki / "concepts" / "llm.md", "LLM", "Links to [[concepts/rag]].")
    result = resolve_wikilinks(tmp_wiki)
    assert result["total_links"] == 2
    assert result["resolved"] == 2
    assert result["broken"] == []


def test_build_backlinks(tmp_wiki):
    """build_backlinks creates reverse link index."""
    _create_page(
        tmp_wiki / "summaries" / "article1.md",
        "Article 1",
        "Mentions [[concepts/rag]] and [[entities/openai]].",
        page_type="summary",
    )
    _create_page(
        tmp_wiki / "concepts" / "rag.md",
        "RAG",
        "RAG is linked from summaries.",
    )
    _create_page(
        tmp_wiki / "entities" / "openai.md",
        "OpenAI",
        "OpenAI content.",
        page_type="entity",
    )
    backlinks = build_backlinks(tmp_wiki)
    assert "concepts/rag" in backlinks
    assert "summaries/article1" in backlinks["concepts/rag"]
    assert "entities/openai" in backlinks
    assert "summaries/article1" in backlinks["entities/openai"]


def test_build_backlinks_empty(tmp_wiki):
    """build_backlinks returns empty dict for empty wiki."""
    backlinks = build_backlinks(tmp_wiki)
    assert backlinks == {}


def test_compile_loop_does_not_double_write_manifest(tmp_project, monkeypatch):
    """Regression: Phase 4.5 CRITICAL item 14.

    Per-loop manifest save duplicated inner ingest save.

    Cycle 25 AC6 adds an intentional pre-marker save (`in_progress:{hash}`)
    before each ingest_source call, so the post-cycle-25 expected count is
    2 saves per source: (1) pre-marker, (2) ingest_source's own success
    overwrite. The original cycle-17 AC3 intent (no ACCIDENTAL double-writes
    from the loop body) is preserved — the assertion now pins the precise
    cycle-25 contract rather than the pre-cycle-25 count.
    """
    import kb.compile.compiler as compiler_mod
    from kb.compile.compiler import compile_wiki

    call_count = {"save_manifest": 0}
    real_save = compiler_mod.save_manifest

    def counting_save(manifest, path=None):
        call_count["save_manifest"] += 1
        return real_save(manifest, path)

    monkeypatch.setattr(compiler_mod, "save_manifest", counting_save)

    raw_dir = tmp_project / "raw"
    (raw_dir / "articles").mkdir(parents=True, exist_ok=True)
    (raw_dir / "articles" / "one.md").write_text("# One\nbody.", encoding="utf-8")
    manifest_path = tmp_project / ".data" / "hashes_test.json"

    # Stub out ingest_source LLM work while preserving its manifest side effect.
    def fake_ingest_source(source, *a, **k):
        manifest = load_manifest(manifest_path)
        manifest[compiler_mod._canonical_rel_path(source, raw_dir)] = compiler_mod.content_hash(
            source
        )
        real_save(manifest, manifest_path)
        return {
            "pages_created": ["summaries/one"],
            "pages_updated": [],
            "pages_skipped": [],
            "wikilinks_injected": [],
            "affected_pages": [],
        }

    monkeypatch.setattr(
        compiler_mod,
        "ingest_source",
        fake_ingest_source,
    )

    wiki_dir = tmp_project / "wiki"
    compile_wiki(
        raw_dir=raw_dir,
        wiki_dir=wiki_dir,
        manifest_path=manifest_path,
        incremental=True,
    )

    # Cycle 25 AC6: expected count rose from 1 → 2 because the pre-marker
    # write intentionally saves before ingest_source. Cycle-17 AC3's "no
    # accidental double-write" invariant is still pinned — a regression
    # would produce 3+ saves (one extra accidental loop-body save).
    assert call_count["save_manifest"] == 2, (
        f"manifest saved {call_count['save_manifest']}x per source; expected 2 "
        f"(cycle-25 AC6 pre-marker + cycle-17 AC3 success overwrite)"
    )
    manifest_after_first = load_manifest(manifest_path)
    source_entries = {
        k: v for k, v in manifest_after_first.items() if not k.startswith("_template/")
    }
    assert source_entries == {
        "raw/articles/one.md": compiler_mod.content_hash(raw_dir / "articles" / "one.md")
    }

    # Cycle 11 AC13 R1 fix (Codex M2 + Sonnet M1): prove manifest STABILITY across
    # a second same-source compile. A correct implementation should observe no
    # content change (same source, same hash). A future refactor that rewrites
    # the manifest with a different normalised key OR mutates unchanged entries
    # on re-compile would break this assertion even when save-count stays at one.
    call_count["save_manifest"] = 0
    compile_wiki(
        raw_dir=raw_dir,
        wiki_dir=wiki_dir,
        manifest_path=manifest_path,
        incremental=True,
    )
    manifest_after_second = load_manifest(manifest_path)
    assert manifest_after_second == manifest_after_first, (
        "second same-source compile mutated manifest; expected idempotent no-op"
    )


# ── Cycle 9 compiler regression test (cycle 48 fold per AC5) ──────
# Source: tests/test_cycle9_compiler.py (deleted in same commit).
def test_load_manifest_recovers_from_os_error(tmp_path, monkeypatch, caplog):
    import logging

    from kb.compile import compiler

    manifest_path = tmp_path / "hashes.json"
    manifest_path.write_text('{"raw/articles/test.md": "abc123"}', encoding="utf-8")

    original_read_text = compiler.Path.read_text

    def raise_oserror(self, *args, **kwargs):
        if self == manifest_path:
            raise OSError("disk read failed")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(compiler.Path, "read_text", raise_oserror)
    caplog.set_level(logging.WARNING, logger="kb.compile.compiler")

    result = compiler.load_manifest(manifest_path=manifest_path)

    assert result == {}
    assert any(
        str(manifest_path) in record.getMessage() and "disk read failed" in record.getMessage()
        for record in caplog.records
    )
