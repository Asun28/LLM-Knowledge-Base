"""Shared helpers for query output adapters.

- safe_slug: slugify with empty-fallback + Windows-reserved-name guard + length cap
- output_path_for: collision-safe output path under OUTPUTS_DIR
- build_provenance: common provenance dict (dynamic kb_version)
- validate_payload_size: pre-render size guard
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from kb import __version__ as KB_VERSION
from kb.config import MAX_OUTPUT_CHARS
from kb.config import OUTPUTS_DIR as _CONFIG_OUTPUTS_DIR
from kb.utils.text import slugify

# Bound as a module attribute so tests can monkeypatch
# `kb.query.formats.common.OUTPUTS_DIR` to redirect output (see test fixtures).
OUTPUTS_DIR = _CONFIG_OUTPUTS_DIR

WINDOWS_RESERVED = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)
MAX_SLUG_LEN = 80
MAX_COLLISION_RETRIES = 9

_FORMAT_EXT = {
    "markdown": "md",
    "marp": "md",
    "html": "html",
    "chart": "py",
    "jupyter": "ipynb",
}


def safe_slug(text: str) -> str:
    """Slugify with empty-fallback + Windows-reserved-name guard + length cap."""
    slug = slugify(text)[:MAX_SLUG_LEN] if text else ""
    if not slug:
        return "untitled"
    # Guard Windows reserved names on any dot-separated component
    if any(part.upper() in WINDOWS_RESERVED for part in slug.split(".") if part):
        slug = f"{slug}_0"
    return slug


def output_path_for(question: str, fmt: str) -> Path:
    """Return a collision-safe reserved path under OUTPUTS_DIR for this question+format.

    Path scheme: outputs/{YYYY-MM-DD-HHMMSS-ffffff}-{slug}.{ext}
    Uses atomic `O_CREAT|O_EXCL` reservation to close the TOCTOU window between
    an `exists()` check and the adapter's subsequent atomic write — under
    concurrent queries or two processes targeting the same OUTPUTS_DIR, the
    reservation guarantees the caller owns the filename exclusively. The
    adapter's later `atomic_text_write(...)` uses `Path.replace()` which
    overwrites this zero-byte placeholder, which is safe because no other
    process can win the race to this filename. Suffixes -2..-9 are tried on
    conflict. Raises OSError if all retries exhausted.
    """
    # KeyError for bad format — caller should validate upstream
    ext = _FORMAT_EXT[fmt]
    # Read the module-scope OUTPUTS_DIR directly. Global name resolution goes
    # through the module's __dict__, so pytest's monkeypatch of
    # `kb.query.formats.common.OUTPUTS_DIR` is honored on every call without
    # a re-import (avoids pulling all adapter modules on the hot path).
    out_dir = OUTPUTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S-%f")
    slug = safe_slug(question)
    base = f"{ts}-{slug}"
    for suffix in ("", *(f"-{i}" for i in range(2, MAX_COLLISION_RETRIES + 2))):
        candidate = out_dir / f"{base}{suffix}.{ext}"
        try:
            # Atomic reserve: O_CREAT|O_EXCL fails if candidate already exists,
            # closing the TOCTOU race that a plain `exists()` check would leave
            # open. The zero-byte placeholder will be overwritten by the
            # adapter's atomic_text_write (temp + rename).
            fd = os.open(str(candidate), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            continue
        os.close(fd)
        return candidate
    raise OSError(f"Collision retries exhausted for {base}.{ext}")


def build_provenance(result: dict) -> dict:
    """Assemble the common provenance dict used across adapters.

    Note: result['question'] is the ORIGINAL (not rewritten) question —
    query_wiki stores the original at engine.py:425.
    """
    return {
        "type": "query_output",
        "query": result.get("question", ""),
        "generated_at": datetime.now(UTC).isoformat(timespec="microseconds"),
        "kb_version": KB_VERSION,
        "source_pages": list(result.get("source_pages", [])),
        "citations": list(result.get("citations", [])),
    }


def validate_payload_size(result: dict) -> None:
    """Raise ValueError if the answer exceeds MAX_OUTPUT_CHARS (pre-render)."""
    answer = result.get("answer", "") or ""
    if len(answer) > MAX_OUTPUT_CHARS:
        raise ValueError(
            f"Answer exceeds MAX_OUTPUT_CHARS={MAX_OUTPUT_CHARS} "
            f"(got {len(answer)}). Refuse to render."
        )
