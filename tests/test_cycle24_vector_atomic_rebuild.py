"""Cycle 24 AC5/AC6/AC7/AC8 — vector-index atomic rebuild via tmp-then-replace.

Regression tests for:
- AC5: rebuild writes to ``<vec_db>.tmp`` and ``os.replace``-swaps atomically.
- AC6: stale ``<vec_db>.tmp`` from crashed prior run is unlinked at entry.
- AC7: ``VectorIndex.build`` accepts keyword-only ``db_path`` override.
- AC8: crash during build leaves no tmp and does not touch production DB.
- CONDITION 2: ``_index_cache.pop`` + explicit ``_conn.close()`` BEFORE
  ``os.replace`` (Windows handle-release contract).

Closes threats T1, T2, T9, T10 from `2026-04-23-cycle24-design.md`.
"""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kb.query import embeddings as embeddings_mod
from kb.query.embeddings import VectorIndex, _vec_db_path, rebuild_vector_index


def _fake_model(dim: int = 4):
    """Stub model that replaces ``model2vec.StaticModel.from_pretrained`` via
    monkeypatch. ``encode`` returns a deterministic 2D numpy-like array.
    """
    import numpy as np

    class _StubModel:
        def encode(self, texts):
            return np.array([[float(i + 1)] * dim for i in range(len(texts))], dtype=np.float32)

    return _StubModel()


def _seed_wiki_with_page(wiki_dir: Path, page_name: str = "entities/foo.md") -> None:
    """Create a minimal wiki page so ``load_all_pages`` returns a non-empty list."""
    page = wiki_dir / page_name
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "---\n"
        "title: Foo\n"
        "source:\n"
        "  - raw/articles/source.md\n"
        "created: 2026-01-01\n"
        "updated: 2026-01-01\n"
        "type: entity\n"
        "confidence: stated\n"
        "---\n\n"
        "# Foo\n\nSome content.\n",
        encoding="utf-8",
    )


