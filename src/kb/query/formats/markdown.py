"""Markdown output adapter — Phase 4.11.

Emits a standalone markdown file with YAML provenance frontmatter +
H1 question + answer body + citations list. Frontmatter is parseable
by any YAML consumer; citations list uses [[wikilinks]] compatible
with Obsidian / wiki-compile tooling.
"""

from __future__ import annotations

import yaml

from kb.query.citations import format_citations
from kb.query.formats.common import build_provenance, validate_payload_size


def render_markdown(result: dict) -> str:
    """Render a query result as a standalone markdown document.

    Args:
        result: dict with keys question, answer, citations, source_pages.

    Returns:
        The full document as a string (UTF-8 safe; no encoding applied here).

    Raises:
        ValueError: answer exceeds MAX_OUTPUT_CHARS.
    """
    validate_payload_size(result)

    prov = build_provenance(result)
    prov["format"] = "markdown"

    # yaml.safe_dump handles quoting, newlines, and unicode.
    frontmatter = yaml.safe_dump(
        prov, sort_keys=False, allow_unicode=True, default_flow_style=False
    )

    question = result.get("question", "").strip() or "(untitled query)"
    answer = result.get("answer", "").strip() or "_No answer synthesized._"

    citations = result.get("citations", [])
    sources_block = format_citations(citations, mode="markdown") if citations else ""

    return f"---\n{frontmatter}---\n\n# {question}\n\n{answer}\n{sources_block}\n"
