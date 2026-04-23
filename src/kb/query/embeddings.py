"""Embedding wrapper (model2vec) and vector index (sqlite-vec)."""

import logging
import os
import re
import sqlite3
import threading
from pathlib import Path

from kb.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

# H17 fix: module-load-time availability flag.  Both model2vec and sqlite_vec
# must be importable; if either is absent we fall back to BM25-only search and
# emit a single WARNING so the operator knows why hybrid is disabled.
try:
    import model2vec  # noqa: F401
    import sqlite_vec  # noqa: F401

    _hybrid_available = True
except ImportError as e:
    _hybrid_available = False
    logger.warning(
        "Hybrid search disabled — install model2vec + sqlite-vec to enable. Error: %s", e
    )

# Serializes concurrent rebuild_vector_index() calls (double-checked locking).
_rebuild_lock = threading.Lock()

_model = None
_model_lock = threading.Lock()
# Cycle 7 AC3: bound _index_cache at MAX_INDEX_CACHE_SIZE with FIFO eviction
# (insertion-ordered dict — CPython 3.7+). Each production process holds ONE
# wiki path, so 8 keys is ample; per-test cache growth caused the previous
# unbounded-dict footgun where tmp_wiki entries accumulated indefinitely.
MAX_INDEX_CACHE_SIZE = 8
_index_cache: dict[str, "VectorIndex"] = {}
# Cycle 3 H8: serialize concurrent `get_vector_index` lookups. Without this,
# two FastMCP worker threads hitting an uncached `vec_path` both instantiate
# a `VectorIndex` and both write into `_index_cache`; future `__init__`
# side-effects (DB schema validation, file lock) would race. Matches the
# `_model_lock` / `_rebuild_lock` double-checked pattern.
_index_cache_lock = threading.Lock()

# Cycle 25 AC4 — process-level observability counter for dim-mismatch events.
# Incremented on EVERY query that detects a stored-dim vs query-dim mismatch
# (NOT once-per-instance). Q8 decision: approximate under concurrent threads
# (no lock) — adequate for diagnostic observation, not billing-grade telemetry.
# A counter race can undercount by ≤N under N concurrent mismatch-queries,
# well within the diagnostic tolerance.
_dim_mismatches_seen: int = 0

# Cycle 26 AC3 — WARN threshold (seconds) for `_get_model` cold-load latency.
# Module-level constant; env override deferred per requirements non-goals.
VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS: float = 0.3

# Cycle 26 AC4 — process-level observability counter for vector model cold-loads.
# cf. `_dim_mismatches_seen` above — lock-free per cycle-25 Q8. This cold-load
# counter piggybacks on `_model_lock` for EXACT counts because cold-loads happen
# at most once per process under normal operation (the enclosing double-checked
# lock is already held), so the exact-vs-approximate trade-off flips compared
# to cycle-25's query-hot-path counter.
_vector_model_cold_loads_seen: int = 0


def get_dim_mismatch_count() -> int:
    """Return the process-level count of vector-index dim-mismatch events.

    Cycle 25 AC4 — module-level observability counter, incremented inside
    ``VectorIndex.query`` whenever the stored dim differs from the query
    vector's dim. Counter is process-local (resets on restart) and approximate
    under concurrent thread load per the Q8 design-gate decision. Intended for
    diagnostic observation (e.g. "did any mismatches happen since boot?"),
    NOT for billing-grade telemetry.

    The counter is RO: no reset helper is exposed. Tests observe monotonic
    deltas by snapshotting before/after a call sequence.
    """
    return _dim_mismatches_seen


def get_vector_model_cold_load_count() -> int:
    """Return the process-level count of successful vector model cold-loads.

    Cycle 26 AC4. Paired with :func:`get_dim_mismatch_count` (cycle 25) — see
    that function for the observability-counter conventions. Intentional
    asymmetry: this cold-load counter is incremented INSIDE ``_model_lock``
    (exact counts; the lock is already held for the `from_pretrained` call),
    whereas cycle-25's dim-mismatch counter is lock-free (query-hot-path,
    approximate counts adequate per Q8). Future maintainers: do NOT
    "normalise" one to match the other — the rate characteristics differ.
    """
    return _vector_model_cold_loads_seen


