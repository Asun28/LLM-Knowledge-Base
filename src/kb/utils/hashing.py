"""Content hashing for incremental compilation (hash-based change detection)."""

import hashlib
from pathlib import Path

_HASH_CHUNK_SIZE = 65536


def content_hash(path: Path | str) -> str:
    """Compute first 32 hex chars (128-bit prefix of SHA-256) of a file's contents."""
    path = Path(path) if isinstance(path, str) else path
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_HASH_CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()[:32]
