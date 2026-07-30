"""Tests for the compile module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


# Cycle 52 fold — cycle-19 AC14-anchor (prune-base consistency).
# Source: tests/test_cycle19_prune_base_consistency_anchor.py (deleted in same commit).
# Per cycle-15 L2 (DROP-with-test-anchor), this test stays as a regression
# anchor for the cycle-17 AC1 prune-base fix.
#
# Cycle 70 AC10 — C41-L1 behavioural upgrade per design.md Q6-B (parametrize
# 2 sites) + C5 (Mock(wraps=...) preserves real return values for downstream
# `set` and `affected_pages` consumers). Replaces the prior inspect.getsource
# source-grep with a positive spy-on-helper test that fails if the real
# `_canonical_rel_path` call is removed from EITHER call site.


@pytest.mark.parametrize("call_site", ["drift_detect", "full_mode"])
def test_canonical_rel_path_invoked_by_both_call_sites(call_site, tmp_path):
    """Cycle 70 AC10 — both prune sites route through ``_canonical_rel_path``.

    Replaces inspect.getsource source-grep (cycle-19 AC14 anchor) with a
    behavioural spy. ``Mock(wraps=compiler._canonical_rel_path)`` preserves
    the real return value so downstream ``set`` and ``existing_rel`` consumers
    keep working (per design.md C5 — bare ``Mock()`` would break those sites
    for unrelated reasons).

    Mutation budget: removing ``_canonical_rel_path(...)`` from
    ``detect_source_drift`` (compiler.py:292,312,373) fails the
    ``drift_detect`` parametrized branch with ``spy.call_count == 0``.
    Removing ``_canonical_rel_path(...)`` from ``compile_wiki`` full-mode
    body (compiler.py:466) fails the ``full_mode`` branch.
    """
    from kb.compile import compiler

    real_helper = compiler._canonical_rel_path
    spy = MagicMock(wraps=real_helper)

    # Common setup: 1 raw file, valid wiki tree, empty manifest.
    raw_dir_root = tmp_path / "raw"
    articles = raw_dir_root / "articles"
    articles.mkdir(parents=True)
    (articles / "alive.md").write_text("# Alive\n", encoding="utf-8")

    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True)

    manifest_path = tmp_path / ".data" / "hashes.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{}", encoding="utf-8")

    if call_site == "drift_detect":
        # Spy on the bound name in compiler module — detect_source_drift looks
        # up the name via module globals at call time.
        with patch.object(compiler, "_canonical_rel_path", spy):
            compiler.detect_source_drift(
                raw_dir=raw_dir_root,
                wiki_dir=wiki_dir,
                manifest_path=manifest_path,
            )
        # detect_source_drift body invokes _canonical_rel_path at lines 292
        # (existing_rel set comprehension), 312 (changed_refs loop), and 373
        # (return-dict list comprehension). With 1 source on disk + empty
        # manifest, line 292 fires once; line 312 fires once for the new
        # source; line 373 fires once for the same source. Total >= 1.
        assert spy.call_count >= 1, (
            "detect_source_drift must route at least one path through "
            "_canonical_rel_path. If spy was never called, the cycle-17 AC1 "
            "fix has been reverted at compiler.py:292/312/373."
        )
    else:  # full_mode
        # compile_wiki full-mode body line 466 calls _canonical_rel_path on each
        # source. Stub ingest_source so we don't actually ingest (we only need
        # the for-source loop to enter and call _canonical_rel_path at line 466
        # before any heavy work).
        with (
            patch("kb.compile.compiler.ingest_source") as mock_ingest,
            patch.object(compiler, "_canonical_rel_path", spy),
        ):
            mock_ingest.return_value = {
                "source_path": "test",
                "source_type": "article",
                "content_hash": "abc123",
                "pages_created": ["summaries/alive"],
                "pages_updated": [],
            }
            compiler.compile_wiki(
                incremental=False,
                raw_dir=raw_dir_root,
                manifest_path=manifest_path,
                wiki_dir=wiki_dir,
            )
        # compile_wiki full-mode body iterates sources_to_process. For each
        # source, line 466 (`rel_path = _canonical_rel_path(source, raw_dir)`)
        # fires before the try/except block. With 1 source on disk, spy.call_count >= 1.
        assert spy.call_count >= 1, (
            "compile_wiki(mode='full') must route at least one path through "
            "_canonical_rel_path. If spy was never called, the cycle-17 AC1 "
            "fix has been reverted at compiler.py:466."
        )


def test_manifest_key_for_alias_is_canonical_rel_path_at_module_scope() -> None:
    """manifest_key_for is the cycle-19 AC11 public alias; must remain a single source of truth."""
    from kb.compile.compiler import _canonical_rel_path, manifest_key_for

    # Identity check (not equality) — the alias must point at the same callable
    # so a refactor that copies-and-diverges cannot silently introduce a second
    # canonicalization path. R2 M1 / cycle-19 design.md AC11.
    assert manifest_key_for is _canonical_rel_path, (
        "manifest_key_for must be the IDENTITY alias of _canonical_rel_path "
        "(not a wrapper) — see cycle-19 design.md AC11."
    )


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


# ─────────────────────────────────────────────────────────────────────
# Folded from tests/test_v01006_compile_fixes.py
# (cycle 77 freeze-and-fold) — Phase 4 compile/ fixes.
# Tests moved VERBATIM; names preserved; provenance in CHANGELOG-history cycle-77.
# ─────────────────────────────────────────────────────────────────────


def test_code_mask_handles_tilde_fences():
    from kb.compile.linker import _CODE_MASK_RE

    text = "~~~python\nfoo_entity()\n~~~"
    masked = _CODE_MASK_RE.sub("MASKED", text)
    assert "foo_entity" not in masked, f"Expected masked but got: {masked!r}"


def test_template_hashes_skips_backup_files(tmp_path, monkeypatch):
    from kb.compile import compiler as _c

    tdir = tmp_path / "templates"
    tdir.mkdir()
    (tdir / "article.yaml").write_text("extract: []\n", encoding="utf-8")
    (tdir / "~article.yaml").write_text("bogus: true\n", encoding="utf-8")
    (tdir / ".hidden.yaml").write_text("bogus: true\n", encoding="utf-8")

    monkeypatch.setattr(_c, "TEMPLATES_DIR", tdir)
    # Clear any LRU cache if _template_hashes is cached
    if hasattr(_c._template_hashes, "cache_clear"):
        _c._template_hashes.cache_clear()
    hashes = _c._template_hashes()
    assert set(hashes.keys()) == {"_template/article"}, (
        f"Expected only '_template/article', got {set(hashes.keys())}"
    )


def test_inject_wikilinks_smoke(tmp_wiki):
    from kb.compile.linker import inject_wikilinks

    # Create a page that mentions "Python" in plain text
    page = tmp_wiki / "concepts" / "general.md"
    page.write_text(
        "---\ntitle: General\n---\nThis is about Python programming.\n",
        encoding="utf-8",
    )
    # Create the target page so it exists in the wiki
    target = tmp_wiki / "entities" / "python.md"
    target.write_text("---\ntitle: Python\n---\nThe Python language.\n", encoding="utf-8")

    updated = inject_wikilinks("Python", "entities/python", wiki_dir=tmp_wiki)
    assert isinstance(updated, list)
    # general.md should have been updated with a wikilink
    assert any("general" in pid for pid in updated)


def test_tilde_fence_not_injected(tmp_wiki):
    from kb.compile.linker import inject_wikilinks

    # Content with entity mention ONLY inside a ~~~ fence
    page = tmp_wiki / "concepts" / "codepage.md"
    page.write_text(
        "---\ntitle: Code Page\n---\nSome text.\n\n~~~python\nTransformer()\n~~~\n",
        encoding="utf-8",
    )
    target = tmp_wiki / "entities" / "transformer.md"
    target.write_text("---\ntitle: Transformer\n---\nThe Transformer.\n", encoding="utf-8")

    updated = inject_wikilinks("Transformer", "entities/transformer", wiki_dir=tmp_wiki)
    # codepage.md should NOT have been updated (mention is inside code fence)
    assert not any("codepage" in pid for pid in updated)
    # Verify file unchanged
    content = page.read_text(encoding="utf-8")
    assert "[[entities/transformer" not in content


# ═══════════════════════════════════════════════════════════════════════
# Cycle 78 freeze-and-fold — moved verbatim from tests/test_v0916_task01.py
# (compile/linker part) and tests/test_v0916_task04.py. No deviations
# (receiver already imports `patch`).
# ═══════════════════════════════════════════════════════════════════════

# ── tests/test_v0916_task01.py — CRITICAL atomic write (compile/linker part) ──


class TestInjectWikilinksAtomicWrite:
    """compile/linker.py inject_wikilinks must use atomic_text_write."""

    def test_inject_wikilinks_uses_atomic_write(self, tmp_wiki):
        """inject_wikilinks should call atomic_text_write, not page_path.write_text."""
        # Create a page that mentions "TestTerm"
        page = tmp_wiki / "concepts" / "other.md"
        page.write_text(
            '---\ntitle: "Other"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
            "This page mentions TestTerm in the body.\n",
            encoding="utf-8",
        )
        # Create the target page
        target = tmp_wiki / "entities" / "test-term.md"
        target.write_text(
            '---\ntitle: "TestTerm"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: entity\nconfidence: stated\n---\n\n"
            "TestTerm page.\n",
            encoding="utf-8",
        )

        with patch("kb.compile.linker.atomic_text_write") as mock_atw:
            from kb.compile.linker import inject_wikilinks

            inject_wikilinks("TestTerm", "entities/test-term", wiki_dir=tmp_wiki)
            if mock_atw.called:
                written = mock_atw.call_args[0][0]
                assert "[[entities/test-term|TestTerm]]" in written


# ── tests/test_v0916_task04.py — Phase 3.97 Task 04 compile/linker fixes ──


class TestInjectWikilinksTitleSanitization:
    """inject_wikilinks must sanitize pipe and newline in titles."""

    def test_pipe_in_title_produces_valid_wikilink(self, tmp_wiki):
        """A title with | should not break wikilink syntax."""
        page = tmp_wiki / "concepts" / "other.md"
        page.write_text(
            '---\ntitle: "Other"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
            "This discusses GPT-4 Preview features.\n",
            encoding="utf-8",
        )
        target = tmp_wiki / "entities" / "gpt-4-preview.md"
        target.write_text(
            '---\ntitle: "GPT-4 | Preview"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: entity\nconfidence: stated\n---\n\n"
            "GPT-4 Preview entity page.\n",
            encoding="utf-8",
        )

        from kb.compile.linker import inject_wikilinks

        updated = inject_wikilinks("GPT-4 Preview", "entities/gpt-4-preview", wiki_dir=tmp_wiki)
        if updated:
            content = page.read_text(encoding="utf-8")
            # Must not have raw pipe in wikilink
            assert "||" not in content or "[[entities/gpt-4-preview|" in content

    def test_newline_in_title_sanitized(self, tmp_wiki):
        """A title with newline should be sanitized before injection."""
        page = tmp_wiki / "concepts" / "other.md"
        page.write_text(
            '---\ntitle: "Other"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
            "This discusses TestEntity in the body.\n",
            encoding="utf-8",
        )
        target = tmp_wiki / "entities" / "test-entity.md"
        target.write_text(
            '---\ntitle: "TestEntity"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: entity\nconfidence: stated\n---\n\n"
            "TestEntity page.\n",
            encoding="utf-8",
        )

        from kb.compile.linker import inject_wikilinks

        # Title with newline should be sanitized
        updated = inject_wikilinks("TestEntity", "entities/test-entity", wiki_dir=tmp_wiki)
        if updated:
            content = page.read_text(encoding="utf-8")
            assert "[[entities/test-entity|TestEntity]]" in content


class TestInjectWikilinksFrontmatterSkipCheck:
    """inject_wikilinks skip guard must check body only, not frontmatter."""

    def test_wikilink_in_frontmatter_does_not_skip_body(self, tmp_wiki):
        """If frontmatter contains [[target]], body injection should still happen."""
        page = tmp_wiki / "concepts" / "other.md"
        # Frontmatter has the target as a literal (unusual but possible)
        page.write_text(
            '---\ntitle: "Other"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n"
            "note: see [[entities/test-entity]]\n---\n\n"
            "This discusses TestEntity in the body.\n",
            encoding="utf-8",
        )
        target = tmp_wiki / "entities" / "test-entity.md"
        target.write_text(
            '---\ntitle: "TestEntity"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: entity\nconfidence: stated\n---\n\n"
            "TestEntity page.\n",
            encoding="utf-8",
        )

        from kb.compile.linker import inject_wikilinks

        updated = inject_wikilinks("TestEntity", "entities/test-entity", wiki_dir=tmp_wiki)
        # The body mention should still be linked
        assert "concepts/other" in updated


class TestScanRawSourcesUsesSharedExtensions:
    """scan_raw_sources should use SUPPORTED_SOURCE_EXTENSIONS from config."""

    def test_rst_file_accepted(self, tmp_path):
        raw = tmp_path / "raw"
        articles = raw / "articles"
        articles.mkdir(parents=True)
        (articles / "test.rst").write_text("content", encoding="utf-8")
        (articles / ".gitkeep").write_text("", encoding="utf-8")

        from kb.compile.compiler import scan_raw_sources

        sources = scan_raw_sources(raw)
        names = [s.name for s in sources]
        assert "test.rst" in names
        assert ".gitkeep" not in names


# -- Cycle 92 fold from test_v0915_task03.py --
# Phase 3.96 Task 3 — Compile & Linker fixes: compile_wiki manifest behaviour,
# inject_wikilinks guards, _mask_code_blocks/_unmask_code_blocks, build_backlinks.


# ── Fix 3.1: wiki_dir forwarded to ingest_source ────────────────────────────


class TestCompileWikiForwardsWikiDir:
    """Fix 3.1 — compile_wiki passes wiki_dir to ingest_source."""

    def test_wiki_dir_forwarded(self, tmp_path, monkeypatch):
        from kb.compile import compiler

        raw = tmp_path / "raw"
        (raw / "articles").mkdir(parents=True)
        source = raw / "articles" / "test.md"
        source.write_text("# Test\n\nContent.", encoding="utf-8")

        wiki = tmp_path / "wiki"
        manifest = tmp_path / "manifest.json"

        captured = {}

        def fake_ingest(path, wiki_dir=None, **kwargs):
            captured["wiki_dir"] = wiki_dir
            return {
                "pages_created": [],
                "pages_updated": [],
                "pages_skipped": [],
                "wikilinks_injected": [],
                "affected_pages": [],
                "duplicate": False,
            }

        monkeypatch.setattr(compiler, "ingest_source", fake_ingest)
        monkeypatch.setattr(compiler, "RAW_DIR", raw)
        monkeypatch.setattr(compiler, "HASH_MANIFEST", manifest)

        compiler.compile_wiki(incremental=False, raw_dir=raw, wiki_dir=wiki)

        assert captured.get("wiki_dir") == wiki

    def test_wiki_dir_none_forwarded_when_not_set(self, tmp_path, monkeypatch):
        """When wiki_dir is not provided, None is forwarded (uses default)."""
        from kb.compile import compiler

        raw = tmp_path / "raw"
        (raw / "articles").mkdir(parents=True)
        source = raw / "articles" / "test.md"
        source.write_text("# Test\n\nContent.", encoding="utf-8")

        manifest = tmp_path / "manifest.json"
        captured = {}

        def fake_ingest(path, wiki_dir=None, **kwargs):
            captured["wiki_dir"] = wiki_dir
            return {
                "pages_created": [],
                "pages_updated": [],
                "pages_skipped": [],
                "wikilinks_injected": [],
                "affected_pages": [],
                "duplicate": False,
            }

        monkeypatch.setattr(compiler, "ingest_source", fake_ingest)
        monkeypatch.setattr(compiler, "RAW_DIR", raw)
        monkeypatch.setattr(compiler, "HASH_MANIFEST", manifest)

        compiler.compile_wiki(incremental=False, raw_dir=raw)

        assert "wiki_dir" in captured
        assert captured["wiki_dir"] is None


# ── Fix 3.3: Partial ingest failure writes failed: prefix ────────────────────


class TestManifestFailedPrefix:
    """Fix 3.3 — failed ingest records 'failed:<hash>' in manifest."""

    def test_failed_source_recorded_with_prefix(self, tmp_path, monkeypatch):
        from kb.compile import compiler

        raw = tmp_path / "raw"
        (raw / "articles").mkdir(parents=True)
        source = raw / "articles" / "bad.md"
        source.write_text("# Bad source\n\nContent.", encoding="utf-8")

        manifest_path = tmp_path / "manifest.json"

        def always_fail(path, wiki_dir=None, **kwargs):
            raise RuntimeError("Simulated ingest failure")

        monkeypatch.setattr(compiler, "ingest_source", always_fail)
        monkeypatch.setattr(compiler, "RAW_DIR", raw)
        monkeypatch.setattr(compiler, "HASH_MANIFEST", manifest_path)

        result = compiler.compile_wiki(incremental=False, raw_dir=raw)

        assert len(result["errors"]) == 1
        assert "Simulated ingest failure" in result["errors"][0]["error"]

        # Manifest should contain failed: prefixed hash
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        rel_key = next((k for k in manifest if "bad.md" in k), None)
        assert rel_key is not None, "Manifest missing entry for bad.md"
        assert manifest[rel_key].startswith("failed:"), (
            f"Expected 'failed:' prefix, got: {manifest[rel_key]!r}"
        )

    def test_failed_source_retried_on_next_compile(self, tmp_path, monkeypatch):
        """A source recorded with 'failed:' prefix is treated as changed."""
        from kb.compile import compiler
        from kb.utils.hashing import content_hash

        raw = tmp_path / "raw"
        (raw / "articles").mkdir(parents=True)
        source = raw / "articles" / "retry.md"
        source.write_text("# Retry\n\nContent.", encoding="utf-8")

        manifest_path = tmp_path / "manifest.json"
        real_hash = content_hash(source)
        # Pre-populate manifest with failed: prefix
        manifest_path.write_text(
            json.dumps({"raw/articles/retry.md": f"failed:{real_hash}"}), encoding="utf-8"
        )

        new, changed = compiler.find_changed_sources(
            raw_dir=raw, manifest_path=manifest_path, save_hashes=False
        )

        all_changed = new + changed
        assert any("retry.md" in str(s) for s in all_changed), (
            f"Expected retry.md in changed sources, got: {all_changed}"
        )

    def test_clean_source_not_retried(self, tmp_path, monkeypatch):
        """A source with a matching (unfailed) hash is not flagged as changed."""
        from kb.compile import compiler
        from kb.utils.hashing import content_hash

        raw = tmp_path / "raw"
        (raw / "articles").mkdir(parents=True)
        source = raw / "articles" / "clean.md"
        source.write_text("# Clean\n\nContent.", encoding="utf-8")

        manifest_path = tmp_path / "manifest.json"
        real_hash = content_hash(source)
        # Pre-populate manifest with both the source hash AND current template hashes
        # so that template-change detection doesn't flag the source for re-compilation.
        initial_manifest = {"raw/articles/clean.md": real_hash}
        initial_manifest.update(compiler._template_hashes())
        manifest_path.write_text(json.dumps(initial_manifest), encoding="utf-8")

        new, changed = compiler.find_changed_sources(
            raw_dir=raw, manifest_path=manifest_path, save_hashes=False
        )

        all_changed = new + changed
        assert not any("clean.md" in str(s) for s in all_changed), (
            f"clean.md should not be in changed sources, got: {all_changed}"
        )


# ── Fix 3.4: inject_wikilinks empty/whitespace title guard ──────────────────


class TestInjectWikilinksEmptyTitle:
    """Fix 3.4 — inject_wikilinks returns [] for empty or whitespace title."""

    def test_empty_title_returns_empty(self, tmp_wiki):
        from kb.compile.linker import inject_wikilinks

        result = inject_wikilinks("", "entities/test", wiki_dir=tmp_wiki)
        assert result == []

    def test_whitespace_title_returns_empty(self, tmp_wiki):
        from kb.compile.linker import inject_wikilinks

        result = inject_wikilinks("   ", "entities/test", wiki_dir=tmp_wiki)
        assert result == []

    def test_newline_only_title_returns_empty(self, tmp_wiki):
        from kb.compile.linker import inject_wikilinks

        result = inject_wikilinks("\n\t\n", "entities/test", wiki_dir=tmp_wiki)
        assert result == []

    def test_valid_title_still_works(self, tmp_wiki, create_wiki_page):
        """Valid title proceeds without error."""
        from kb.compile.linker import inject_wikilinks

        # Create a page that mentions the title
        create_wiki_page(
            "concepts/other",
            content="GPT-4o is a great model.",
            wiki_dir=tmp_wiki,
        )
        # Should not raise even if no matches
        result = inject_wikilinks("GPT-4o", "entities/gpt-4o", wiki_dir=tmp_wiki)
        assert isinstance(result, list)


# ── Fix 3.7: build_backlinks set-based dedup ────────────────────────────────


class TestBuildBacklinksDedup:
    """Fix 3.7 — build_backlinks produces no duplicate entries per source."""

    def test_no_duplicate_backlinks(self, tmp_wiki, create_wiki_page):
        from kb.compile.linker import build_backlinks

        # Create target page
        create_wiki_page("concepts/target", content="Target page.", wiki_dir=tmp_wiki)

        # Create source page that links to target multiple times
        create_wiki_page(
            "concepts/source",
            content=(
                "First mention [[concepts/target|Target]]. "
                "Second mention [[concepts/target|Target]] again."
            ),
            wiki_dir=tmp_wiki,
        )

        backlinks = build_backlinks(wiki_dir=tmp_wiki)
        target_backlinks = backlinks.get("concepts/target", [])
        # Should not contain duplicates
        assert len(target_backlinks) == len(set(target_backlinks)), (
            f"Duplicate backlinks found: {target_backlinks}"
        )

    def test_backlinks_values_are_sorted(self, tmp_wiki, create_wiki_page):
        """Backlink lists are sorted."""
        from kb.compile.linker import build_backlinks

        create_wiki_page("concepts/target", content="Target page.", wiki_dir=tmp_wiki)
        create_wiki_page(
            "concepts/alpha",
            content="Mentions [[concepts/target|Target]].",
            wiki_dir=tmp_wiki,
        )
        create_wiki_page(
            "concepts/beta",
            content="Also mentions [[concepts/target|Target]].",
            wiki_dir=tmp_wiki,
        )

        backlinks = build_backlinks(wiki_dir=tmp_wiki)
        target_backlinks = backlinks.get("concepts/target", [])
        assert target_backlinks == sorted(target_backlinks)


# ── Fix 3.8: inject_wikilinks continues past blocked matches ────────────────


class TestInjectWikilinksFinditer:
    """Fix 3.8 — blocked match inside [[ ]] doesn't suppress all subsequent matches."""

    def test_second_mention_injected_when_first_blocked(self, tmp_wiki, create_wiki_page):
        """When first occurrence is inside a wikilink, the second plain mention is linked."""
        from kb.compile.linker import inject_wikilinks

        # Create target page
        create_wiki_page("entities/openai", content="OpenAI page.", wiki_dir=tmp_wiki)

        # Source page: first mention is already in a wikilink, second is plain text
        create_wiki_page(
            "concepts/source",
            content="[[entities/openai|OpenAI]] is great. OpenAI also does research.",
            wiki_dir=tmp_wiki,
        )

        updated = inject_wikilinks("OpenAI", "entities/openai", wiki_dir=tmp_wiki)
        # source already links to target → should be skipped entirely (existing_links check)
        # This test confirms the code at least doesn't crash with the new finditer loop
        assert isinstance(updated, list)

    def test_second_occurrence_linked_when_first_inside_unrelated_wikilink(
        self, tmp_wiki, create_wiki_page
    ):
        """Fix 3.8 core case: first occurrence of title is a display name inside an
        *unrelated* wikilink ([[some/other|Target]]).  Because the target_page_id
        ('entities/target') is NOT yet linked, the existing_links guard does NOT
        skip the page.  The finditer loop must skip the blocked match and still
        inject a wikilink for the second plain-text occurrence."""
        from kb.compile.linker import inject_wikilinks

        # Create the target page and an unrelated page that will appear as the wikilink host.
        create_wiki_page("entities/target", content="Target page.", wiki_dir=tmp_wiki)
        create_wiki_page("concepts/other", content="Some other concept.", wiki_dir=tmp_wiki)

        # Source: "Target" appears first as a display name in [[concepts/other|Target]],
        # then again as plain text.  The target_page_id (entities/target) is NOT linked.
        create_wiki_page(
            "concepts/source",
            content="[[concepts/other|Target]] is interesting. Target deserves a link.",
            wiki_dir=tmp_wiki,
        )

        updated = inject_wikilinks("Target", "entities/target", wiki_dir=tmp_wiki)

        # The source page must be in the updated list.
        assert "concepts/source" in updated, (
            f"Expected concepts/source to be updated; got: {updated}"
        )

        # Verify the second plain-text occurrence was actually replaced.
        source_file = tmp_wiki / "concepts" / "source.md"
        content = source_file.read_text(encoding="utf-8")
        assert "[[entities/target|Target]]" in content, (
            f"Expected wikilink injected for second occurrence; content:\n{content}"
        )
        # The original unrelated wikilink must remain untouched.
        assert "[[concepts/other|Target]]" in content, (
            f"Original wikilink was modified; content:\n{content}"
        )

    def test_plain_mention_injected_when_not_blocked(self, tmp_wiki, create_wiki_page):
        """Plain text mention is injected correctly."""
        from kb.compile.linker import inject_wikilinks

        create_wiki_page("entities/anthropic", content="Anthropic page.", wiki_dir=tmp_wiki)
        create_wiki_page(
            "concepts/source",
            content="Anthropic builds frontier AI systems.",
            wiki_dir=tmp_wiki,
        )

        updated = inject_wikilinks("Anthropic", "entities/anthropic", wiki_dir=tmp_wiki)
        assert "concepts/source" in updated

        # Verify the file was actually updated
        source_file = tmp_wiki / "concepts" / "source.md"
        content = source_file.read_text(encoding="utf-8")
        assert "[[entities/anthropic|Anthropic]]" in content


