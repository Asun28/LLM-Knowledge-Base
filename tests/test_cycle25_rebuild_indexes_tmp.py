"""Cycle 25 AC1/AC2 — `rebuild_indexes` also unlinks `<vec_db>.tmp`.

Regression tests:
- AC1: `rebuild_indexes` cleans the sibling `.tmp` file produced by cycle-24
  `rebuild_vector_index`. Closes the HIGH-Deferred cycle-24 R2 follow-up.
- CONDITION 1 (Q1): a tmp-unlink failure does NOT blank the main
  `result["vector"]["cleared"]` status — compound error reports both.
- CONDITION Q9: `vector_db=` override derives tmp from the effective path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from kb.compile.compiler import rebuild_indexes


def _seed_wiki(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a minimal wiki + data layout. Returns (wiki_dir, vec_path, tmp_path)."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    data_dir = tmp_path / ".data"
    data_dir.mkdir()
    vec_path = data_dir / "vector_index.db"
    tmp_vec_path = data_dir / "vector_index.db.tmp"
    return wiki_dir, vec_path, tmp_vec_path


def test_stale_tmp_unlinked(tmp_path, monkeypatch):
    """AC1 — rebuild_indexes unlinks both <vec_db> and <vec_db>.tmp."""
    # Redirect PROJECT_ROOT so the validator accepts our tmp_path.
    import kb.compile.compiler as compiler_mod
    import kb.config

    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(compiler_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(compiler_mod, "WIKI_DIR", tmp_path / "wiki")
    monkeypatch.setattr(compiler_mod, "HASH_MANIFEST", tmp_path / ".data" / "hashes.json")

    wiki_dir, vec_path, tmp_vec_path = _seed_wiki(tmp_path)
    # Seed both files.
    vec_path.write_bytes(b"MAIN DB BYTES")
    tmp_vec_path.write_bytes(b"STALE TMP BYTES FROM CRASH")
    assert vec_path.exists()
    assert tmp_vec_path.exists()

    result = rebuild_indexes(wiki_dir=wiki_dir)

    assert not vec_path.exists(), "Main vec_path must be unlinked"
    assert not tmp_vec_path.exists(), (
        "AC1: stale .tmp must be unlinked. Pre-cycle-25 revert would leave it."
    )
    assert result["vector"]["cleared"] is True
    assert result["vector"]["error"] is None


def test_no_tmp_file_is_tolerant(tmp_path, monkeypatch):
    """AC1 — when no .tmp sibling exists, the cleanup succeeds silently
    (`missing_ok=True`). The main vec_path unlink still sets `cleared=True`.
    """
    import kb.compile.compiler as compiler_mod
    import kb.config

    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(compiler_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(compiler_mod, "WIKI_DIR", tmp_path / "wiki")
    monkeypatch.setattr(compiler_mod, "HASH_MANIFEST", tmp_path / ".data" / "hashes.json")

    wiki_dir, vec_path, tmp_vec_path = _seed_wiki(tmp_path)
    vec_path.write_bytes(b"MAIN DB BYTES")
    assert not tmp_vec_path.exists()

    result = rebuild_indexes(wiki_dir=wiki_dir)

    assert not vec_path.exists()
    assert result["vector"]["cleared"] is True
    assert result["vector"]["error"] is None


def test_tmp_failure_does_not_blank_vector_cleared(tmp_path, monkeypatch):
    """CONDITION 1 / Q1 — tmp-unlink OSError produces a compound error but
    preserves `cleared=True` (main unlink succeeded).
    """
    import kb.compile.compiler as compiler_mod
    import kb.config

    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(compiler_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(compiler_mod, "WIKI_DIR", tmp_path / "wiki")
    monkeypatch.setattr(compiler_mod, "HASH_MANIFEST", tmp_path / ".data" / "hashes.json")

    wiki_dir, vec_path, tmp_vec_path = _seed_wiki(tmp_path)
    vec_path.write_bytes(b"MAIN DB BYTES")
    tmp_vec_path.write_bytes(b"STALE TMP")

    # Monkeypatch Path.unlink so only the tmp path fails.
    real_unlink = Path.unlink

    def _selective_unlink(self, missing_ok=False):
        if self == tmp_vec_path:
            raise OSError("simulated Windows lock on tmp file")
        return real_unlink(self, missing_ok=missing_ok)

    with patch.object(Path, "unlink", _selective_unlink):
        result = rebuild_indexes(wiki_dir=wiki_dir)

    # Main unlink succeeded → cleared=True preserved.
    assert not vec_path.exists()
    assert result["vector"]["cleared"] is True, (
        "CONDITION 1: tmp failure must NOT blank the main cleared status"
    )
    # Compound error includes "tmp:" marker.
    err = result["vector"]["error"]
    assert err is not None
    assert "tmp:" in err, f"Compound error must name the tmp path failure; got {err!r}"
    # Stale tmp persists because unlink failed — expected.


def test_vector_db_override_also_cleans_tmp(tmp_path, monkeypatch):
    """Q9 — when caller passes `vector_db=` override, the sibling `.tmp` is
    derived from THAT path (not from `_vec_db_path(wiki_dir)`).
    """
    import kb.compile.compiler as compiler_mod
    import kb.config

    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(compiler_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(compiler_mod, "WIKI_DIR", tmp_path / "wiki")
    monkeypatch.setattr(compiler_mod, "HASH_MANIFEST", tmp_path / ".data" / "hashes.json")

    wiki_dir, _, _ = _seed_wiki(tmp_path)
    # Custom vector DB path at tmp_path/custom/my_vec.db (inside project root).
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()
    custom_vec = custom_dir / "my_vec.db"
    custom_tmp = custom_dir / "my_vec.db.tmp"
    custom_vec.write_bytes(b"CUSTOM MAIN")
    custom_tmp.write_bytes(b"CUSTOM TMP")

    result = rebuild_indexes(wiki_dir=wiki_dir, vector_db=custom_vec)

    assert not custom_vec.exists()
    assert not custom_tmp.exists(), (
        "Q9: tmp must be derived from the effective vector_path (override), "
        "not from _vec_db_path(wiki_dir)"
    )
    assert result["vector"]["cleared"] is True
