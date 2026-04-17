"""Embedding wrapper (model2vec) and vector index (sqlite-vec)."""

import logging
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
_index_cache: dict[str, "VectorIndex"] = {}
# Cycle 3 H8: serialize concurrent `get_vector_index` lookups. Without this,
# two FastMCP worker threads hitting an uncached `vec_path` both instantiate
# a `VectorIndex` and both write into `_index_cache`; future `__init__`
# side-effects (DB schema validation, file lock) would race. Matches the
# `_model_lock` / `_rebuild_lock` double-checked pattern.
_index_cache_lock = threading.Lock()


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


def rebuild_vector_index(wiki_dir: Path, force: bool = False) -> bool:
    """Rebuild the sqlite-vec index from all pages in wiki_dir.

    H17 fix: this is the production entry point that was previously missing,
    leaving Phase 4 "hybrid" search as BM25-only in practice.

    Gates:
        1. ``_hybrid_available`` — model2vec + sqlite_vec must be importable.
        2. mtime check (skipped when ``force=True``) — if the DB is newer than
           all wiki pages, no rebuild is performed.
        3. ``_rebuild_lock`` — serializes concurrent callers (double-checked).

    Args:
        wiki_dir: Path to the wiki directory (used to locate pages and DB).
        force: Skip the mtime gate and always rebuild.

    Returns:
        True if the index was (re)built; False if skipped.
    """
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
        vec_path = _vec_db_path(wiki_dir)
        vec_path.parent.mkdir(parents=True, exist_ok=True)

        if not pages:
            VectorIndex(vec_path).build([])
            logger.info("Vector index rebuilt: %s (0 entries)", vec_path)
            # Cycle 3 H8 PR review R1 Sonnet MAJOR: clear stale cache entry
            # under the index cache lock so a concurrent `get_vector_index`
            # caller cannot observe the evicted instance after the pop.
            with _index_cache_lock:
                _index_cache.pop(str(vec_path), None)
            return True

        texts = [page.get("content", "") for page in pages]
        embeddings = embed_texts(texts)
        entries = [(page["id"], emb) for page, emb in zip(pages, embeddings)]
        VectorIndex(vec_path).build(entries)
        with _index_cache_lock:
            _index_cache.pop(str(vec_path), None)
        logger.info("Vector index rebuilt: %s (%d entries)", vec_path, len(entries))
        return True


def get_vector_index(vec_path: str) -> "VectorIndex":
    """Return a cached VectorIndex keyed by path. Avoids re-instantiation per query.

    Cycle 3 H8: double-checked locking around `_index_cache` — the fast path
    skips the lock when the key is already populated; the slow path serializes
    instantiation so concurrent FastMCP threads observe a single shared
    `VectorIndex`.
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
        return cached


def _get_model():
    """Lazy-load model2vec model (thread-safe singleton)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from model2vec import StaticModel

                _model = StaticModel.from_pretrained(EMBEDDING_MODEL)
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
        self._disabled: bool = False
        self._ext_warned: bool = False

    def _ensure_conn(self) -> sqlite3.Connection | None:
        """Lazy-load sqlite3 connection + sqlite_vec extension.

        Returns the persistent connection, or ``None`` when the index is
        disabled (extension unavailable / DB missing). Never retries after a
        failure: the `_disabled` flag is sticky.
        """
        if self._disabled:
            return None
        if self._conn is not None:
            return self._conn
        if not self.db_path.exists():
            # Not disabled — the DB may be created later by ``build()``.
            # Leave _conn=None so the next query retries only if DB appears.
            return None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.enable_load_extension(True)
            import sqlite_vec

            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        except Exception as e:
            if not self._ext_warned:
                logger.warning("sqlite_vec extension load failed — vector search disabled: %s", e)
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

    def build(self, entries: list[tuple[str, list[float]]]) -> None:
        """Build index from (page_id, embedding) pairs. Replaces existing index.

        Cycle 3 L2: the dim used in the f-string `CREATE VIRTUAL TABLE ...
        vec0(embedding float[{dim}])` is validated to be a sane positive
        integer. An attacker-controlled or bug-introduced non-int dim would
        otherwise be interpolated verbatim into SQL.
        """
        if not entries:
            # Create empty DB and reset dim cache.
            conn = sqlite3.connect(str(self.db_path))
            conn.close()
            self._stored_dim = 0
            return

        dim = len(entries[0][1])
        if not (isinstance(dim, int) and 1 <= dim <= self._MAX_DIM):
            raise ValueError(f"Invalid embedding dim={dim!r}; expected int in [1, {self._MAX_DIM}]")
        conn = sqlite3.connect(str(self.db_path))
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
                if not self._dim_warned:
                    logger.warning(
                        "Vector index dim mismatch: query=%d vs stored=%d at %s; "
                        "returning empty (rebuild index to align)",
                        len(query_vec),
                        stored_dim,
                        self.db_path,
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