def _warm_load_target(vec_path: Path) -> None:
    """Daemon-thread target that wraps ``_get_model()`` for T6 exception visibility.

    Cycle 26 AC1 / Q2 / CONDITION 10 — catches any exception inside the
    warm-load attempt and calls ``logger.exception`` so silent thread
    failures still produce structured log output. Returns normally
    otherwise; the model singleton caches the result for subsequent
    user queries.
    """
    try:
        _get_model()
    except Exception:
        logger.exception("Warm-load thread failed for vec_db=%s", vec_path)


def maybe_warm_load_vector_model(wiki_dir: Path) -> "threading.Thread | None":
    """Optional MCP-startup warm-load of the vector embedding model.

    Cycle 26 AC1. Spawns a daemon thread calling :func:`_get_model` when
    hybrid search is available AND a vector-index DB already exists for
    ``wiki_dir`` AND the model has not already been loaded this process.
    Returns the :class:`threading.Thread` so tests can ``.join(timeout=...)``;
    production callers (``kb.mcp.__init__.main``) ignore the return value.

    Returns ``None`` when any precondition fails (hybrid unavailable,
    ``_vec_db_path(wiki_dir)`` missing, or ``_model`` already set — idempotent
    no-op).

    Single-spawn caveat: this helper does NOT lock against concurrent callers.
    T5 unbounded-spawn acceptance rests on the single-caller production
    invariant (AC2 — exactly one call site in ``kb.mcp.__init__.main``).
    Callers outside tests MUST NOT loop this function; the cycle-26 CI-gate
    grep enforces exactly one production caller.
    """
    if not _hybrid_available:
        return None
    vec_path = _vec_db_path(wiki_dir)
    if not vec_path.exists():
        return None
    if _model is not None:
        return None
    logger.info("Warm-loading vector model in background (vec_db=%s)", vec_path)
    thread = threading.Thread(target=_warm_load_target, args=(vec_path,), daemon=True)
    thread.start()
    return thread


def _reset_model() -> None:
    """Reset cached model and index. Call in test teardown.

    Cycle 3 H8 PR review R1 Sonnet MAJOR: acquire `_index_cache_lock` when
    clearing so a concurrent `get_vector_index` slow-path cannot re-populate
    a stale pre-reset instance between our clear and the caller's next
    lookup. `_model_lock` analogously guards `_model`.
    """
    global _model
    with _model_lock:
        _model = None
    with _index_cache_lock:
        _index_cache.clear()


def _vec_db_path(wiki_dir: Path) -> Path:
    """Return canonical path for the vector index DB, relative to wiki_dir's project root."""
    return wiki_dir.parent / ".data" / "vector_index.db"


def _is_rebuild_needed(wiki_dir: Path) -> bool:
    """Return True if any wiki page is newer than the existing vector index DB.

    Also returns True when the DB does not yet exist.
    """
    vec_path = _vec_db_path(wiki_dir)
    if not vec_path.exists():
        return True
    db_mtime = vec_path.stat().st_mtime
    newest_page = max((p.stat().st_mtime for p in wiki_dir.rglob("*.md")), default=0.0)
    return newest_page > db_mtime


def _evict_vector_index_cache_entry(vec_path: Path) -> None:
    """Pop the cached ``VectorIndex`` for ``vec_path`` AND close its sqlite3
    connection before returning.

    Cycle 24 AC5 (CONDITION 2): on Windows NTFS, ``os.replace(tmp, vec_path)``
    fails with ``PermissionError [WinError 5]`` if any cached ``_conn`` still
    holds a read handle on ``vec_path``. ``_index_cache.pop`` alone removes the
    DICT reference but does NOT guarantee the connection closes (other
    references may pin the instance briefly). Explicit ``.close()`` unpins the
    sqlite3 fd so ``os.replace`` succeeds cross-platform.

    Cycle 24 PR #38 R1 Sonnet MAJOR M1: the ``.close()`` call and the
    ``_conn = None`` rebind happen INSIDE ``_index_cache_lock`` so a concurrent
    query thread that grabbed the instance before the pop cannot race against
    ``_ensure_conn()``'s ``_conn is not None`` check. Hot-path queries already
    re-acquire ``_conn_lock`` inside ``_ensure_conn`` before touching
    ``self._conn``, but the eviction path crossed the lock boundary — a
    concurrent ``query()`` could observe ``_conn`` non-None at the fast-path
    check and then fail inside sqlite on the closed handle. Holding
    ``_index_cache_lock`` across the close serialises the eviction with
    `get_vector_index`'s slow path (the two paths share the same lock), and
    the instance is already out of the cache dict so only pre-evict readers
    can observe it.

    The caller MUST invoke this BEFORE ``os.replace`` per design CONDITION 2.
    """
    with _index_cache_lock:
        popped = _index_cache.pop(str(vec_path), None)
        if popped is not None and popped._conn is not None:
            try:
                popped._conn.close()
            except Exception:
                # sqlite3.Connection.close() is idempotent; a double-close or
                # a connection closed due to earlier extension-load failure
                # is safe to swallow.
                pass
            popped._conn = None


