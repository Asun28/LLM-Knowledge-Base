"""Citation and provenance tracking for query answers."""

import html as _html
import re

# Matches both legacy `[source: X]` / `[ref: X]` and canonical `[[X]]` formats.
# Cycle 5 redo T1: prompt at engine.py instructs the new wikilink form; the
# extractor accepts both so legacy LLM outputs and persisted answers continue
# to parse.
_CITATION_PATTERN = re.compile(
    r"\[(source|ref):\s*([\w/_.-]+)\]|\[\[([\w/_.-]+)\]\]"
)

_VALID_FORMAT_MODES = frozenset({"markdown", "html", "marp"})


def extract_citations(text: str) -> list[dict]:
    """Extract citation references from an LLM-generated answer.

    Looks for patterns like [source: wiki/path] or [ref: raw/path] in text.
    Overrides type based on path prefix: raw/ paths are always type="raw".

    Item 17 (cycle 2): deduplicate by `(type, path)` preserving the first
    occurrence's context. Prior behaviour produced duplicate citations from
    the same page/source mentioned multiple times in one answer, inflating
    the downstream Sources list.

    Returns:
        List of dicts with keys: type ('wiki' or 'raw'), path, context (surrounding text).
    """
    citations = []
    seen: set[tuple[str, str]] = set()
    for match in _CITATION_PATTERN.finditer(text):
        # Group 2 = legacy `[source|ref: X]` path; group 3 = canonical `[[X]]` path.
        # Exactly one will be non-None per match.
        legacy_kind = match.group(1)
        path = match.group(2) if legacy_kind is not None else match.group(3)
        if ".." in path or path.startswith("/"):
            continue
        # Q_K_a fix (Phase 4.5 HIGH): reject per-segment leading-dot (e.g. raw/articles/.env)
        # while allowing legitimate dot-in-name (e.g. raw/articles/foo.env.md).
        # The old path.startswith(".") check was too broad — it only caught top-level dotfiles.
        if any(not part or part.startswith(".") for part in path.split("/")):
            continue
        if legacy_kind == "ref":
            cite_type = "raw"
        else:
            # legacy `[source: X]` and canonical `[[X]]` both default to wiki;
            # path-prefix check below promotes raw/ paths.
            cite_type = "wiki"
        # Override type based on path prefix
        if path.startswith("raw/"):
            cite_type = "raw"
        key = (cite_type, path)
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            {
                "type": cite_type,
                "path": path,
                "context": text[max(0, match.start() - 50) : match.end() + 50].strip(),
            }
        )
    return citations


def format_citations(citations: list[dict], mode: str = "markdown") -> str:
    """Format citations as a sources section in the requested mode.

    Modes:
        "markdown" (default): legacy behavior — `[[wikilinks]]` + `` `raw/paths` ``.
        "html":     `<ul>` list of `<a href="./wiki/path.md">path</a>` + `<code>raw/path</code>`.
        "marp":     same rendering as markdown (kept as distinct mode so future
                    Marp-specific link syntax can diverge).

    Raises:
        ValueError: unknown mode.
    """
    if mode not in _VALID_FORMAT_MODES:
        raise ValueError(
            f"format_citations: unknown mode '{mode}'; "
            f"expected one of {sorted(_VALID_FORMAT_MODES)}"
        )
    if not citations:
        return ""

    seen: set[str] = set()
    deduped: list[dict] = []
    for cite in citations:
        path = cite["path"]
        if path in seen:
            continue
        seen.add(path)
        deduped.append(cite)

    if mode == "html":
        lines = ['<ul class="sources">']
        for cite in deduped:
            escaped_path = _html.escape(cite["path"], quote=True)
            if cite["type"] == "wiki":
                href = f"./wiki/{escaped_path}.md"
                lines.append(f'  <li><a href="{href}">{escaped_path}</a></li>')
            else:
                lines.append(f"  <li><code>{escaped_path}</code></li>")
        lines.append("</ul>")
        return "\n".join(lines)

    # markdown + marp share the current legacy rendering
    lines = ["\n---\n**Sources:**\n"]
    for cite in deduped:
        path = cite["path"]
        if cite["type"] == "wiki":
            lines.append(f"- [[{path}]]")
        else:
            lines.append(f"- `{path}`")
    return "\n".join(lines)
