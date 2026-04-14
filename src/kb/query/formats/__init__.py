"""Output-format adapters for kb_query (Phase 4.11).

Public API:
    render_output(fmt, result) -> Path | None
    VALID_FORMATS: frozenset[str]
"""

from __future__ import annotations

from pathlib import Path

from kb.query.formats.chart import render_chart
from kb.query.formats.common import output_path_for
from kb.query.formats.html import render_html
from kb.query.formats.jupyter import render_jupyter
from kb.query.formats.markdown import render_markdown
from kb.query.formats.marp import render_marp
from kb.utils.io import atomic_text_write

__all__ = ["VALID_FORMATS", "render_output"]

VALID_FORMATS = frozenset({"text", "markdown", "marp", "html", "chart", "jupyter"})

_ADAPTERS = {
    "markdown": render_markdown,
    "marp": render_marp,
    "html": render_html,
    "chart": render_chart,
    "jupyter": render_jupyter,
}


def _normalize(fmt: str) -> str:
    return (fmt or "").strip().lower()


def render_output(fmt: str, result: dict) -> Path | None:
    """Render `result` into the requested format and write to OUTPUTS_DIR.

    Args:
        fmt: one of VALID_FORMATS (case/whitespace normalized here).
        result: query_wiki-shaped dict with question, answer, citations,
                source_pages, context_pages.

    Returns:
        Path to the written file, or None when fmt is "text" (no-op).

    Raises:
        ValueError: unknown format, or payload size exceeds MAX_OUTPUT_CHARS.
        OSError: collision retries exhausted or write failure.
    """
    fmt_n = _normalize(fmt)
    if fmt_n not in VALID_FORMATS:
        raise ValueError(f"unknown format '{fmt}'; expected one of {sorted(VALID_FORMATS)}")
    if fmt_n == "text":
        return None  # text is stdout-only; no file produced

    adapter = _ADAPTERS[fmt_n]
    question = result.get("question", "") or "(untitled)"
    path = output_path_for(question, fmt_n)

    if fmt_n == "chart":
        script, data_json = adapter(result)
        atomic_text_write(script, path)
        json_sidecar = path.with_suffix(".json")
        atomic_text_write(data_json, json_sidecar)
    else:
        payload = adapter(result)
        atomic_text_write(payload, path)

    return path