def rebuild_vector_index(wiki_dir: Path, force: bool = False) -> bool:
    """Rebuild the sqlite-vec index from all pages in wiki_dir.

    H17 fix: this is the production entry point that was previously missing,
    leaving Phase 4 "hybrid" search as BM25-only in practice.

    Cycle 24 AC5/AC6/AC8: rebuild now uses a tmp-then-replace flow
    (``<vec_db>.tmp`` built separately then ``os.replace``-swapped into place)
    so a crash mid-build leaves the production DB intact. A stale ``.tmp``
    from a prior crash is unlinked at function entry unconditionally — BEFORE
    any gate or lock — so the next invocation cleans up even if the gates
    skip. On exception during build or replace, the tmp is unlinked and the
    exception re-raised (clean-slate policy).

    Gates:
        1. ``_hybrid_available`` — model2vec + sqlite_vec must be importable.
        2. mtime check (skipped when ``force=True``) — if the DB is newer than
           all wiki pages, no rebuild is performed.
        3. ``_rebuild_lock`` — serializes concurrent in-process callers
           (double-checked). Cross-process rebuilders still race ``os.replace``
           but NTFS kernel-level serialisation makes the outcome idempotent
           since both produce the same content.

    Args:
        wiki_dir: Path to the wiki directory (used to locate pages and DB).
        force: Skip the mtime gate and always rebuild.

    Returns:
        True if the index was (re)built; False if skipped.
    """
    # Cycle 24 AC6 — stale-tmp cleanup runs unconditionally at entry, BEFORE
    # every gate. A crashed prior run's <vec_db>.tmp must not persist
    # indefinitely; even in the "skip this call" path we clean up.
    vec_path = _vec_db_path(wiki_dir)
    tmp_path = vec_path.parent / (vec_path.name + ".tmp")
    try:
        tmp_path.unlink(missing_ok=True)
    except OSError:
        # Best-effort: a stale tmp we cannot unlink will surface later as a
        # sqlite3 error during the actual rebuild. Avoid masking the real issue.
        pass

    if not _hybrid_available:
        return False

    if not force and not _is_rebuild_needed(wiki_dir):
        return False

    with _rebuild_lock:
        # Double-check inside lock — another thread may have rebuilt while we waited.
        if not force and not _is_rebuild_needed(wiki_dir):
            return False

        from kb.utils.pages import load_all_pages

        pages = load_all_pages(wiki_dir=wiki_dir)
        vec_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Cycle 24 AC5 — build to tmp, then atomic-replace. Both branches
            # (empty and populated) route through the same tmp-then-replace
            # flow per design CONDITION 5.
            if not pages:
                VectorIndex(vec_path).build([], db_path=tmp_path)
                entry_count = 0
            else:
                # Cycle 7 AC2: call model.encode() directly (returns numpy 2D
                # array) and pass each row via buffer protocol to
                # VectorIndex.build -> sqlite_vec.serialize_float32. Bypasses
                # the list[list[float]] round-trip previously paid inside
                # embed_texts for the batch path.
                texts = [page.get("content", "") for page in pages]
                model = _get_model()
                embeddings_np = model.encode(texts)
                entries = [(pages[i]["id"], embeddings_np[i]) for i in range(len(pages))]
                VectorIndex(vec_path).build(entries, db_path=tmp_path)
                entry_count = len(entries)

            # Cycle 24 CONDITION 2 — pop+close cached VectorIndex BEFORE
            # os.replace so Windows can release the read handle on vec_path.
            _evict_vector_index_cache_entry(vec_path)

            os.replace(str(tmp_path), str(vec_path))
        except Exception:
            # Cycle 24 AC8 — clean-slate on crash: the tmp DB may be partial
            # or complete-but-unreplaced; either way it is not the production
            # DB and must not persist.
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        logger.info("Vector index rebuilt: %s (%d entries)", vec_path, entry_count)
        return True


