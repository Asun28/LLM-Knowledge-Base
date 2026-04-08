"""Content hashing for incremental compilation (hash-based change detection)."""

import hashlib
from pathlib import Path


def content_hash(path: Path | str) -> str:
    """Compute first 32 hex chars (128-bit prefix of SHA-256) of a file's contents."""
    path = Path(path) if isinstance(path, str) else path
    return hashlib.sha256(path.read_bytes()).hexdigest()[:32]