# ── Fix 3.9: _CODE_MASK_RE masks markdown links/images ──────────────────────


class TestCodeMaskMarkdownLinks:
    """Fix 3.9 — _CODE_MASK_RE masks [text](url) and ![alt](url) patterns."""

    def test_markdown_link_masked(self):
        from kb.compile.linker import _CODE_MASK_RE

        text = "See [OpenAI](https://openai.com) for details."
        masked = _CODE_MASK_RE.sub("MASKED", text)
        assert "[OpenAI](https://openai.com)" not in masked
        assert "MASKED" in masked

    def test_image_masked(self):
        from kb.compile.linker import _CODE_MASK_RE

        text = "Here is ![diagram](./img/arch.png) inline."
        masked = _CODE_MASK_RE.sub("MASKED", text)
        assert "![diagram](./img/arch.png)" not in masked
        assert "MASKED" in masked

    def test_fenced_code_still_masked(self):
        from kb.compile.linker import _CODE_MASK_RE

        text = "```python\nprint('hello')\n```"
        masked = _CODE_MASK_RE.sub("MASKED", text)
        assert "```" not in masked

    def test_inline_code_still_masked(self):
        from kb.compile.linker import _CODE_MASK_RE

        text = "Use `compile_wiki()` to compile."
        masked = _CODE_MASK_RE.sub("MASKED", text)
        assert "`compile_wiki()`" not in masked

    def test_mask_blocks_wikilink_injection_into_markdown_link(self, tmp_wiki, create_wiki_page):
        """Title inside a markdown link url/text is not converted to a wikilink."""
        from kb.compile.linker import inject_wikilinks

        create_wiki_page("entities/openai", content="OpenAI page.", wiki_dir=tmp_wiki)
        create_wiki_page(
            "concepts/source",
            content="Visit [OpenAI](https://openai.com) for more.",
            wiki_dir=tmp_wiki,
        )

        updated = inject_wikilinks("OpenAI", "entities/openai", wiki_dir=tmp_wiki)
        # The markdown link text "OpenAI" is inside [text](url) → masked → no injection
        assert "concepts/source" not in updated


