"""HTML output adapter — Phase 4.11.

Emits a self-contained HTML5 document with inline CSS and no external
assets. Every user-controlled string passes through html.escape(quote=True)
individually; citation anchors are built from the structured citations
list (never regex over already-escaped text).
"""

from __future__ import annotations

import html as _html

from kb.query.formats.common import build_provenance, validate_payload_size

_INLINE_CSS = """
body { font-family: ui-sans-serif, system-ui, sans-serif; max-width: 720px;
       margin: 2rem auto; padding: 0 1rem; line-height: 1.6; color: #222; }
h1 { border-bottom: 1px solid #eee; padding-bottom: .25rem; }
.sources { border-top: 1px solid #eee; margin-top: 2rem; padding-top: 1rem;
           font-size: .9em; }
.meta { color: #666; font-size: .85em; }
pre { background: #f5f5f5; padding: 1em; overflow-x: auto; border-radius: 4px; }
code { background: #f5f5f5; padding: 2px 4px; border-radius: 2px; }
ul.sources { list-style: disc; padding-left: 1.5rem; }
""".strip()


def _escape(s: str) -> str:
    """Shortcut for html.escape with quote=True."""
    return _html.escape(s or "", quote=True)


def _render_answer_body(answer: str) -> str:
    """Split answer into <p> paragraphs on blank lines; escape each.

    Paragraph breaks come from blank lines; single newlines become <br>.
    """
    if not answer.strip():
        return "<p><em>No answer synthesized.</em></p>"
    paras = [p.strip() for p in answer.split("\n\n") if p.strip()]
    out = []
    for p in paras:
        escaped = _escape(p).replace("\n", "<br>\n")
        out.append(f"<p>{escaped}</p>")
    return "\n".join(out)


def _render_sources(citations: list[dict]) -> str:
    """Build the sources block by delegating to the canonical renderer.

    Uses `kb.query.citations.format_citations(mode="html")` — same escape /
    dedup / link-scheme rules as the rest of the codebase. Wrapping only
    handles the empty-citations case with a dedicated placeholder.
    """
    if not citations:
        return '<p class="sources"><em>No sources cited.</em></p>'

    from kb.query.citations import format_citations

    rendered = format_citations(citations, mode="html")
    if not rendered:
        return '<p class="sources"><em>No sources cited.</em></p>'
    return rendered


def render_html(result: dict) -> str:
    """Render a query result as a self-contained HTML5 document."""
    validate_payload_size(result)

    prov = build_provenance(result)
    question = result.get("question", "") or "(untitled query)"
    answer = result.get("answer", "") or ""

    escaped_q = _escape(question)
    escaped_title_q = _escape(question[:80])
    generated_at = prov["generated_at"]
    kb_version = prov["kb_version"]
    source_count = len(prov["source_pages"])

    answer_block = _render_answer_body(answer)
    sources_block = _render_sources(prov["citations"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>KB Query: {escaped_title_q}</title>
  <meta name="kb-query" content="{escaped_q}">
  <meta name="kb-generated-at" content="{_escape(generated_at)}">
  <meta name="kb-version" content="{_escape(kb_version)}">
  <meta name="kb-source-count" content="{source_count}">
  <style>
{_INLINE_CSS}
  </style>
</head>
<body>
  <article>
    <header>
      <h1>{escaped_q}</h1>
      <p class="meta">Generated {_escape(generated_at)} · {source_count} source page(s)</p>
    </header>
    <section class="answer">
{answer_block}
    </section>
    <section>
      <h2>Sources</h2>
{sources_block}
    </section>
  </article>
</body>
</html>
"""
