"""Marp output adapter — Phase 4.11.

Emits marp-compatible markdown (marp: true directive + --- slide separators).
The slide splitter is code-fence-aware: fenced blocks are never broken across
slides, even if their internal blank lines would otherwise trigger a split.
"""

from __future__ import annotations

import yaml

from kb.query.citations import format_citations
from kb.query.formats.common import build_provenance, validate_payload_size

_DEFAULT_SLIDE_CHARS = 800


def _split_into_slides(text: str, max_chars: int = _DEFAULT_SLIDE_CHARS) -> list[str]:
    """Split text into slide-sized chunks while preserving fenced code blocks.

    Splits on \\n\\n boundaries, packing paragraphs until max_chars is reached,
    but never breaks inside a triple-backtick fenced region. A fenced block
    larger than max_chars is kept whole (overflow is acceptable).

    Args:
        text: the raw markdown body to split.
        max_chars: soft cap per slide (exceeded only to preserve fenced blocks).

    Returns:
        List of slide strings; at least one element (may equal original text).
    """
    if not text:
        return [""]

    segments = text.split("\n\n")
    slides: list[str] = []
    current: list[str] = []
    current_len = 0
    in_fence = False

    for seg in segments:
        # Count fence toggles in this segment; odd count flips the state
        fences = seg.count("```")
        would_toggle = (fences % 2) == 1

        add_len = len(seg) + (2 if current else 0)  # +2 for the "\n\n" rejoin
        # Only flush when we're NOT currently inside a fence
        if current and not in_fence and (current_len + add_len) > max_chars:
            slides.append("\n\n".join(current))
            current = [seg]
            current_len = len(seg)
        else:
            current.append(seg)
            current_len += add_len

        if would_toggle:
            in_fence = not in_fence

    if current:
        slides.append("\n\n".join(current))

    return slides if slides else [""]


def render_marp(result: dict) -> str:
    """Render a query result as a marp-compatible markdown deck.

    Slide structure:
        - Frontmatter (marp: true + provenance metadata)
        - Question slide
        - One or more Answer slides (800-char soft cap, fence-aware split)
        - Sources slide
    """
    validate_payload_size(result)

    prov = build_provenance(result)
    prov["format"] = "marp"

    marp_header: dict = {
        "marp": True,
        "theme": "default",
        "paginate": True,
    }
    # Prefix provenance keys with kb_ so they're clearly distinct from marp directives
    for k, v in prov.items():
        marp_header[f"kb_{k}"] = v

    frontmatter = yaml.safe_dump(
        marp_header, sort_keys=False, allow_unicode=True, default_flow_style=False
    )

    question = result.get("question", "").strip() or "(untitled)"
    answer = result.get("answer", "").strip() or "_No answer synthesized._"
    citations = result.get("citations", [])
    sources_block = format_citations(citations, mode="marp") if citations else "_No sources cited._"

    answer_slides = _split_into_slides(answer)
    answer_sections: list[str] = []
    for i, slide in enumerate(answer_slides):
        title = "# Answer" if i == 0 else f"# Answer (cont. {i + 1})"
        answer_sections.append(f"{title}\n\n{slide}")

    parts = [
        f"---\n{frontmatter}---\n",
        f"# Question\n\n{question}\n",
    ]
    for slide in answer_sections:
        parts.append(f"---\n\n{slide}\n")
    parts.append(f"---\n\n# Sources\n\n{sources_block}\n")
    return "\n".join(parts)