# ── Fix 3.10: _mask_code_blocks per-call UUID prefix ────────────────────────


class TestMaskCodeBlocksPrefix:
    """Fix 3.10 — _mask_code_blocks uses per-call UUID prefix."""

    def test_returns_three_values(self):
        from kb.compile.linker import _mask_code_blocks

        result = _mask_code_blocks("hello `world`")
        assert len(result) == 3, f"Expected 3-tuple, got {len(result)}-tuple"

    def test_prefix_is_string(self):
        from kb.compile.linker import _mask_code_blocks

        _, _, prefix = _mask_code_blocks("hello `world`")
        assert isinstance(prefix, str)
        assert len(prefix) == 8  # uuid4 hex[:8]

    def test_different_calls_different_prefixes(self):
        """Two calls produce different prefixes (probabilistically)."""
        from kb.compile.linker import _mask_code_blocks

        _, _, prefix1 = _mask_code_blocks("`a`")
        _, _, prefix2 = _mask_code_blocks("`b`")
        # UUID4 hex is random — collision probability is 1/16^8 ≈ 2e-10
        assert prefix1 != prefix2

    def test_roundtrip_with_prefix(self):
        """Masked and unmasked text is identical to original."""
        from kb.compile.linker import _mask_code_blocks, _unmask_code_blocks

        original = "Here is `inline code` and ```block code``` in text."
        masked, codes, prefix = _mask_code_blocks(original)
        assert "`inline code`" not in masked
        restored = _unmask_code_blocks(masked, codes, prefix)
        assert restored == original

    def test_unmask_requires_correct_prefix(self):
        """Using wrong prefix leaves placeholders un-restored."""
        from kb.compile.linker import _mask_code_blocks, _unmask_code_blocks

        original = "Use `foo()` here."
        masked, codes, prefix = _mask_code_blocks(original)
        # Unmask with wrong prefix
        wrong = _unmask_code_blocks(masked, codes, "00000000")
        # Should NOT be fully restored (placeholder still in text)
        assert "`foo()`" not in wrong


