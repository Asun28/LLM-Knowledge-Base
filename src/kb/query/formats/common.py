"""Shared helpers for query output adapters.

- safe_slug: slugify with empty-fallback + Windows-reserved-name guard + length cap
- output_path_for: collision-safe output path under OUTPUTS_DIR
- build_provenance: common provenance dict (dynamic kb_version)
- validate_payload_size: pre-render size guard
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from kb import __version__ as KB_VERSION
from kb.config import MAX_OUTPUT_CHARS, OUTPUTS_DIR
from kb.utils.text import slugify

WINDOWS_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})
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
    """Return a collision-safe path under OUTPUTS_DIR for this question+format.

    Path scheme: outputs/{YYYY-MM-DD-HHMMSS-ffffff}-{slug}.{ext}
    If the first candidate exists (microsecond collision under heavy concurrency),
    suffixes -2..-9 are tried. Raises OSError if all retries exhausted.
    """
    # KeyError for bad format — caller should validate upstream
    ext = _FORMAT_EXT[fmt]
    # Re-read OUTPUTS_DIR from the module so monkeypatching in tests works
    from kb.query.formats import common as _self
    out_dir = _self.OUTPUTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S-%f")
    slug = safe_slug(question)
    base = f"{ts}-{slug}"
    for suffix in ("", *(f"-{i}" for i in range(2, MAX_COLLISION_RETRIES + 2))):
        candidate = out_dir / f"{base}{suffix}.{ext}"
        if not candidate.exists():
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
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
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
