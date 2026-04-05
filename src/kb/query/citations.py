"""Citation and provenance tracking for query answers."""

import re


def extract_citations(text: str) -> list[dict]:
    """Extract citation references from an LLM-generated answer.

    Looks for patterns like [source: wiki/path] or [ref: raw/path] in text.

    Returns:
        List of dicts with keys: type ('wiki' or 'raw'), path, context (surrounding text).
    """
    citations = []
    # Match [source: path] or [ref: path] patterns
    pattern = re.compile(r"\[(source|ref):\s*([\w/.-]+)\]")
    for match in pattern.finditer(text):
        cite_type = "wiki" if match.group(1) == "source" else "raw"
        citations.append({
            "type": cite_type,
            "path": match.group(2),
            "context": text[max(0, match.start() - 50) : match.end() + 50].strip(),
        })
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