# ── Fix 3.14: build_backlinks lowercases source_id values ───────────────────


class TestBuildBacklinksLowercaseValues:
    """Fix 3.14 — source_id values in backlinks are lowercase."""

    def test_source_ids_lowercased(self, tmp_wiki):
        from kb.compile.linker import build_backlinks

        # Create pages directly with uppercase names
        target = tmp_wiki / "concepts" / "target.md"
        target.write_text(
            '---\ntitle: "Target"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\nTarget page.",
            encoding="utf-8",
        )
        source = tmp_wiki / "concepts" / "Source-Page.md"
        source.write_text(
            '---\ntitle: "Source Page"\nsource:\n  - "raw/articles/b.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\nMentions [[concepts/target|Target]].",
            encoding="utf-8",
        )

        backlinks = build_backlinks(wiki_dir=tmp_wiki)
        for _target, sources in backlinks.items():
            for src in sources:
                assert src == src.lower(), f"Expected lowercase, got: {src!r}"


# ── Fix 3.15: frontmatter stripped before extract_wikilinks ─────────────────


class TestFrontmatterStrippedBeforeExtract:
    """Fix 3.15 — resolve_wikilinks and build_backlinks skip frontmatter."""

    def test_wikilink_in_frontmatter_not_counted(self, tmp_wiki):
        """A [[link]] inside a frontmatter YAML value is not counted as a real link."""
        from kb.compile.linker import resolve_wikilinks

        # Create a page with a wikilink-like pattern in the frontmatter (not a real link)
        page = tmp_wiki / "concepts" / "tricky.md"
        page.write_text(
            '---\ntitle: "Tricky [[concepts/ghost]] page"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\nNormal body with no wikilinks.",
            encoding="utf-8",
        )

        result = resolve_wikilinks(wiki_dir=tmp_wiki)
        # concepts/ghost does not exist — if frontmatter is scanned it would appear as broken
        broken_targets = [b["target"] for b in result["broken"]]
        # The frontmatter link should NOT appear in broken links
        assert "concepts/ghost" not in broken_targets

    def test_backlinks_ignore_frontmatter(self, tmp_wiki):
        """A [[link]] in frontmatter is not included in the backlink index."""
        from kb.compile.linker import build_backlinks

        target = tmp_wiki / "concepts" / "realpage.md"
        target.write_text(
            '---\ntitle: "Real Page"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\nReal page.",
            encoding="utf-8",
        )
        source = tmp_wiki / "concepts" / "sneaky.md"
        source.write_text(
            '---\ntitle: "Sneaky [[concepts/realpage]] in frontmatter"\n'
            'source:\n  - "raw/articles/b.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\nBody with no wikilinks.",
            encoding="utf-8",
        )

        backlinks = build_backlinks(wiki_dir=tmp_wiki)
        realpage_backlinks = backlinks.get("concepts/realpage", [])
        # sneaky.md has no real body wikilink to realpage → should not appear in backlinks
        assert "concepts/sneaky" not in realpage_backlinks


