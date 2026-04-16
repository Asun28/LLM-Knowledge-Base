"""Content hashing for incremental compilation (hash-based change detection)."""

import hashlib
from pathlib import Path

_HASH_CHUNK_SIZE = 65536


def _normalize_newlines(data: bytes) -> bytes:
    """Normalize CRLF and lone CR to LF. Item 11 (cycle 2): prevents Windows
    clones with core.autocrlf=true from hashing every source differently from
    POSIX (which would force a full re-ingest on first compile)."""
    # Order matters: CRLF first so we don't double-convert trailing CR of CRLF.
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def content_hash(path: Path | str) -> str:
    """Compute first 32 hex chars (128-bit prefix of SHA-256) of a file's contents.

    The 128-bit prefix has a birthday bound of ~2^64 ≈ 1.8e19; collision
    probability is ~n²/2^129 for n inputs (≈ 10^-31 at n=10^4, ≈ 10^-3 at
    n=10^18). Intended as a content identifier for change detection and
    deduplication — NOT a security-relevant identifier. Do not use for
    authentication, signatures, or anywhere collision resistance against
    adversaries is required.

    Item 11 (cycle 2): Line endings are normalized (CRLF/CR → LF) before hashing
    so the same file on Windows and POSIX produces the same hash.
    """
    path = Path(path) if isinstance(path, str) else path
    h = hashlib.sha256()
    carry = b""
    with path.open("rb") as f:
        while chunk := f.read(_HASH_CHUNK_SIZE):
            buf = carry + chunk
            # Defer a trailing CR to the next iteration — it may be the CR of a
            # CRLF that straddles the chunk boundary.
            if buf.endswith(b"\r"):
                carry = b"\r"
                buf = buf[:-1]
            else:
                carry = b""
            h.update(_normalize_newlines(buf))
    if carry:
        h.update(_normalize_newlines(carry))
    return h.hexdigest()[:32]


def hash_bytes(data: bytes) -> str:
    """Compute first 32 hex chars (128-bit prefix of SHA-256) of raw bytes.

    Use instead of content_hash(path) when bytes are already in memory —
    eliminates TOCTOU risk and the duplicate I/O.

    Item 11 (cycle 2): Line endings normalized (CRLF/CR → LF) before hashing,
    matching content_hash so in-memory and on-disk calls agree.
    """
    return hashlib.sha256(_normalize_newlines(data)).hexdigest()[:32]
