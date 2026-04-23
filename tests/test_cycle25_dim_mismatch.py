"""Cycle 25 AC3/AC4/AC5 — vector-index dim-mismatch operator guidance.

Regression tests for:
- AC3: `VectorIndex.query` warning message includes `kb rebuild-indexes` and
  the wiki directory (derived via `self.db_path.parent.parent` per Q7).
- AC4: module-level `_dim_mismatches_seen` counter + `get_dim_mismatch_count()`
  getter — increments per mismatch query (NOT once-per-instance).
- CONDITION 11: Q8 approximate-counter contract under concurrent threads.

Closes threat T4 (counter monotonicity) + T5 (path leak accepted as
developer-local log per threat model §3).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from kb.query.embeddings import VectorIndex, get_dim_mismatch_count


def _seed_vector_db(db_path: Path, dim: int = 32) -> None:
    """Create a sqlite-vec DB with a fixed stored dim (no sqlite-vec extension
    needed for this test — we only care about the dim-mismatch branch which
    short-circuits before the MATCH query).

    We bypass the real `VectorIndex.build` (which requires sqlite-vec) by
    directly creating a table whose column type declares the dim — the
    `_read_stored_dim` regex matches `float[{dim}]`.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(f"CREATE TABLE IF NOT EXISTS vec_pages (embedding float[{dim}])")
        conn.commit()
    finally:
        conn.close()


def _make_vector_index(tmp_path: Path, dim: int = 32) -> VectorIndex:
    """Create a VectorIndex pointing at a seeded DB with stored dim."""
    # Mirror the _vec_db_path layout: <wiki_dir>.parent/.data/vector_index.db
    # so that db_path.parent.parent resolves to the wiki dir (Q7 contract).
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(exist_ok=True)
    data_dir = tmp_path / ".data"
    data_dir.mkdir(exist_ok=True)
    db_path = data_dir / "vector_index.db"
    _seed_vector_db(db_path, dim=dim)
    idx = VectorIndex(db_path)
    # Pre-populate `_stored_dim` so `_ensure_conn` isn't needed (sqlite-vec
    # loading is not available in this test env).
    idx._stored_dim = dim
    # Pre-populate `_conn` so `_ensure_conn()` returns it without trying to
    # load sqlite-vec (which may not be available).
    idx._conn = sqlite3.connect(str(db_path))
    return idx


def test_warning_message_includes_remediation_command(tmp_path, caplog):
    """AC3 — warning contains 'kb rebuild-indexes --wiki-dir <path>'."""
    idx = _make_vector_index(tmp_path, dim=32)

    with caplog.at_level(logging.WARNING, logger="kb.query.embeddings"):
        # Query with mismatched dim (64 vs stored 32).
        result = idx.query([0.1] * 64, limit=5)

    assert result == [], "Mismatch returns empty list"
    # Find the warning record.
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_records) >= 1, "At least one warning emitted"
    msg = warning_records[-1].getMessage()
    assert "kb rebuild-indexes" in msg, (
        f"AC3 warning must include 'kb rebuild-indexes' command; got {msg!r}"
    )
    assert "--wiki-dir" in msg, "AC3 warning must include --wiki-dir flag"


def test_warning_uses_db_path_parent_parent_for_wiki_dir(tmp_path, caplog):
    """Q7 — wiki_dir substitution uses `db_path.parent.parent`.

    The DB is at `<tmp>/.data/vector_index.db`; the wiki dir hint must
    resolve to `<tmp>` (not `<tmp>/.data` which is `db_path.parent`).
    """
    idx = _make_vector_index(tmp_path, dim=32)
    expected_wiki_hint = str(idx.db_path.parent.parent)

    with caplog.at_level(logging.WARNING, logger="kb.query.embeddings"):
        idx.query([0.1] * 64, limit=5)

    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    matching = [m for m in msgs if expected_wiki_hint in m]
    assert matching, (
        f"Warning must contain wiki dir hint '{expected_wiki_hint}'; got messages: {msgs!r}"
    )
    # Anti-assertion: the .db file path alone must NOT be the wiki_dir hint
    # substituted at --wiki-dir (would mean Q7 was reverted).
    db_path_str = str(idx.db_path)
    for m in matching:
        # Extract the --wiki-dir argument and check it's not the db path.
        idx_pos = m.index("--wiki-dir ")
        after = m[idx_pos + len("--wiki-dir ") :]
        # The next token is the wiki dir hint (quoted argument may appear).
        token = after.split("'", 1)[0].strip()
        assert token != db_path_str, (
            f"--wiki-dir must be a directory, not the .db file path {db_path_str}"
        )


