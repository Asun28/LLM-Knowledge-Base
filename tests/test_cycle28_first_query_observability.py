"""Cycle 28 AC1-AC5 — first-query observability completion.

Pins the new `_ensure_conn` sqlite-vec extension-load latency instrumentation
(AC1 INFO + AC2 WARNING + AC3 counter in `embeddings.py`) and the
`BM25Index.__init__` corpus-indexing latency instrumentation (AC4 INFO +
AC5 counter in `bm25.py`). Closes HIGH-Deferred sub-item (b), cycle-26 Q16
follow-up.

Eight tests per CONDITION 3 (design gate Q10 / R2 finding / cycle-26 test-7
precedent):

1. test_sqlite_vec_load_emits_info_on_success
2. test_sqlite_vec_load_emits_warning_above_threshold
3. test_sqlite_vec_load_no_warning_below_threshold
4. test_sqlite_vec_load_count_increments_exactly_once
5. test_sqlite_vec_load_count_stable_on_fast_path
6. test_sqlite_vec_load_no_info_on_failure_path  (C3 mandate — revert-divergent)
7. test_bm25_build_emits_info_with_n_docs
8. test_bm25_build_count_monotonic_across_instances

**Monkeypatch discipline (C7):** tests monkey-patch `sqlite_vec.load` (the
extension loader) directly — NOT `time.perf_counter`. Elapsed is measured
against real wall clock via a stub that `time.sleep()`s to cross the 0.3s
WARN threshold. Zero raw `time.perf_counter = ...` assignments appear in
this module (grep-verified by C7).

**Reload-defense (cycle-20 L1 / T8):** counter reads ALWAYS pair with a
preceding baseline snapshot (monotonic-delta, not absolute-equality). This
pattern survives `importlib.reload(kb.query.embeddings)` cascades in sibling
tests because a reload resets the counter to 0 but monotonic-delta only
requires the post-state to be `>= baseline + N`.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pytest

from kb.query import bm25 as bm25_mod
from kb.query import embeddings as embeddings_mod
from kb.query.bm25 import BM25Index
from kb.query.embeddings import VectorIndex

# --------------------------- helpers ---------------------------


def _build_minimal_vec_db(tmp_path: Path) -> Path:
    """Create a real sqlite-vec-backed DB via `VectorIndex.build()`.

    Cycle-28 tests need a DB that `_ensure_conn` can successfully open +
    `sqlite_vec.load`. Using `VectorIndex.build()` with a trivial 4-dim
    embedding produces a schema-valid `vec_pages` virtual table.
    """
    db_path = tmp_path / "vector.db"
    builder = VectorIndex(db_path)
    builder.build([("seed", [0.1, 0.2, 0.3, 0.4])])
    return db_path


def _skip_if_no_hybrid():
    """Skip sqlite-vec tests when the extension is unavailable in this venv."""
    if not embeddings_mod._hybrid_available:
        pytest.skip("sqlite-vec + model2vec not installed; hybrid path unavailable")


# --------------------------- AC1-AC3 sqlite-vec tests ---------------------------


def test_sqlite_vec_load_emits_info_on_success(tmp_path, caplog):
    """AC1 — successful extension load emits one INFO record with elapsed + db path."""
    _skip_if_no_hybrid()
    db_path = _build_minimal_vec_db(tmp_path)
    fresh_idx = VectorIndex(db_path)

    caplog.set_level(logging.INFO, logger="kb.query.embeddings")
    conn = fresh_idx._ensure_conn()

    assert conn is not None, "Fresh VectorIndex on valid DB should return a conn"
    info_records = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO and "sqlite-vec extension loaded in" in r.getMessage()
    ]
    assert info_records, (
        "Expected exactly one INFO 'sqlite-vec extension loaded in' record; "
        f"got {[r.getMessage() for r in caplog.records]!r}"
    )
    # The db path must appear in the message tail.
    msg = info_records[0].getMessage()
    assert str(db_path) in msg, f"Expected db path in log; got {msg!r}"


def test_sqlite_vec_load_emits_warning_above_threshold(tmp_path, caplog, monkeypatch):
    """AC2 — elapsed >= 0.3s threshold emits additional WARNING.

    Monkeypatches `sqlite_vec.load` with a slow stub so real wall-clock
    elapsed exceeds `SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS = 0.3`. NO
    `time.perf_counter` patching (C7 — zero raw assignments).
    """
    _skip_if_no_hybrid()
    db_path = _build_minimal_vec_db(tmp_path)
    fresh_idx = VectorIndex(db_path)

    import sqlite_vec

    original_load = sqlite_vec.load

    def _slow_load(conn):
        time.sleep(0.35)  # above 0.3s threshold
        # Call original so the extension still actually loads (test doesn't query after).
        original_load(conn)

    monkeypatch.setattr(sqlite_vec, "load", _slow_load)

    caplog.set_level(logging.INFO, logger="kb.query.embeddings")
    conn = fresh_idx._ensure_conn()

    assert conn is not None
    warning_records = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "consider warm-loading" in r.getMessage()
    ]
    assert warning_records, (
        "Expected WARNING 'consider warm-loading' record for 0.35s > 0.3s threshold; "
        f"got {[r.getMessage() for r in caplog.records]!r}"
    )


def test_sqlite_vec_load_no_warning_below_threshold(tmp_path, caplog):
    """AC2 — real fast load (<< 0.3s) emits INFO only, no WARNING."""
    _skip_if_no_hybrid()
    db_path = _build_minimal_vec_db(tmp_path)
    fresh_idx = VectorIndex(db_path)

    caplog.set_level(logging.INFO, logger="kb.query.embeddings")
    conn = fresh_idx._ensure_conn()

    assert conn is not None
    info_records = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO and "sqlite-vec extension loaded in" in r.getMessage()
    ]
    warning_records = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "consider warm-loading" in r.getMessage()
    ]
    assert info_records, "Expected INFO on sub-threshold load"
    assert not warning_records, (
        "Expected NO WARNING on sub-threshold load; "
        f"got {[r.getMessage() for r in caplog.records]!r}"
    )


def test_sqlite_vec_load_count_increments_exactly_once(tmp_path):
    """AC3 — counter +1 exactly after a successful `_ensure_conn` call."""
    _skip_if_no_hybrid()
    db_path = _build_minimal_vec_db(tmp_path)
    fresh_idx = VectorIndex(db_path)

    baseline = embeddings_mod.get_sqlite_vec_load_count()
    conn = fresh_idx._ensure_conn()
    assert conn is not None
    delta = embeddings_mod.get_sqlite_vec_load_count() - baseline
    assert delta == 1, f"Expected counter +1 after first load; got delta={delta}"


def test_sqlite_vec_load_count_stable_on_fast_path(tmp_path):
    """AC3 — second `_ensure_conn` on the same instance hits `self._conn` cache; counter stable."""
    _skip_if_no_hybrid()
    db_path = _build_minimal_vec_db(tmp_path)
    fresh_idx = VectorIndex(db_path)

    conn_a = fresh_idx._ensure_conn()
    assert conn_a is not None

    baseline_after_first = embeddings_mod.get_sqlite_vec_load_count()
    conn_b = fresh_idx._ensure_conn()
    assert conn_b is conn_a, "Cached conn must be returned on second call"
    delta = embeddings_mod.get_sqlite_vec_load_count() - baseline_after_first
    assert delta == 0, f"Expected counter stable on fast-path; got delta={delta}"


def test_sqlite_vec_load_no_info_on_failure_path(tmp_path, caplog, monkeypatch):
    """C3 / Q10 — failure-path divergence: no INFO fires, counter stable, `_disabled=True`.

    Revert-failing (cycle-24 L4): reverting the instrumentation to a
    `try/finally:` wrap would emit INFO even on the failure path — this
    test flips from pass to fail. Also detects accidental counter-increment
    outside the post-success ordering block.
    """
    _skip_if_no_hybrid()
    db_path = _build_minimal_vec_db(tmp_path)
    fresh_idx = VectorIndex(db_path)

    import sqlite_vec

    def _raising_load(conn):
        raise RuntimeError("simulated sqlite-vec load failure")

    monkeypatch.setattr(sqlite_vec, "load", _raising_load)

    caplog.set_level(logging.INFO, logger="kb.query.embeddings")
    baseline = embeddings_mod.get_sqlite_vec_load_count()

    conn = fresh_idx._ensure_conn()

    assert conn is None, "Failure path must return None"
    assert fresh_idx._disabled is True, "Failure path must set _disabled=True"
    info_records = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO and "sqlite-vec extension loaded in" in r.getMessage()
    ]
    assert not info_records, (
        "C3 violation: INFO 'sqlite-vec extension loaded in' fired on failure path. "
        f"Records: {[r.getMessage() for r in caplog.records]!r}"
    )
    # Existing failure WARNING must still fire (cycle-3 H7 precedent preserved).
    failure_warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "sqlite_vec extension load failed" in r.getMessage()
    ]
    assert failure_warnings, (
        "Existing failure WARNING missing — cycle-3 contract regression. "
        f"Records: {[r.getMessage() for r in caplog.records]!r}"
    )
    delta = embeddings_mod.get_sqlite_vec_load_count() - baseline
    assert delta == 0, f"C3 violation: counter advanced by {delta} on failure path"


# --------------------------- AC4-AC5 BM25 tests ---------------------------


def test_bm25_build_emits_info_with_n_docs(caplog):
    """AC4 — `BM25Index.__init__` emits one INFO record with elapsed + n_docs.

    Sub-assertion for empty-corpus edge case (R2 finding 6 / Q10 empty-corpus
    coverage): `BM25Index([])` still emits INFO with n_docs=0.
    """
    caplog.set_level(logging.INFO, logger="kb.query.bm25")
    BM25Index([["foo", "bar"], ["baz"]])

    nonempty_records = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO
        and "BM25 index built in" in r.getMessage()
        and "n_docs=2" in r.getMessage()
    ]
    assert nonempty_records, (
        "Expected INFO 'BM25 index built in ... n_docs=2' for 2-doc corpus; "
        f"got {[r.getMessage() for r in caplog.records]!r}"
    )

    # Empty corpus sub-assertion.
    caplog.clear()
    BM25Index([])
    empty_records = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO
        and "BM25 index built in" in r.getMessage()
        and "n_docs=0" in r.getMessage()
    ]
    assert empty_records, (
        "Expected INFO 'BM25 index built in ... n_docs=0' for empty corpus; "
        f"got {[r.getMessage() for r in caplog.records]!r}"
    )


def test_bm25_build_count_monotonic_across_instances():
    """AC5 — counter +3 exactly after 3 `BM25Index()` constructor calls.

    Pins Q11 semantics: "constructor executions, NOT distinct cache
    insertions" — both wiki (`engine.py:110`) and raw (`engine.py:794`) call
    sites contribute to the same aggregate counter. The test exercises three
    separate constructor calls; cache reuse is out of scope for this counter.
    """
    baseline = bm25_mod.get_bm25_build_count()

    BM25Index([["a", "b"]])
    BM25Index([["c", "d"], ["e", "f"]])
    BM25Index([])  # empty counts too

    delta = bm25_mod.get_bm25_build_count() - baseline
    assert delta == 3, f"Expected counter +3 after 3 constructor calls; got delta={delta}"
