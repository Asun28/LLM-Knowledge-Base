"""Cycle 67 AC05 — sqlite_vec.load() error sanitization at the build() call site.

Phase 6 cross-LLM cycle-64 LOW: `sqlite_vec.load(conn)` raises
`sqlite3.OperationalError` whose message embeds the absolute filesystem
path of the .so/.dll that failed to load. The path can leak via MCP
error responses (T15 information disclosure).

Cycle 65 AC14 already shipped sanitization at the `_connect()` call site
(`embeddings.py:583-588`). Cycle 67 AC05 closes the SECOND call site
inside `build()` (line 665) with the same pattern.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """A per-test sqlite db path that won't collide with other tests."""
    return tmp_path / "vec_index_AC05.db"


def test_t05a_build_sanitizes_operational_error(
    tmp_db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T05-A: VectorIndex.build() with monkey-patched failing sqlite_vec.load
    raises RuntimeError with sanitized message; `.so`/`.dll` path is NOT
    leaked into the user-facing exception string.
    """
    import sqlite_vec

    LEAKY_PATH = "C:\\Users\\Admin\\AppData\\Local\\sqlite_vec_module.dll"

    def _failing_load(_conn):
        raise sqlite3.OperationalError(f"error loading {LEAKY_PATH}")

    monkeypatch.setattr(sqlite_vec, "load", _failing_load)

    from kb.query.embeddings import VectorIndex  # noqa: PLC0415

    idx = VectorIndex(db_path=tmp_db_path)
    entries = [("page_1", [0.1, 0.2, 0.3])]
    with pytest.raises(RuntimeError) as exc_info:
        idx.build(entries)

    msg = str(exc_info.value)
    assert "sqlite-vec extension failed to load" in msg, (
        f"AC05 T05-A: expected sanitized message; got: {msg!r}"
    )
    assert "AppData" not in msg, (
        f"AC05 T05-A: leaky path 'AppData' fragment leaked into message: {msg!r}"
    )
    assert ".dll" not in msg, f"AC05 T05-A: '.dll' suffix leaked into message: {msg!r}"


def test_t05b_cause_chain_preserved_for_local_logs(
    tmp_db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T05-B: the original OperationalError is preserved in __cause__ so
    local debugging logs can still trace the original error (with the path)
    while the surfaced message stays sanitized.
    """
    import sqlite_vec

    def _failing_load(_conn):
        raise sqlite3.OperationalError("original error with /private/path/lib.so")

    monkeypatch.setattr(sqlite_vec, "load", _failing_load)

    from kb.query.embeddings import VectorIndex  # noqa: PLC0415

    idx = VectorIndex(db_path=tmp_db_path)
    entries = [("page_1", [0.1, 0.2])]
    with pytest.raises(RuntimeError) as exc_info:
        idx.build(entries)

    cause = exc_info.value.__cause__
    assert isinstance(cause, sqlite3.OperationalError), (
        f"AC05 T05-B: __cause__ chain MUST preserve the original OperationalError; "
        f"got: {type(cause).__name__}"
    )
    assert "/private/path/lib.so" in str(cause), (
        f"AC05 T05-B: __cause__ should preserve the original path detail "
        f"for local debugging; got cause str: {str(cause)!r}"
    )


def test_t05c_divergent_fail_naked_error_leaks() -> None:
    """T05-C divergent-fail: pins the divergence direction so a future revert
    produces a meaningful red. Reference sanitized message has no path-like
    fragments; the naked OperationalError WOULD leak the path.
    """
    LEAKY_PATH = "C:\\fake\\path\\leaks.dll"
    naked_error = sqlite3.OperationalError(f"error loading {LEAKY_PATH}")
    naked_msg = str(naked_error)
    assert LEAKY_PATH in naked_msg, (
        "T05-C: sanity check failed — sqlite3.OperationalError(...) does not "
        "preserve message content as expected. Test environment skewed."
    )
    sanitized = "sqlite-vec extension failed to load; reinstall the sqlite-vec wheel"
    assert "fake" not in sanitized
    assert "leaks" not in sanitized


def test_t05d_both_call_sites_have_sanitization() -> None:
    """T05-D: regression test that BOTH call sites have the sanitization
    wrapper — cycle 65 AC14 (_connect at line 583-588) and cycle 67 AC05
    (build at line 665).

    Counts occurrences of the canonical sanitized message in the source. A
    revert of either site drops the count below 2 → RED.
    """
    import inspect

    import kb.query.embeddings as emb_mod

    src = inspect.getsource(emb_mod)
    sanitized_count = src.count(
        "sqlite-vec extension failed to load; reinstall the sqlite-vec wheel"
    )
    assert sanitized_count >= 2, (
        f"AC05 T05-D: expected ≥2 sites with sanitized message (cycle 65 AC14 "
        f"_connect + cycle 67 AC05 build); found {sanitized_count}. "
        f"Either cycle 65 site was reverted or AC05's site is missing."
    )
