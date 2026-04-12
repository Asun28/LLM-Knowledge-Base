"""Citation and provenance tracking for query answers."""

import re

_CITATION_PATTERN = re.compile(r"\[(source|ref):\s*([\w/_.-]+)\]")


def extract_citations(text: str) -> list[dict]:
    """Extract citation references from an LLM-generated answer.

    Looks for patterns like [source: wiki/path] or [ref: raw/path] in text.
    Overrides type based on path prefix: raw/ paths are always type="raw".

    Returns:
        List of dicts with keys: type ('wiki' or 'raw'), path, context (surrounding text).
    """
    citations = []
    for match in _CITATION_PATTERN.finditer(text):
        path = match.group(2)
        if ".." in path or path.startswith("/") or path.startswith("."):
            continue
        # Reject paths with empty components (e.g. raw//page) or consecutive dots mid-component
        if any(not part or ".." in part for part in path.split("/")):
            continue
        cite_type = "wiki" if match.group(1) == "source" else "raw"
        # Override type based on path prefix
        if path.startswith("raw/"):
            cite_type = "raw"
        citations.append(
            {
                "type": cite_type,
                "path": path,
                "context": text[max(0, match.start() - 50) : match.end() + 50].strip(),
            }
        )
    return citations


def format_citations(citations: list[dict]) -> str:
    """Format citations as a markdown sources section."""
    if not citations:
        return ""
    lines = ["\n---\n**Sources:**\n"]
    seen = set()
    for cite in citations:
        path = cite["path"]
        if path in seen:
            continue
        seen.add(path)
        if cite["type"] == "wiki":
            lines.append(f"- [[{path}]]")
        else:
            lines.append(f"- `{path}`")
    return "\n".join(lines)
