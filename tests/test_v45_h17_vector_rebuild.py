"""Regression: Phase 4.5 HIGH item H17 — hybrid vector-index lifecycle.

Covers:
- Module-load-time _hybrid_available flag
- rebuild_vector_index() with mtime gate + _rebuild_lock
- _skip_vector_rebuild kwarg on ingest_source
- compile_wiki single rebuild at loop tail
"""

import logging
import os
import sys
from unittest.mock import patch

import pytest

from kb.query.embeddings import _hybrid_available

# ---------------------------------------------------------------------------
# Helper: skip if hybrid deps are not available
# ---------------------------------------------------------------------------


def _require_hybrid():
    """Skip the calling test if model2vec/sqlite-vec are not installed."""
    if not _hybrid_available:
        pytest.skip("model2vec + sqlite-vec not installed — hybrid search unavailable")


# ---------------------------------------------------------------------------
# Test 1: ingest_source calls rebuild_vector_index at tail (when deps present)
# ---------------------------------------------------------------------------


class TestIngestSourceCreatesVectorIndex:
    """H17 T1: ingest_source triggers a vector index rebuild at tail."""

    def test_ingest_source_creates_vector_index(self, tmp_project, monkeypatch):
        """After ingest_source, .data/vector_index.db should exist."""
        _require_hybrid()

        from kb.ingest.pipeline import ingest_source

        # Create a minimal raw source in tmp_project
        raw_dir = tmp_project / "raw"
        articles_dir = raw_dir / "articles"
        articles_dir.mkdir(parents=True, exist_ok=True)
        source_file = articles_dir / "test-h17.md"
        source_file.write_text("# Test H17\n\nThis is a test article for H17.", encoding="utf-8")

        # Patch RAW_DIR so the path validation passes for tmp_project
        monkeypatch.setattr("kb.ingest.pipeline.RAW_DIR", raw_dir, raising=False)
        monkeypatch.setattr("kb.utils.paths.RAW_DIR", raw_dir, raising=False)

        extraction = {
            "title": "Test H17",
            "core_argument": "Testing vector index rebuild.",
            "key_claims": ["Hybrid search relies on vector index."],
            "entities_mentioned": [],
            "concepts_mentioned": [],
        }

        wiki_dir = tmp_project / "wiki"
        ingest_source(source_file, extraction=extraction, wiki_dir=wiki_dir)

        # The vec DB lands next to .data/ relative to wiki_dir's parent
        vec_db = tmp_project / ".data" / "vector_index.db"
        assert vec_db.exists(), f"vector_index.db not found at {vec_db}"


# ---------------------------------------------------------------------------
# Test 2: _skip_vector_rebuild=True suppresses the rebuild
# ---------------------------------------------------------------------------


class TestSkipVectorRebuildParam:
    """H17 T2: _skip_vector_rebuild=True prevents rebuild_vector_index call."""

    def test_ingest_source_skip_vector_rebuild_param(self, tmp_project, monkeypatch):
        """With _skip_vector_rebuild=True, rebuild_vector_index is NOT called."""
        from kb.ingest.pipeline import ingest_source

        raw_dir = tmp_project / "raw"
        articles_dir = raw_dir / "articles"
        articles_dir.mkdir(parents=True, exist_ok=True)
        source_file = articles_dir / "test-h17-skip.md"
        source_file.write_text("# Skip Test\n\nShould not rebuild.", encoding="utf-8")

        # Patch RAW_DIR so the path validation passes for tmp_project
        monkeypatch.setattr("kb.ingest.pipeline.RAW_DIR", raw_dir, raising=False)
        monkeypatch.setattr("kb.utils.paths.RAW_DIR", raw_dir, raising=False)

        extraction = {
            "title": "Skip Test",
            "core_argument": "No rebuild.",
            "key_claims": [],
            "entities_mentioned": [],
            "concepts_mentioned": [],
        }

        wiki_dir = tmp_project / "wiki"

        with patch("kb.query.embeddings.rebuild_vector_index") as mock_rebuild:
            ingest_source(
                source_file,
                extraction=extraction,
                wiki_dir=wiki_dir,
                _skip_vector_rebuild=True,
            )
            mock_rebuild.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: mtime-gated rebuild skips if DB is newer than all pages
# ---------------------------------------------------------------------------