def get_vector_index(vec_path: str) -> "VectorIndex":
    """Return a cached VectorIndex keyed by path. Avoids re-instantiation per query.

    Cycle 3 H8: double-checked locking around `_index_cache` — the fast path
    skips the lock when the key is already populated; the slow path serializes
    instantiation so concurrent FastMCP threads observe a single shared
    `VectorIndex`.

    Cycle 7 AC3: bound the cache at ``MAX_INDEX_CACHE_SIZE`` with FIFO eviction
    so long-running processes or heavy test batches don't accumulate stale
    VectorIndex entries. Eviction happens under ``_index_cache_lock`` so the
    pop cannot race a concurrent insert.
    """
    key = str(vec_path)
    cached = _index_cache.get(key)
    if cached is not None:
        return cached
    with _index_cache_lock:
        cached = _index_cache.get(key)
        if cached is None:
            cached = VectorIndex(Path(vec_path))
            _index_cache[key] = cached
            # FIFO eviction when over cap — insertion-ordered dict means
            # next(iter(...)) yields the oldest key.
            while len(_index_cache) > MAX_INDEX_CACHE_SIZE:
                oldest = next(iter(_index_cache))
                _index_cache.pop(oldest, None)
        return cached


def _get_model():
    """Lazy-load model2vec model (thread-safe singleton).

    Cycle 26 AC3 — instrumented with ``time.perf_counter`` around
    ``StaticModel.from_pretrained``. On successful load, emits an INFO log
    with elapsed time, increments the AC4 counter, and on threshold breach
    (``VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS``) emits an additional WARNING
    nudging operators toward :func:`maybe_warm_load_vector_model`. The
    log + increment fire ONLY on the success path (not in ``finally:``) so
    an exception from ``from_pretrained`` leaves ``_model`` as ``None``,
    produces no misleading "cold-loaded" log line, and the next query
    re-attempts naturally.
    """
    global _model, _vector_model_cold_loads_seen
    if _model is None:
        with _model_lock:
            if _model is None:
                import time

                from model2vec import StaticModel

                start = time.perf_counter()
                _model = StaticModel.from_pretrained(EMBEDDING_MODEL, force_download=False)
                elapsed = time.perf_counter() - start
                _vector_model_cold_loads_seen += 1
                logger.info("Vector model cold-loaded in %.2fs", elapsed)
                if elapsed >= VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS:
                    logger.warning(
                        "Vector model cold-load exceeded %.2fs threshold (%.2fs actual). "
                        "Consider warm-load on startup via "
                        "maybe_warm_load_vector_model(wiki_dir).",
                        VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS,
                        elapsed,
                    )
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts using model2vec. Returns list of float lists."""
    if not texts:
        return []
    model = _get_model()
    embeddings = model.encode(texts)
    return [vec.tolist() for vec in embeddings]


class VectorIndex:
    """sqlite-vec backed vector index for wiki page embeddings.

    Cycle 3 H7 + L2: the class now self-validates the embedding dimension on
    both build AND query paths so a caller feeding a zero-length or oversized
    embedding vector is rejected early (L2), and a query whose vector length
    disagrees with the stored table schema returns `[]` with a WARN log (H7)
    instead of silently falling back to BM25-only after a cryptic vec0 error.
    """

    # L2: accept dims roughly matching known embedding models (model2vec
    # potion-base-8M defaults to 256). 4096 is a conservative upper bound
    # covering all production OpenAI/Anthropic/Cohere embedding sizes.
    _MAX_DIM = 4096

    def __init__(self, db_path: Path):
        self.db_path = db_path
        # H7: cache stored dim on first query so we avoid running
        # `PRAGMA table_info` on the hot path. `None` means "not yet probed".
        # `0` means "empty DB / missing table" (query returns []).
        self._stored_dim: int | None = None
        self._dim_warned: bool = False
        # Cycle 6 AC5 — persistent sqlite3 connection. Loaded once via
        # `_ensure_conn()` and reused across every `query()` call. On
        # extension-load failure `_disabled = True`; a single WARNING is
        # logged via `_ext_warned`. Subsequent `query()` calls return `[]`
        # without retrying `sqlite_vec.load`. Connection is left open for
        # the VectorIndex instance's lifetime per OQ4 (single-user local
        # tool; process exit closes the sqlite3 fd — `__del__` is unsafe).
        self._conn: sqlite3.Connection | None = None
        # PR #20 R1 Sonnet M1: per-instance lock so concurrent threads on the
        # SAME VectorIndex instance do not both open a sqlite3 connection
        # and leak one. Mirrors the module-level `_model_lock` /
        # `_rebuild_lock` double-checked pattern.
        self._conn_lock: threading.Lock = threading.Lock()
        self._disabled: bool = False
        self._ext_warned: bool = False

    def _ensure_conn(self) -> sqlite3.Connection | None:
        """Lazy-load sqlite3 connection + sqlite_vec extension.

        Returns the persistent connection, or ``None`` when the index is
        disabled (extension unavailable / DB missing). Never retries after a
        failure: the `_disabled` flag is sticky. Thread-safe via
        `_conn_lock` double-checked locking (PR #20 R1 Sonnet M1 fix).

        **Threading contract** (PR #20 R3 nit): the returned connection is
        opened with ``check_same_thread=False`` and SHARED across all
        ``query()`` callers. Today ``query()`` is purely READ-only (SELECT +
        PRAGMA) so concurrent reads are safe under Python sqlite3's
        serialized threading mode. If a future caller adds writes to the
        shared connection, it MUST serialize them (per-statement
        ``threading.Lock``) or open its own connection — do NOT rely on
        ``_conn_lock``, which only guards first-time initialization.
        """
        # Fast path: lock-free hot-path check (dominant case once connected).
        if self._disabled:
            return None
        if self._conn is not None:
            return self._conn
        if not self.db_path.exists():
            # Not disabled — the DB may be created later by ``build()``.
            # Leave _conn=None so the next query retries only if DB appears.
            return None
        with self._conn_lock:
            # Double-check inside lock — another thread may have won.
            if self._disabled:
                return None
            if self._conn is not None:
                return self._conn
            if not self.db_path.exists():
                return None
            try:
                # PR #20 R2 Codex NEW-ISSUE fix: sqlite3 connections are
                # thread-affine by default. Since this connection is shared
                # across every subsequent ``query()`` call (potentially from
                # multiple FastMCP worker threads), set
                # ``check_same_thread=False``. Python sqlite3 ships in
                # serialized threading mode, so concurrent READ-only queries
                # are safe without external serialization. ``build()`` keeps
                # its own thread-local connection, so the default there is
                # unaffected.
                conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
                conn.enable_load_extension(True)
                import sqlite_vec

                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
            except Exception as e:
                if not self._ext_warned:
                    logger.warning(
                        "sqlite_vec extension load failed — vector search disabled: %s", e
                    )
                    self._ext_warned = True
                self._disabled = True
                try:
                    # Close partial connection if one was opened.
                    if "conn" in locals():
                        conn.close()  # type: ignore[has-type]
                except Exception:
                    pass
                return None
            self._conn = conn
            return conn

    def build(
        self,
        entries: list[tuple[str, list[float]]],
        *,
        db_path: Path | None = None,
    ) -> None:
        """Build index from (page_id, embedding) pairs. Replaces existing index.

        Cycle 3 L2: the dim used in the f-string `CREATE VIRTUAL TABLE ...
        vec0(embedding float[{dim}])` is validated to be a sane positive
        integer. An attacker-controlled or bug-introduced non-int dim would
        otherwise be interpolated verbatim into SQL.

        Cycle 24 AC7 (CONDITION 11): ``db_path`` is KEYWORD-ONLY and overrides
        ``self.db_path`` when not None. ``rebuild_vector_index`` uses the
        override to build into a tmp file for the atomic tmp-then-replace flow.
        When ``db_path`` is None (default), the call targets ``self.db_path``
        and ``self._stored_dim`` is updated. When ``db_path`` is passed
        explicitly, ``self._stored_dim`` is NOT mutated so the instance state
        stays coherent with its self-described DB file.
        """
        target_path = db_path if db_path is not None else self.db_path

        if not entries:
            # Create empty DB and reset dim cache (only when targeting own DB).
            conn = sqlite3.connect(str(target_path))
            conn.close()
            if db_path is None:
                self._stored_dim = 0
            return

        dim = len(entries[0][1])
        if not (isinstance(dim, int) and 1 <= dim <= self._MAX_DIM):
            raise ValueError(f"Invalid embedding dim={dim!r}; expected int in [1, {self._MAX_DIM}]")
        conn = sqlite3.connect(str(target_path))
        try:
            conn.enable_load_extension(True)
            import sqlite_vec

            sqlite_vec.load(conn)
            conn.enable_load_extension(False)

            conn.execute("DROP TABLE IF EXISTS page_ids")
            conn.execute("DROP TABLE IF EXISTS vec_pages")
            conn.execute("CREATE TABLE page_ids (rowid INTEGER PRIMARY KEY, page_id TEXT)")
            conn.execute(f"CREATE VIRTUAL TABLE vec_pages USING vec0(embedding float[{dim}])")

            for i, (page_id, vec) in enumerate(entries):
                rowid = i + 1
                conn.execute("INSERT INTO page_ids VALUES (?, ?)", (rowid, page_id))
                conn.execute(
                    "INSERT INTO vec_pages (rowid, embedding) VALUES (?, ?)",
                    (rowid, sqlite_vec.serialize_float32(vec)),
                )

            conn.commit()
            if db_path is None:
                self._stored_dim = dim
        finally:
            conn.close()

    def _read_stored_dim(self, conn: sqlite3.Connection) -> int:
        """Return the embedding dim declared by the `vec_pages` table, or 0
        when the table does not exist / has no dim metadata.

        sqlite-vec declares the virtual table as `vec0(embedding float[N])`;
        the declared schema surfaces via `PRAGMA table_info` as a column with
        type `float[N]`. We parse N out of the type string.
        """
        try:
            rows = conn.execute("PRAGMA table_info(vec_pages)").fetchall()
        except sqlite3.OperationalError:
            return 0
        for row in rows:
            # row layout: (cid, name, type, notnull, dflt_value, pk)
            col_type = row[2] or ""
            match = re.search(r"float\[(\d+)\]", col_type, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return 0

    def query(self, query_vec: list[float], limit: int = 10) -> list[tuple[str, float]]:
        """Query for nearest neighbors. Returns [(page_id, distance), ...].

        Cycle 3 H7: validates `len(query_vec)` against the stored dim from
        `vec_pages` before running the MATCH query. Dim mismatch returns `[]`
        with a single WARN log (subsequent mismatches are silent — the cache
        remembers we already warned).
        Cycle 6 AC5: reuses a persistent `sqlite3.connect` via
        `_ensure_conn()`. Failure once → disabled forever (no retry loop).
        """
        conn = self._ensure_conn()
        if conn is None:
            return []

        try:
            import sqlite_vec

            if self._stored_dim is None:
                self._stored_dim = self._read_stored_dim(conn)
            stored_dim = self._stored_dim
            # stored_dim == 0 indicates an empty DB / missing table — not a
            # mismatch; just an empty index. Return without warning.
            if stored_dim == 0:
                return []
            if len(query_vec) != stored_dim:
                # Cycle 25 AC4 — increment process-level counter on EVERY
                # mismatch (decoupled from _dim_warned's once-per-instance
                # log-gate so tests see per-query deltas).
                global _dim_mismatches_seen
                _dim_mismatches_seen += 1
                if not self._dim_warned:
                    # Cycle 25 AC3 + Q7 resolution: self.db_path.parent.parent
                    # is the inverse of _vec_db_path(wiki_dir) which returns
                    # wiki_dir.parent / ".data" / "vector_index.db". Emitting
                    # db_path.parent.parent yields the wiki directory string
                    # `kb rebuild-indexes --wiki-dir <that>` expects (otherwise
                    # the `.data/...db` file path would be rejected by
                    # rebuild_indexes's containment validator).
                    wiki_dir_hint = self.db_path.parent.parent
                    logger.warning(
                        "Vector index dim mismatch: query=%d vs stored=%d at %s. "
                        "Run 'kb rebuild-indexes --wiki-dir %s' to realign, "
                        "OR ignore if BM25-only search is intended.",
                        len(query_vec),
                        stored_dim,
                        self.db_path,
                        wiki_dir_hint,
                    )
                    self._dim_warned = True
                return []

            rows = conn.execute(
                """
                SELECT p.page_id, v.distance
                FROM vec_pages v
                JOIN page_ids p ON p.rowid = v.rowid
                WHERE v.embedding MATCH ?
                AND v.k = ?
                ORDER BY v.distance
                """,
                (sqlite_vec.serialize_float32(query_vec), limit),
            ).fetchall()
            return [(row[0], row[1]) for row in rows]
        except Exception as e:
            logger.debug("Vector query failed: %s", e)
            return []
