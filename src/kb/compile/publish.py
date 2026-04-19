"""Publish wiki contents as machine-consumable outputs.

Cycle 14 AC20/AC21/AC22 — Tier-1 recommended next item (Karpathy-verbatim
``/llms.txt``, ``/llms-full.txt``, and ``/graph.jsonld``). Each builder is
a pure function: reads from ``wiki_dir``, writes one file to ``out_path``.

Security/threat mitigations:
  - T1 (path containment): enforced by the CLI wrapper ``kb publish``.
  - T2 (epistemic filter): pages with ``belief_state in {retracted,
    contradicted}`` OR ``confidence == speculative`` are excluded from
    every output with a ``[!excluded] N`` footer.
  - T3 (JSON injection): ``build_graph_jsonld`` uses ``json.dump`` with a
    fully-constructed Python dict; no f-string JSON assembly.
  - T8 (URL disclosure): JSON-LD ``url`` is a wiki-relative POSIX path; no
    absolute filesystem paths and no ``file://`` scheme.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from kb.utils.markdown import extract_wikilinks
from kb.utils.pages import load_all_pages

logger = logging.getLogger(__name__)

# Cycle 14 AC20 — 5 MiB UTF-8 byte cap for llms-full.txt. Includes all
# separators, headers, and the truncation footer.
LLMS_FULL_MAX_BYTES = 5 * 1024 * 1024

# Page separator for llms-full.txt — four-dash horizontal rule + blank
# lines.
_PAGE_SEPARATOR = "\n\n----\n\n"

# Filter predicate keys per threat T2.
_EXCLUDED_BELIEF_STATES = frozenset({"retracted", "contradicted"})
_EXCLUDED_CONFIDENCE = "speculative"


def _is_excluded(page: dict) -> bool:
    """Return True if the page should be filtered from publish outputs.

    Threat T2 — pages with belief_state in {retracted, contradicted}, or
    confidence == speculative, are unfit for external LLM consumption.
    """
    if str(page.get("confidence", "")).lower() == _EXCLUDED_CONFIDENCE:
        return True
    # belief_state comes from metadata via load_all_pages. This module
    # reads raw frontmatter directly below since load_all_pages doesn't
    # surface belief_state today. See partition logic.
    return False


def _partition_pages(pages: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split pages into (kept, excluded).

    The ``belief_state`` field is not yet surfaced by ``load_all_pages``;
    read it from the raw frontmatter via python-frontmatter for each page
    so we can respect the filter.
    """
    import frontmatter

    kept: list[dict] = []
    excluded: list[dict] = []
    for page in pages:
        # Fast-path: confidence comes from load_all_pages.
        if _is_excluded(page):
            excluded.append(page)
            continue
        # Slow-path: pull belief_state from the page's frontmatter.
        try:
            parsed = frontmatter.load(page["path"])
        except (OSError, ValueError, UnicodeDecodeError):
            kept.append(page)
            continue
        belief_state = str(parsed.metadata.get("belief_state", "")).lower()
        if belief_state in _EXCLUDED_BELIEF_STATES:
            excluded.append(page)
        else:
            kept.append(page)
    return kept, excluded


def _sort_pages(pages: list[dict]) -> list[dict]:
    """Deterministic ascending page_id order for reproducible outputs."""
    return sorted(pages, key=lambda p: p["id"])


def _sanitize_line(text: str) -> str:
    """Collapse embedded newlines so the llms.txt one-line-per-page
    contract survives titles/sources with U+2028 / \\n / \\r.

    Threat T3 (plain-text variant).
    """
    return (
        str(text)
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\u2028", " ")
        .replace("\u2029", " ")
    )