def test_counter_increments_per_query(tmp_path, caplog):
    """AC4 + CONDITION 3 — counter increments PER QUERY, not once-per-instance."""
    idx = _make_vector_index(tmp_path, dim=32)
    baseline = get_dim_mismatch_count()

    with caplog.at_level(logging.WARNING, logger="kb.query.embeddings"):
        for _ in range(3):
            idx.query([0.1] * 64, limit=5)

    assert get_dim_mismatch_count() - baseline == 3, (
        "Counter must increment once per query (3 queries → 3 increments); "
        "once-per-instance revert would show delta=1"
    )

    # Re-instantiate with a fresh VectorIndex — _dim_warned reset but counter
    # keeps counting (per AC4 contract: process-level, not instance-level).
    idx2 = _make_vector_index(tmp_path, dim=32)
    with caplog.at_level(logging.WARNING, logger="kb.query.embeddings"):
        for _ in range(2):
            idx2.query([0.1] * 64, limit=5)
    assert get_dim_mismatch_count() - baseline == 5, (
        "Counter must keep incrementing across instances (5 total increments)"
    )


def test_dim_warned_stays_once_per_instance(tmp_path, caplog):
    """AC3 — `_dim_warned` sticky flag still emits only ONE warning per
    VectorIndex instance, independent of counter increments.
    """
    idx = _make_vector_index(tmp_path, dim=32)

    with caplog.at_level(logging.WARNING, logger="kb.query.embeddings"):
        for _ in range(5):
            idx.query([0.1] * 64, limit=5)

    # Count WARNING records for THIS instance's logger.
    warning_records = [
        r for r in caplog.records if r.levelno == logging.WARNING and "kb rebuild" in r.getMessage()
    ]
    assert len(warning_records) == 1, (
        f"Expected 1 warning per VectorIndex instance (sticky _dim_warned); "
        f"got {len(warning_records)}"
    )


def test_counter_approximate_under_concurrency(tmp_path, caplog):
    """CONDITION 11 — Q8 accepts approximate counter under thread concurrency.

    GIL makes `+= 1` mostly-atomic but not bytecode-atomic, so a tiny skew
    (typically <1%) is tolerated. The test asserts the counter is within a
    generous 5% of the expected value — catches a broken counter (lock
    around the wrong variable, missing global declaration) but tolerates
    the accepted race window.
    """
    idx = _make_vector_index(tmp_path, dim=32)
    # Pre-trip the sticky warn so threads don't all serialize on logger.
    with caplog.at_level(logging.WARNING, logger="kb.query.embeddings"):
        idx.query([0.1] * 64, limit=5)
    baseline = get_dim_mismatch_count()

    n_threads = 10
    n_per_thread = 50
    expected = n_threads * n_per_thread

    def _worker():
        for _ in range(n_per_thread):
            idx.query([0.1] * 64, limit=5)

    threads = [threading.Thread(target=_worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    observed = get_dim_mismatch_count() - baseline
    # Tolerate ≤5% loss under concurrency per Q8.
    lower_bound = int(expected * 0.95)
    assert observed >= lower_bound, (
        f"Counter under-counted significantly under concurrency: "
        f"observed={observed}, expected={expected}, min={lower_bound}. "
        f"Q8 accepts approximate counts but not losses >5%."
    )
    assert observed <= expected, f"Counter over-counted: observed={observed} > expected={expected}"