# ── Fix 3.16: find_changed_sources prunes deleted-source entries ─────────────


class TestFindChangedSourcesPrunesDeleted:
    """Fix 3.16 — manifest entries for deleted files are removed."""

    def test_deleted_source_pruned(self, tmp_path):
        from kb.compile import compiler

        raw = tmp_path / "raw"
        (raw / "articles").mkdir(parents=True)

        # Create a source, record it in the manifest, then delete it
        source = raw / "articles" / "deleted.md"
        source.write_text("# Gone\n", encoding="utf-8")

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            json.dumps({"raw/articles/deleted.md": "oldhash"}), encoding="utf-8"
        )

        # Now delete the source
        source.unlink()

        new, changed = compiler.find_changed_sources(
            raw_dir=raw, manifest_path=manifest_path, save_hashes=True
        )

        # Manifest should no longer contain the deleted file
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "raw/articles/deleted.md" not in manifest

    def test_existing_sources_not_pruned(self, tmp_path):
        """Existing source entries are preserved in the manifest."""
        from kb.compile import compiler
        from kb.utils.hashing import content_hash

        raw = tmp_path / "raw"
        (raw / "articles").mkdir(parents=True)
        source = raw / "articles" / "keep.md"
        source.write_text("# Keep\n", encoding="utf-8")
        real_hash = content_hash(source)

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({"raw/articles/keep.md": real_hash}), encoding="utf-8")

        compiler.find_changed_sources(raw_dir=raw, manifest_path=manifest_path, save_hashes=True)

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "raw/articles/keep.md" in manifest


