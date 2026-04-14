"""Jupyter output adapter — Phase 4.11.

Emits a valid .ipynb via nbformat v4 with explicit kernelspec. Never sets
metadata.trusted=True (auto-exec vector). All user-controlled strings are
json.dumps'd into code-cell literals — never f-string interpolated.
"""

from __future__ import annotations

import json

import nbformat as nbf

from kb.query.citations import format_citations
from kb.query.formats.common import build_provenance, validate_payload_size


def render_jupyter(result: dict) -> str:
    """Render a query result as a .ipynb (JSON string) using nbformat v4."""
    validate_payload_size(result)

    prov = build_provenance(result)
    question = result.get("question", "") or "(untitled query)"
    answer = result.get("answer", "") or "_No answer synthesized._"
    citations = result.get("citations", [])
    sources_md = (
        format_citations(citations, mode="markdown") if citations else "_No sources cited._"
    )

    nb = nbf.v4.new_notebook()
    # Explicit kernelspec so Jupyter/VSCode don't prompt on open.
    # trusted deliberately NOT set (auto-execute vector).
    nb.metadata = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.12"},
        "kb_query": prov,
    }

    nb.cells = [
        nbf.v4.new_markdown_cell(f"# Question\n\n{question}"),
        nbf.v4.new_markdown_cell(f"## Answer\n\n{answer}"),
        nbf.v4.new_markdown_cell(f"## Sources\n{sources_md}"),
        nbf.v4.new_code_cell(
            "# Re-run this query or inspect citations programmatically\n"
            "from kb.query.engine import query_wiki\n\n"
            f"QUESTION = {json.dumps(question)}\n"
            "# result = query_wiki(QUESTION)\n"
            "# print(result['answer'])"
        ),
    ]

    # Validate before emitting — surfaces malformed metadata as ValidationError
    nbf.validate(nb)

    return nbf.writes(nb)