def build_llms_txt(wiki_dir: Path, out_path: Path) -> Path:
    """Write a one-line-per-page index grouped by page type.

    Format:
        # LLMs index
        ## entity
        Title — raw/articles/foo.md — 2026-04-20
        ...

    Each page gets exactly one line, `\\n`-collapsed. Pages with
    belief_state in {retracted, contradicted} or confidence ==
    speculative are filtered (threat T2); an ``[!excluded] N pages``
    footer records the count.

    Args:
        wiki_dir: Source wiki directory to enumerate.
        out_path: Destination file path (will be overwritten).

    Returns:
        The ``out_path`` that was written.
    """
    pages = load_all_pages(wiki_dir, include_content_lower=False)
    kept, excluded = _partition_pages(pages)
    kept = _sort_pages(kept)

    lines: list[str] = ["# LLMs index", ""]
    by_type: dict[str, list[dict]] = {}
    for page in kept:
        by_type.setdefault(str(page.get("type", "unknown")), []).append(page)
    for ptype in sorted(by_type):
        lines.append(f"## {ptype}")
        for page in by_type[ptype]:
            title = _sanitize_line(page.get("title", page["id"]))
            sources = page.get("sources") or []
            source_ref = _sanitize_line(sources[0]) if sources else "(no source)"
            updated = _sanitize_line(page.get("updated", ""))
            lines.append(f"{title} — {source_ref} — {updated}")
        lines.append("")
    if excluded:
        lines.append(
            f"[!excluded] {len(excluded)} pages filtered (retracted/contradicted/speculative)"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def build_llms_full_txt(wiki_dir: Path, out_path: Path) -> Path:
    """Write full wiki body content separated by ``\\n\\n----\\n\\n``.

    UTF-8 byte-capped at ``LLMS_FULL_MAX_BYTES`` including separators,
    headers, and the truncation footer. Pages are emitted in page_id
    order; when appending the next page would exceed the cap, the loop
    stops and emits a ``[TRUNCATED — N pages remaining]`` footer. If the
    FIRST page alone exceeds cap, it is included truncated with an
    ``[!oversized]`` marker (graceful fallback — empty output is worse).

    Same T2 filter as ``build_llms_txt``.

    Args:
        wiki_dir: Source wiki directory.
        out_path: Destination file path.

    Returns:
        The ``out_path`` that was written.
    """
    pages = load_all_pages(wiki_dir, include_content_lower=False)
    kept, excluded = _partition_pages(pages)
    kept = _sort_pages(kept)

    parts: list[str] = []
    current_bytes = 0
    cap = LLMS_FULL_MAX_BYTES
    truncated_count = 0
    first_page_oversized = False

    for idx, page in enumerate(kept):
        title = _sanitize_line(page.get("title", page["id"]))
        header = f"# {title}\n\n"
        body = str(page.get("content", ""))
        payload = header + body
        # Prepend separator for non-first pages
        piece = payload if idx == 0 else _PAGE_SEPARATOR + payload
        piece_bytes = len(piece.encode("utf-8"))
        # Reserve room for the future footer (worst case).
        worst_case_footer = b"\n\n[TRUNCATED 9999999 pages remaining: , , ...]\n"
        if current_bytes + piece_bytes > cap - len(worst_case_footer):
            if idx == 0:
                # Oversized first page — include a truncated slice so
                # the file is not empty (graceful fallback).
                slice_limit = cap - len(worst_case_footer) - 64
                if slice_limit > 0:
                    encoded = piece.encode("utf-8")[:slice_limit]
                    # Avoid mid-codepoint split — decode with errors=ignore
                    parts.append(encoded.decode("utf-8", errors="ignore"))
                    parts.append("\n\n[!oversized page truncated]\n")
                    current_bytes += len(encoded)
                    first_page_oversized = True
                idx += 1
            truncated_count = len(kept) - idx
            break
        parts.append(piece)
        current_bytes += piece_bytes

    footer_lines: list[str] = []
    if truncated_count > 0 and not first_page_oversized:
        remaining_ids = [
            p["id"] for p in kept[len(kept) - truncated_count : len(kept) - truncated_count + 3]
        ]
        footer_lines.append(
            f"\n\n[TRUNCATED {truncated_count} pages remaining: {', '.join(remaining_ids)} ...]\n"
        )
    if excluded:
        footer_lines.append(
            f"[!excluded] {len(excluded)} pages filtered (retracted/contradicted/speculative)\n"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(parts + footer_lines), encoding="utf-8")
    return out_path


def build_graph_jsonld(wiki_dir: Path, out_path: Path) -> Path:
    """Write a JSON-LD graph of wiki pages.

    Uses ``json.dump(obj, f, ensure_ascii=False, indent=2)`` with a
    fully-constructed Python dict (threat T3). Each node is a
    ``CreativeWork`` with an allowlisted set of fields:
      - ``@type``
      - ``name`` (title)
      - ``url`` (wiki-relative POSIX path — threat T8)
      - ``dateModified`` (updated)
      - ``citation`` (list of relative URLs for outbound wikilinks)

    Same T2 filter as the other builders.

    Args:
        wiki_dir: Source wiki directory.
        out_path: Destination file path.

    Returns:
        The ``out_path`` that was written.
    """
    pages = load_all_pages(wiki_dir, include_content_lower=False)
    kept, excluded = _partition_pages(pages)
    kept = _sort_pages(kept)

    # Build an id→url map so citations can resolve wikilinks to relative
    # URLs of the pages we actually kept.
    id_to_url: dict[str, str] = {}
    for page in kept:
        try:
            page_path = Path(page["path"])
            url = page_path.relative_to(wiki_dir).as_posix()
        except (ValueError, OSError):
            url = page["id"]
        id_to_url[page["id"]] = url

    nodes: list[dict] = []
    for page in kept:
        url = id_to_url[page["id"]]
        body = str(page.get("content", ""))
        wikilinks = extract_wikilinks(body)
        citations: list[str] = []
        for target in wikilinks:
            # extract_wikilinks already lowercases targets and strips .md.
            if target in id_to_url:
                citations.append(id_to_url[target])
        node = {
            "@type": "CreativeWork",
            "name": str(page.get("title", page["id"])),
            "url": url,
            "dateModified": str(page.get("updated", "")),
        }
        if citations:
            node["citation"] = citations
        nodes.append(node)

    document = {
        "@context": "https://schema.org/",
        "@graph": nodes,
    }
    if excluded:
        # Avoid f-string inside the JSON-LD builder body per threat T3 grep
        # contract — use concatenation; json.dump handles escaping regardless.
        excluded_count = str(len(excluded))
        document["disambiguatingDescription"] = (
            excluded_count + " pages filtered (retracted/contradicted/speculative)"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(document, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return out_path
