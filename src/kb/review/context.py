"""Page-source pairing and review context builder."""

from pathlib import Path

import frontmatter

from kb.config import RAW_DIR, WIKI_DIR


def pair_page_with_sources(
    page_id: str, wiki_dir: Path | None = None, raw_dir: Path | None = None
) -> dict:
    """Load a wiki page and all its referenced raw sources.

    Args:
        page_id: Wiki page ID (e.g., 'concepts/rag').
        wiki_dir: Path to wiki directory.
        raw_dir: Path to raw directory.

    Returns:
        Dict with page_id, page_content, page_metadata, source_contents.
        On error: dict with 'error' key.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    raw_dir = raw_dir or RAW_DIR

    page_path = wiki_dir / f"{page_id}.md"
    if not page_path.exists():
        return {"error": f"Page not found: {page_id}", "page_id": page_id}

    post = frontmatter.load(str(page_path))

    # Get source paths from frontmatter
    sources_meta = post.metadata.get("source", [])
    if isinstance(sources_meta, str):
        sources_meta = [sources_meta]

    source_contents = []
    for source_ref in sources_meta:
        # Resolve: "raw/articles/foo.md" -> project_root / "raw/articles/foo.md"
        # source_ref starts with "raw/" so we go to parent of raw_dir (= project root)
        project_root = raw_dir.parent
        source_path = project_root / source_ref
        if source_path.exists():
            source_contents.append(
                {
                    "path": source_ref,
                    "content": source_path.read_text(encoding="utf-8"),
                }
            )
        else:
            source_contents.append(
                {
                    "path": source_ref,
                    "content": None,
                    "error": f"Source file not found: {source_ref}",
                }
            )

    return {
        "page_id": page_id,
        "page_content": post.content,
        "page_metadata": dict(post.metadata),
        "source_contents": source_contents,
    }


def build_review_checklist() -> str:
    """Return the review checklist text for quality evaluation."""
    return (
        "## Review Checklist\n\n"
        "Evaluate each item and report findings as JSON:\n\n"
        "1. **Source fidelity**: Does every factual claim trace to a specific source passage?\n"
        "2. **Entity/concept accuracy**: Are entities and concepts correctly identified?\n"
        "3. **Wikilink validity**: Do all [[wikilinks]] resolve to existing pages?\n"
        "4. **Confidence level**: Does the confidence match the evidence strength?\n"
        "5. **No hallucination**: Is there information NOT present in the raw source?\n"
        "6. **Title accuracy**: Does the title accurately reflect the page content?\n\n"
        "Return your review as JSON:\n```json\n"
        '{\n  "verdict": "approve | revise | reject",\n'
        '  "fidelity_score": 0.0,\n'
        '  "issues": [{"severity": "error|warning|info", '
        '"type": "unsourced_claim|missing_info|wrong_confidence|broken_link", '
        '"description": "...", "suggested_fix": "..."}],\n'
        '  "missing_from_source": ["..."],\n'
        '  "suggestions": ["..."]\n}\n```'
    )


def build_review_context(
    page_id: str, wiki_dir: Path | None = None, raw_dir: Path | None = None
) -> str:
    """Build a complete review context for a wiki page.

    Returns formatted text with page content, source content, and review checklist.
    Claude Code or the wiki-reviewer agent uses this context to produce a structured review.
    """
    paired = pair_page_with_sources(page_id, wiki_dir, raw_dir)

    if "error" in paired and "page_content" not in paired:
        return f"Error: {paired['error']}"

    lines = [
        f"# Review Context for: {page_id}\n",
        f"**Type:** {paired['page_metadata'].get('type', 'unknown')}",
        f"**Confidence:** {paired['page_metadata'].get('confidence', 'unknown')}",
        f"**Sources:** {len(paired['source_contents'])} file(s)\n",
        "---\n",
        "## Wiki Page Content\n",
        paired["page_content"],
        "\n---\n",
    ]

    for i, source in enumerate(paired["source_contents"], 1):
        lines.append(f"## Raw Source {i}: {source['path']}\n")
        if source.get("content"):
            lines.append(source["content"])
        else:
            lines.append(f"*Source file not available: {source.get('error', 'unknown')}*")
        lines.append("\n---\n")

    lines.append(build_review_checklist())

    return "\n".join(lines)
