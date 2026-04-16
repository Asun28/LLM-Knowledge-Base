"""Embedding wrapper (model2vec) and vector index (sqlite-vec)."""

import logging
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


def _reset_model() -> None:
    """Reset cached model and index. Call in test teardown."""
    global _model
    _model = None
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
            # Clear any stale cache entry
            _index_cache.pop(str(vec_path), None)
            return True

        texts = [page.get("content", "") for page in pages]
        embeddings = embed_texts(texts)
        entries = [(page["id"], emb) for page, emb in zip(pages, embeddings)]
        VectorIndex(vec_path).build(entries)
        _index_cache.pop(str(vec_path), None)
        logger.info("Vector index rebuilt: %s (%d entries)", vec_path, len(entries))
        return True


def get_vector_index(vec_path: str) -> "VectorIndex":
    """Return a cached VectorIndex keyed by path. Avoids re-instantiation per query."""
    key = str(vec_path)
    if key not in _index_cache:
        _index_cache[key] = VectorIndex(Path(vec_path))
    return _index_cache[key]


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
    """sqlite-vec backed vector index for wiki page embeddings."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def build(self, entries: list[tuple[str, list[float]]]) -> None:
        """Build index from (page_id, embedding) pairs. Replaces existing index."""
        if not entries:
            # Create empty DB
            conn = sqlite3.connect(str(self.db_path))
            conn.close()
            return

        dim = len(entries[0][1])
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
        finally:
            conn.close()

    def query(self, query_vec: list[float], limit: int = 10) -> list[tuple[str, float]]:
        """Query for nearest neighbors. Returns [(page_id, distance), ...]."""
        if not self.db_path.exists():
            return []

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.enable_load_extension(True)
            import sqlite_vec

            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        except Exception as e:
            logger.warning("sqlite_vec extension load failed — vector search disabled: %s", e)
            conn.close()
            return []

        try:
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
        finally:
            conn.close()
