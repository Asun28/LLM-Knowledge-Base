"""Content hashing for incremental compilation (hash-based change detection)."""

import hashlib
from pathlib import Path


def content_hash(path: Path | str) -> str:
    """Compute SHA-256 hash of a file's contents (32-char hex digest)."""
    path = Path(path) if isinstance(path, str) else path
    return hashlib.sha256(path.read_bytes()).hexdigest()[:32]