@pytest.fixture
def hybrid_wiki(tmp_path, monkeypatch):
    """Set up a ``.data`` + ``wiki/`` layout; force hybrid enabled + model stub."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (tmp_path / ".data").mkdir()
    _seed_wiki_with_page(wiki_dir)
    monkeypatch.setattr(embeddings_mod, "_hybrid_available", True)
    monkeypatch.setattr(embeddings_mod, "_get_model", lambda: _fake_model())
    # Reset cache/state before each test.
    embeddings_mod._index_cache.clear()
    monkeypatch.setattr(embeddings_mod, "_model", None)
    return wiki_dir


def test_stale_tmp_unlinked_at_entry(hybrid_wiki, monkeypatch):
    """AC6 — a stale ``<vec_db>.tmp`` from a crashed prior run is unlinked
    unconditionally at rebuild entry (before any gate or lock)."""
    vec_path = _vec_db_path(hybrid_wiki)
    tmp_path = vec_path.parent / (vec_path.name + ".tmp")
    # Seed a dummy stale tmp with recognisable bytes.
    tmp_path.write_bytes(b"STALE BYTES FROM CRASHED PRIOR RUN")
    assert tmp_path.exists()

    result = rebuild_vector_index(hybrid_wiki, force=True)
    assert result is True

    # After rebuild, vec_path exists and the stale tmp is gone.
    assert vec_path.exists()
    assert not tmp_path.exists(), "Stale tmp must not persist after successful rebuild"
    # The stale bytes must NOT appear in the final vec_path (would mean the
    # stale tmp was just renamed into place without a real rebuild).
    assert b"STALE BYTES" not in vec_path.read_bytes()


def test_os_replace_called_with_correct_paths(hybrid_wiki, monkeypatch):
    """AC5 — ``os.replace(tmp_path, vec_path)`` is called exactly once with
    the right path pair. Divergent-fails on revert to direct in-place write."""
    vec_path = _vec_db_path(hybrid_wiki)
    tmp_path = vec_path.parent / (vec_path.name + ".tmp")

    replace_spy = MagicMock(wraps=embeddings_mod.os.replace)
    monkeypatch.setattr(embeddings_mod.os, "replace", replace_spy)

    rebuild_vector_index(hybrid_wiki, force=True)

    assert replace_spy.call_count == 1, (
        f"os.replace must fire exactly once; got {replace_spy.call_count}. "
        f"Revert to direct in-place write would fire 0 calls."
    )
    # Call args: (tmp_path_str, vec_path_str) per the production contract.
    args = replace_spy.call_args.args
    assert args == (str(tmp_path), str(vec_path)), f"os.replace called with wrong paths: {args}"


def test_crash_during_build_leaves_no_tmp_and_preserves_production(hybrid_wiki, monkeypatch):
    """AC8 — a mid-build exception unlinks the tmp and preserves the existing
    production vec_path (or leaves it absent if it never existed).

    Divergent-fails on AC8 revert (no try/except cleanup): stale tmp persists.
    """
    vec_path = _vec_db_path(hybrid_wiki)
    tmp_path = vec_path.parent / (vec_path.name + ".tmp")

    # Pre-seed production DB with distinct bytes so we can assert it's unchanged.
    vec_path.parent.mkdir(parents=True, exist_ok=True)
    vec_path.write_bytes(b"PRE-EXISTING PRODUCTION DB BYTES")
    pre_bytes = vec_path.read_bytes()

    # Force VectorIndex.build to raise on first call (simulates mid-build crash).
    def _raise(*args, **kwargs):
        # Touch the tmp file first so the crash leaves a real on-disk artifact
        # (mirrors real sqlite3.connect opening the tmp before the insert fails).
        kwargs.get("db_path", Path("")).write_bytes(b"PARTIAL TMP BYTES")
        raise RuntimeError("simulated mid-build crash")

    monkeypatch.setattr(VectorIndex, "build", _raise)

    with pytest.raises(RuntimeError, match="simulated mid-build crash"):
        rebuild_vector_index(hybrid_wiki, force=True)

    # Production DB unchanged.
    assert vec_path.exists()
    assert vec_path.read_bytes() == pre_bytes, (
        "Production vec_path must be untouched after mid-build crash"
    )
    # Tmp cleaned up by the except/finally.
    assert not tmp_path.exists(), (
        "Partial tmp must be unlinked after mid-build crash (AC8 clean-slate)"
    )


def test_build_signature_is_keyword_only(hybrid_wiki):
    """AC7 — ``VectorIndex.build`` ``db_path`` kwarg is KEYWORD-ONLY.

    Prevents future callers from accidentally passing a positional arg that
    gets interpreted as ``db_path`` (typo → wrong DB file replaced).
    """
    sig = inspect.signature(VectorIndex.build)
    param = sig.parameters["db_path"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
        f"db_path must be KEYWORD_ONLY; got {param.kind}"
    )
    assert param.default is None
    # Calling with positional db_path must raise TypeError.
    idx = VectorIndex(hybrid_wiki / ".data" / "vector_index.db")
    with pytest.raises(TypeError):
        # Passing Path(".tmp") positionally is forbidden by KEYWORD_ONLY.
        idx.build([], Path(".tmp"))  # type: ignore[misc]


def test_build_respects_db_path_override(tmp_path):
    """AC7 — explicit ``db_path=`` directs the build target WITHOUT touching
    the instance's ``self.db_path``. ``self._stored_dim`` is NOT mutated when
    building to an override path (design CONDITION 11 rationale)."""
    own_path = tmp_path / "own.db"
    override_path = tmp_path / "override.db"
    idx = VectorIndex(own_path)
    # Pre-build state.
    assert idx._stored_dim is None
    # Build EMPTY with override; instance state stays None (no mutation).
    idx.build([], db_path=override_path)
    assert override_path.exists()
    assert not own_path.exists(), "own path must not be touched when db_path overrides"
    assert idx._stored_dim is None, (
        "_stored_dim must not be mutated when building to an override path"
    )


def test_cache_entry_closed_and_popped_before_replace(hybrid_wiki, monkeypatch):
    """CONDITION 2 — cached ``VectorIndex._conn`` is closed AND popped from
    ``_index_cache`` BEFORE ``os.replace`` fires.

    On Windows this is the difference between a clean rebuild and a
    ``PermissionError [WinError 5]``. On POSIX it enforces consistent
    ordering so tests exercise the same code path cross-platform.
    """
    vec_path = _vec_db_path(hybrid_wiki)

    # Pre-populate _index_cache with a VectorIndex whose _conn is a mock.
    idx = VectorIndex(vec_path)
    mock_conn = MagicMock(spec=sqlite3.Connection)
    idx._conn = mock_conn
    embeddings_mod._index_cache[str(vec_path)] = idx

    # Spy on os.replace — verify cache pop + conn.close happened BEFORE it.
    # Capture real os.replace BEFORE monkeypatching to avoid recursion.
    real_replace = embeddings_mod.os.replace
    ordering_checks = []

    def _spy_replace(src, dst):
        ordering_checks.append(("replace", src, dst))
        real_replace(src, dst)

    def _spy_close():
        ordering_checks.append(("close",))

    mock_conn.close = _spy_close
    monkeypatch.setattr(embeddings_mod.os, "replace", _spy_replace)

    rebuild_vector_index(hybrid_wiki, force=True)

    # Assert close appeared before replace in the ordering log.
    close_idx = next(i for i, c in enumerate(ordering_checks) if c[0] == "close")
    replace_idx = next(i for i, c in enumerate(ordering_checks) if c[0] == "replace")
    assert close_idx < replace_idx, (
        f"_conn.close must run BEFORE os.replace; got ordering {ordering_checks}"
    )
    # Cache entry popped (no longer contains the instance).
    assert str(vec_path) not in embeddings_mod._index_cache


def test_empty_pages_branch_uses_tmp_then_replace(tmp_path, monkeypatch):
    """CONDITION 5 — the empty-wiki path also goes through tmp-then-replace."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (tmp_path / ".data").mkdir()
    # Do NOT seed any pages; load_all_pages returns [].
    monkeypatch.setattr(embeddings_mod, "_hybrid_available", True)
    embeddings_mod._index_cache.clear()

    vec_path = _vec_db_path(wiki_dir)
    tmp_path_db = vec_path.parent / (vec_path.name + ".tmp")

    replace_spy = MagicMock(wraps=embeddings_mod.os.replace)
    monkeypatch.setattr(embeddings_mod.os, "replace", replace_spy)

    result = rebuild_vector_index(wiki_dir, force=True)
    assert result is True
    assert replace_spy.call_count == 1, (
        "Empty-pages branch must also call os.replace(tmp, vec) exactly once"
    )
    assert replace_spy.call_args.args == (str(tmp_path_db), str(vec_path))
    assert vec_path.exists()
    assert not tmp_path_db.exists()
