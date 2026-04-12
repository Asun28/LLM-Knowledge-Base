"""Embedding wrapper (model2vec) and vector index (sqlite-vec)."""

import logging
import sqlite3
import threading
from pathlib import Path

from kb.config import EMBEDDING_DIM, EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()


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
        except Exception:
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