class TestMtimeGatedRebuildSkipsFresh:
    """H17 T3: rebuild_vector_index returns False when vec DB is newer than pages."""

    def test_mtime_gated_rebuild_skips_fresh(self, tmp_wiki, tmp_path):
        """Second rebuild skips because db_mtime > newest page mtime."""
        _require_hybrid()

        from kb.query.embeddings import _is_rebuild_needed, rebuild_vector_index

        # Create a minimal wiki page
        entities_dir = tmp_wiki / "entities"
        entities_dir.mkdir(parents=True, exist_ok=True)
        page = entities_dir / "test-entity.md"
        page.write_text(
            "---\ntitle: Test\nsource:\n  - raw/articles/x.md\n"
            "created: 2026-01-01\nupdated: 2026-01-01\n"
            "type: entity\nconfidence: stated\n---\n\n# Test\n",
            encoding="utf-8",
        )

        # First rebuild: builds the index
        result1 = rebuild_vector_index(tmp_wiki)
        assert result1 is True, "First rebuild should succeed"

        # Force the DB mtime to be 2 seconds AFTER the newest page mtime
        vec_db = tmp_wiki.parent / ".data" / "vector_index.db"
        assert vec_db.exists()
        newest_page_mtime = page.stat().st_mtime
        future_mtime = newest_page_mtime + 2.0
        os.utime(vec_db, (future_mtime, future_mtime))

        # Mtime check should now say "no rebuild needed"
        assert not _is_rebuild_needed(tmp_wiki), "DB newer than pages → rebuild NOT needed"

        # Second rebuild call should skip (return False)
        result2 = rebuild_vector_index(tmp_wiki)
        assert result2 is False, "Second rebuild should be skipped (mtime gate)"


# ---------------------------------------------------------------------------
# Test 4: compile_wiki calls rebuild_vector_index exactly once at tail
# ---------------------------------------------------------------------------


class TestCompileWikiSingleRebuildAtTail:
    """H17 T4: compile_wiki calls rebuild_vector_index exactly once (not per-source)."""

    def test_compile_wiki_single_rebuild_at_tail(self, tmp_project):
        """Verify rebuild_vector_index is called exactly once after all sources processed."""
        from kb.compile.compiler import compile_wiki

        raw_dir = tmp_project / "raw"
        articles_dir = raw_dir / "articles"
        articles_dir.mkdir(parents=True, exist_ok=True)

        # Create 3 source files
        for i in range(3):
            f = articles_dir / f"source-{i}.md"
            f.write_text(f"# Source {i}\n\nContent for source {i}.", encoding="utf-8")

        wiki_dir = tmp_project / "wiki"

        # Patch rebuild at the module where it is imported inside compiler.py
        with patch("kb.query.embeddings.rebuild_vector_index") as mock_rebuild:
            mock_rebuild.return_value = False  # Return value doesn't matter

            # Also patch ingest_source to avoid actual LLM calls
            with patch("kb.compile.compiler.ingest_source") as mock_ingest:
                mock_ingest.return_value = {
                    "pages_created": [],
                    "pages_updated": [],
                    "pages_skipped": [],
                    "wikilinks_injected": [],
                    "affected_pages": [],
                    "duplicate": False,
                }
                compile_wiki(incremental=False, raw_dir=raw_dir, wiki_dir=wiki_dir)

            # rebuild_vector_index should have been called exactly ONCE (at loop tail)
            # NOT once per source (which would be 3 times)
            assert mock_rebuild.call_count == 1, (
                f"Expected rebuild_vector_index called exactly 1 time, "
                f"got {mock_rebuild.call_count}"
            )


# ---------------------------------------------------------------------------
# Test 5: _hybrid_available=False when imports are missing
# ---------------------------------------------------------------------------


class TestHybridFlagFalseWhenImportsMissing:
    """H17 T5: _hybrid_available is False and warning logged when deps are absent."""

    def test_hybrid_flag_false_when_imports_missing(self, caplog):
        """Monkeypatching away model2vec/sqlite_vec causes _hybrid_available=False."""
        # Save originals
        original_modules = {
            k: sys.modules[k] for k in ("model2vec", "sqlite_vec") if k in sys.modules
        }
        # Also remove from sys.modules so importlib.reload sees the mocked state
        for mod_name in ("model2vec", "sqlite_vec"):
            sys.modules.pop(mod_name, None)

        # Make the imports fail
        import builtins

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name in ("model2vec", "sqlite_vec"):
                raise ImportError(f"Mocked missing: {name}")
            return original_import(name, *args, **kwargs)

        # Remove the module so it reloads fresh
        sys.modules.pop("kb.query.embeddings", None)

        try:
            with patch.object(builtins, "__import__", side_effect=_mock_import):
                with caplog.at_level(logging.WARNING, logger="kb.query.embeddings"):
                    import kb.query.embeddings as emb_fresh

            assert emb_fresh._hybrid_available is False, (
                "_hybrid_available should be False when model2vec/sqlite_vec missing"
            )
            # Warning should have been emitted
            assert any("Hybrid search disabled" in r.message for r in caplog.records), (
                "Expected 'Hybrid search disabled' warning in logs"
            )
        finally:
            # Restore sys.modules
            sys.modules.pop("kb.query.embeddings", None)
            for mod_name, mod in original_modules.items():
                sys.modules[mod_name] = mod
            # Re-import to restore normal state
            import kb.query.embeddings  # noqa: F401
