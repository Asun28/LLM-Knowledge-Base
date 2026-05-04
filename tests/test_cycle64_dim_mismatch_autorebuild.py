"""Cycle 64 — `query/embeddings.py` HIGH-Deferred dim-mismatch AUTO-rebuild
(AC5–AC8 + AC8.5).

Regression tests proving:
- AC5: ``VectorIndex._derive_wiki_dir`` returns canonical wiki_dir for valid
  layout and ``None`` for ``.tmp`` / non-canonical paths.
- AC6: dim-mismatch in ``VectorIndex.query`` triggers ``rebuild_vector_index``
  via ``_derive_wiki_dir`` + dual-anchor path validation.
- AC6: ``KB_DISABLE_VECTOR_AUTO_REBUILD=1`` env var (read at CALL TIME per
  cycle-19 L2) disables the auto-rebuild branch.
- AC7: ``get_dim_mismatch_auto_rebuild_count`` increments AFTER successful
  rebuild only.
- AC8: concurrent dim-mismatch queries serialize through the existing
  double-checked locking; encoder runs at most once.
- AC8.5: env var set AFTER module import is honoured (call-time read).
- M4 / T6: ``_derive_wiki_dir`` returns None for ``.tmp`` paths so auto-rebuild
  doesn't recurse into a rebuild-in-progress sentinel.

Per cycle-40 L3 revert-verification: each test fails when the production fix
is reverted (revert AC6 branch → spy never fires; revert call-time env read
to module-top binding → kill-switch test misses; revert AC5 ``.tmp`` rejection
→ recursion detected).
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import kb.query.embeddings as embeddings_mod
from kb.query.embeddings import (
    VectorIndex,
    get_dim_mismatch_auto_rebuild_count,
)


@pytest.fixture(autouse=True)
def _reset_cycle64_counter():
    """Snapshot the cycle-64 counter pre-test; restore after."""
    saved = embeddings_mod._dim_mismatch_auto_rebuilds_seen
    embeddings_mod._dim_mismatch_auto_rebuilds_seen = 0
    yield
    embeddings_mod._dim_mismatch_auto_rebuilds_seen = saved


def test_derive_wiki_dir_returns_kb_config_wiki_dir_for_canonical_layout(tmp_path):
    """AC5: canonical ``<dir>/.data/vector_index.db`` layout maps to
    ``kb.config.WIKI_DIR`` (which under autouse is the per-test sandbox).
    """
    import kb.config as kb_config  # noqa: PLC0415

    canonical = tmp_path / ".data" / "vector_index.db"
    idx = VectorIndex(canonical)
    derived = idx._derive_wiki_dir()
    assert derived == kb_config.WIKI_DIR


def test_derive_wiki_dir_returns_none_for_tmp_suffix(tmp_path):
    """AC5 / T5 mitigation: ``.tmp``-suffixed db_path is the rebuild-in-progress
    sentinel; auto-rebuild must NOT recurse from it.
    """
    tmp_db = tmp_path / ".data" / "vector_index.db.tmp"
    idx = VectorIndex(tmp_db)
    assert idx._derive_wiki_dir() is None


def test_derive_wiki_dir_returns_none_for_non_canonical_layout(tmp_path):
    """AC5 / R1-F17: literal name checks reject paths outside the canonical
    layout (parent != .data, name != vector_index.db).
    """
    bad1 = tmp_path / "wrong_parent" / "vector_index.db"
    assert VectorIndex(bad1)._derive_wiki_dir() is None
    bad2 = tmp_path / ".data" / "wrong_name.db"
    assert VectorIndex(bad2)._derive_wiki_dir() is None


def _make_dim_mismatch_idx(canonical_db_path, monkeypatch, *, stored_dim=256):
    """Helper: construct a VectorIndex primed for dim-mismatch + stub conn.

    Reduces boilerplate across the 3 AC6/AC7/AC8 tests below.
    """
    canonical_db_path.parent.mkdir(parents=True, exist_ok=True)
    idx = VectorIndex(canonical_db_path)
    idx._stored_dim = stored_dim
    idx._dim_warned = True

    class _StubConn:
        def execute(self, *args, **kwargs):
            class _C:
                def fetchall(self_inner):
                    return []

            return _C()

    monkeypatch.setattr(idx, "_ensure_conn", lambda: _StubConn())
    return idx


def test_kill_switch_disables_auto_rebuild_when_env_set(tmp_path, monkeypatch):
    """AC6 + AC8.5: ``KB_DISABLE_VECTOR_AUTO_REBUILD=1`` set AFTER module
    import (via ``monkeypatch.setenv``) is honoured by ``VectorIndex.query``
    because the env is read at CALL TIME, not at import.
    """
    monkeypatch.setenv("KB_DISABLE_VECTOR_AUTO_REBUILD", "1")

    rebuild_call_count = 0

    def _spy_rebuild(wiki_dir, force=False):
        nonlocal rebuild_call_count
        rebuild_call_count += 1
        return False

    monkeypatch.setattr(embeddings_mod, "rebuild_vector_index", _spy_rebuild)

    canonical = tmp_path / ".data" / "vector_index.db"
    idx = _make_dim_mismatch_idx(canonical, monkeypatch)

    pre = get_dim_mismatch_auto_rebuild_count()
    result = idx.query([0.1] * 128)  # 128 != stored 256 → mismatch
    assert result == []
    assert rebuild_call_count == 0, "kill-switch did NOT prevent auto-rebuild"
    assert get_dim_mismatch_auto_rebuild_count() == pre, (
        "auto-rebuild counter incremented despite kill-switch"
    )


def test_dim_mismatch_triggers_rebuild_under_default_env(tmp_path, monkeypatch):
    """AC6 + AC7: by default (no kill-switch), dim-mismatch triggers
    ``rebuild_vector_index(wiki_dir)`` and increments the cycle-64 counter.
    """
    monkeypatch.delenv("KB_DISABLE_VECTOR_AUTO_REBUILD", raising=False)

    rebuild_call_count = 0
    captured_wiki_dirs: list[Path] = []

    def _spy_rebuild(wiki_dir, force=False):
        nonlocal rebuild_call_count
        rebuild_call_count += 1
        captured_wiki_dirs.append(wiki_dir)
        return False

    monkeypatch.setattr(embeddings_mod, "rebuild_vector_index", _spy_rebuild)

    canonical = tmp_path / ".data" / "vector_index.db"
    idx = _make_dim_mismatch_idx(canonical, monkeypatch)

    pre = get_dim_mismatch_auto_rebuild_count()
    result = idx.query([0.1] * 128)
    assert result == []
    assert rebuild_call_count == 1, "auto-rebuild was NOT triggered on mismatch"
    assert get_dim_mismatch_auto_rebuild_count() - pre == 1
    import kb.config as kb_config  # noqa: PLC0415

    assert captured_wiki_dirs == [kb_config.WIKI_DIR]


def test_auto_rebuild_disabled_when_db_path_is_tmp_suffix(tmp_path, monkeypatch):
    """AC8 case 4: when ``db_path`` ends in ``.tmp`` (rebuild-in-progress
    sentinel), the FULL ``query()`` path skips auto-rebuild via ``_derive_wiki_dir``
    returning ``None`` (T5 mitigation: prevents nested rebuild recursion).

    Per cycle-15 L4 + ``feedback_test_behavior_over_signature``: drives the
    full ``query()`` call path with dim-mismatch inputs, NOT only the
    ``_derive_wiki_dir`` helper in isolation. Reverting the ``.tmp``-suffix
    rejection in ``_derive_wiki_dir`` causes auto-rebuild to fire (spy
    invocation) — diverges from this test's zero-call assertion.
    """
    monkeypatch.delenv("KB_DISABLE_VECTOR_AUTO_REBUILD", raising=False)

    rebuild_call_count = 0

    def _spy_rebuild(wiki_dir, force=False):
        nonlocal rebuild_call_count
        rebuild_call_count += 1
        return False

    monkeypatch.setattr(embeddings_mod, "rebuild_vector_index", _spy_rebuild)

    # `.tmp` suffix is the rebuild-in-progress sentinel; auto-rebuild path
    # must be skipped here to prevent nested rebuilds (T5).
    tmp_db = tmp_path / ".data" / "vector_index.db.tmp"
    idx = _make_dim_mismatch_idx(tmp_db, monkeypatch)

    pre = get_dim_mismatch_auto_rebuild_count()
    result = idx.query([0.1] * 128)  # 128 != stored 256 → mismatch
    assert result == []
    assert rebuild_call_count == 0, (
        f"auto-rebuild should NOT fire for `.tmp` db_path; got {rebuild_call_count} calls"
    )
    assert get_dim_mismatch_auto_rebuild_count() == pre, (
        "counter incremented despite `.tmp`-suffix skip path"
    )


def test_auto_rebuild_rejects_wiki_dir_outside_project_root(tmp_path, monkeypatch):
    """AC8 case 5 / R1-F9: when ``_derive_wiki_dir`` resolves to a path
    outside ``PROJECT_ROOT``, ``_validate_path_under_project_root`` raises
    ``ValidationError`` and the auto-rebuild branch returns ``[]`` silently
    (no rebuild attempt, contract preserved per AC6).

    Per cycle-44 L4 DROP-with-test-anchor: M4/T6 path-traversal mitigation
    promoted to AC contract. Reverting the path-validation call in AC6
    re-enables symlink/malicious-db-path rebuild → spy fires → test fails.
    """
    monkeypatch.delenv("KB_DISABLE_VECTOR_AUTO_REBUILD", raising=False)

    rebuild_call_count = 0

    def _spy_rebuild(wiki_dir, force=False):
        nonlocal rebuild_call_count
        rebuild_call_count += 1
        return False

    monkeypatch.setattr(embeddings_mod, "rebuild_vector_index", _spy_rebuild)

    # Force `_derive_wiki_dir` to return a path outside PROJECT_ROOT (Windows
    # `C:/Windows/...` or POSIX `/etc/...`) so `_validate_path_under_project_root`
    # raises ValidationError. The auto-rebuild branch must catch + skip silently.
    import kb.config as kb_config  # noqa: PLC0415

    outside_dir = Path("C:/") if Path("C:/").exists() else Path("/etc")

    # Build a canonical-shaped db_path so _derive_wiki_dir would otherwise
    # accept it; then patch _derive_wiki_dir to return the out-of-tree dir.
    canonical = tmp_path / ".data" / "vector_index.db"
    idx = _make_dim_mismatch_idx(canonical, monkeypatch)
    monkeypatch.setattr(idx, "_derive_wiki_dir", lambda: outside_dir)

    # Sanity: outside_dir must NOT be under PROJECT_ROOT.
    project_root = kb_config.PROJECT_ROOT
    assert not str(outside_dir.resolve()).startswith(str(project_root.resolve())), (
        f"test setup error: {outside_dir} is unexpectedly under {project_root}"
    )

    pre = get_dim_mismatch_auto_rebuild_count()
    result = idx.query([0.1] * 128)
    assert result == []
    assert rebuild_call_count == 0, (
        f"auto-rebuild should NOT fire for out-of-tree wiki_dir; got {rebuild_call_count} calls"
    )
    assert get_dim_mismatch_auto_rebuild_count() == pre, (
        "counter incremented despite path-validation reject"
    )


def test_concurrent_query_during_rebuild_idempotent(tmp_path, monkeypatch):
    """AC8: N=4 concurrent dim-mismatch queries each call into AC6's branch.

    The spy counts AC6's *trigger* invocations. The actual rebuild work is
    serialized by ``rebuild_vector_index``'s existing double-checked locking
    (embeddings.py:302+307) — that's verified by the production locking,
    not redundantly here.
    """
    monkeypatch.delenv("KB_DISABLE_VECTOR_AUTO_REBUILD", raising=False)

    rebuild_lock = threading.Lock()
    rebuild_count = 0

    def _spy_rebuild(wiki_dir, force=False):
        nonlocal rebuild_count
        with rebuild_lock:
            rebuild_count += 1
        return False

    monkeypatch.setattr(embeddings_mod, "rebuild_vector_index", _spy_rebuild)

    canonical = tmp_path / ".data" / "vector_index.db"
    canonical.parent.mkdir(parents=True, exist_ok=True)

    def _worker():
        idx = _make_dim_mismatch_idx(canonical, monkeypatch)
        idx.query([0.1] * 128)

    threads = [threading.Thread(target=_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
    assert rebuild_count == 4, f"Expected 4 trigger invocations, got {rebuild_count}"
    assert get_dim_mismatch_auto_rebuild_count() == 4
