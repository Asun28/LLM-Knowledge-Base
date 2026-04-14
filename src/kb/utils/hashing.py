"""Content hashing for incremental compilation (hash-based change detection)."""

import hashlib
from pathlib import Path

_HASH_CHUNK_SIZE = 65536


def content_hash(path: Path | str) -> str:
    """Compute first 32 hex chars (128-bit prefix of SHA-256) of a file's contents.

    The 128-bit prefix is collision-safe up to ~10^18 inputs (birthday bound
    ~2^64 ≈ 10^19). Intended as a content identifier for change detection and
    deduplication — NOT a security-relevant identifier. Do not use for
    authentication, signatures, or anywhere collision resistance against
    adversaries is required.
    """
    path = Path(path) if isinstance(path, str) else path
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_HASH_CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()[:32]


def hash_bytes(data: bytes) -> str:
    """Compute first 32 hex chars (128-bit prefix of SHA-256) of raw bytes.

    Use instead of content_hash(path) when bytes are already in memory —
    eliminates TOCTOU risk and the duplicate I/O.
    """
    return hashlib.sha256(data).hexdigest()[:32]