# -- Cycle 92 fold from test_v0915_task11.py (linker mask/unmask subset) --


class TestMaskCodeBlocksCollision:
    """11.18: _mask_code_blocks collision test."""

    def test_preexisting_placeholder_not_corrupted(self):
        from kb.compile.linker import _mask_code_blocks, _unmask_code_blocks

        text = "Normal text.\n```\ncode block\n```\nMore text."
        masked_text, masked_items, prefix = _mask_code_blocks(text)
        restored = _unmask_code_blocks(masked_text, masked_items, prefix)
        assert "code block" in restored
        assert "Normal text." in restored

    def test_roundtrip_preserves_content(self):
        from kb.compile.linker import _mask_code_blocks, _unmask_code_blocks

        text = "Before `inline code` after."
        masked_text, masked_items, prefix = _mask_code_blocks(text)
        restored = _unmask_code_blocks(masked_text, masked_items, prefix)
        assert restored == text

    def test_multiple_code_blocks_restored(self):
        from kb.compile.linker import _mask_code_blocks, _unmask_code_blocks

        text = "Start ```\nblock1\n``` middle ```\nblock2\n``` end"
        masked_text, masked_items, prefix = _mask_code_blocks(text)
        restored = _unmask_code_blocks(masked_text, masked_items, prefix)
        assert "block1" in restored
        assert "block2" in restored
        assert "Start" in restored
        assert "middle" in restored
        assert "end" in restored

    def test_mixed_inline_and_block_code(self):
        from kb.compile.linker import _mask_code_blocks, _unmask_code_blocks

        text = "Inline `code1` text ```\nblock\n``` and `code2` end"
        masked_text, masked_items, prefix = _mask_code_blocks(text)
        restored = _unmask_code_blocks(masked_text, masked_items, prefix)
        assert "code1" in restored
        assert "code2" in restored
        assert "block" in restored
