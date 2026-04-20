"""Publish wiki contents as machine-consumable outputs.

Cycle 14 AC20/AC21/AC22 — Tier-1 recommended next item (Karpathy-verbatim
``/llms.txt``, ``/llms-full.txt``, and ``/graph.jsonld``).

Cycle 16 AC20-AC22 adds two more builders:
  - ``build_per_page_siblings`` writes ``{out_dir}/pages/{page_id}.txt`` +
    ``.json`` per page (multi-file output — takes a base directory).
  - ``build_sitemap_xml`` writes ``{out_path}`` with sitemap.org/0.9 schema
    (single-file output — takes a full path).

Signature convention: single-file builders (``build_llms_txt``,
``build_llms_full_txt``, ``build_graph_jsonld``, ``build_sitemap_xml``)
take a full ``out_path``; multi-file builders (``build_per_page_siblings``)
take a base ``out_dir`` and derive child paths internally. This asymmetry
encodes output-cardinality and is intentional (cycle 16 Q9).

Security/threat mitigations:
  - T1 (path containment): enforced by the CLI wrapper ``kb publish``.
  - T2 (epistemic filter): pages with ``belief_state in {retracted,
    contradicted}`` OR ``confidence == speculative`` are excluded from
    every output with a ``[!excluded] N`` footer.
  - T3 (JSON injection): ``build_graph_jsonld`` uses ``json.dump`` with a
    fully-constructed Python dict; no f-string JSON assembly.
  - T7 (XML injection, cycle 16): ``build_sitemap_xml`` uses ``ET.SubElement``
    + ``.text`` assignment — never f-string-concatenates child text.
  - T8 (URL disclosure): every ``<loc>`` / ``url`` is a wiki-relative POSIX
    path; no absolute filesystem paths, no ``file://`` scheme.
  - T9 (sibling path traversal, cycle 16): every per-page sibling write
    resolves the target and asserts containment under ``out_dir/pages``.
  - T10 (incremental-skip retracted leak, cycle 16): per-page sibling
    cleanup for ``excluded`` pages runs UNCONDITIONALLY on every publish,
    BEFORE the incremental skip check — ``incremental=True`` can never
    leave stale retracted siblings on disk.
"""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from kb.utils.io import atomic_text_write
from kb.utils.markdown import extract_wikilinks
from kb.utils.pages import load_all_pages, scan_wiki_pages

logger = logging.getLogger(__name__)

# Cycle 14 AC20 — 5 MiB UTF-8 byte cap for llms-full.txt. Includes all
# separators, headers, and the truncation footer.
LLMS_FULL_MAX_BYTES = 5 * 1024 * 1024


def _publish_skip_if_unchanged(wiki_dir: Path, out_path: Path) -> bool:
    """Cycle 15 AC12 — mtime-based short-circuit for incremental publish.

    Returns ``True`` when ``out_path`` exists and its mtime is not older
    than the maximum mtime across canonical wiki pages (as produced by
    ``scan_wiki_pages``). Uses nanosecond-granular ``st_mtime_ns`` on both
    sides to avoid Windows/NFS second-granularity flakiness (threat T3).

    Auto-maintained index files (``log.md``, ``_sources.md``, ``index.md``,
    ``_categories.md``, ``contradictions.md``) are excluded because they
    mutate on every ingest without warranting a publish regen;
    ``scan_wiki_pages`` only walks the canonical wiki subdirs.

    **Single-writer assumed.** When another process writes a wiki page
    BETWEEN this mtime read and the caller's return, the stale output is
    handed back without regen. Operators who suspect drift should re-run
    with ``incremental=False`` (``kb publish --no-incremental``).
    """
    if not out_path.exists():
        return False
    try:
        max_page_mtime_ns = max(
            (p.stat().st_mtime_ns for p in scan_wiki_pages(wiki_dir)),
            default=0,
        )
        out_mtime_ns = out_path.stat().st_mtime_ns
    except OSError:
        return False
    return max_page_mtime_ns <= out_mtime_ns


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
    if str(page.get("belief_state", "")).lower() in _EXCLUDED_BELIEF_STATES:
        return True
    return False


def _partition_pages(pages: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split pages into (kept, excluded).

    Both ``confidence`` and ``belief_state`` are surfaced by
    ``load_all_pages`` (cycle 14), so no second disk read is required —
    partition is a pure dict check over the already-loaded page list.
    """
    kept: list[dict] = []
    excluded: list[dict] = []
    for page in pages:
        if _is_excluded(page):
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


def build_llms_txt(wiki_dir: Path, out_path: Path, *, incremental: bool = False) -> Path:
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

    Cycle 15 AC9/AC12 — uses ``atomic_text_write`` for crash-safe
    writes (temp + rename). With ``incremental=True`` and an output
    newer than every canonical wiki page, returns ``out_path`` without
    regen. T2 filter + T1 containment run BEFORE the skip branch
    (ordering invariant).

    Args:
        wiki_dir: Source wiki directory to enumerate.
        out_path: Destination file path (will be overwritten).
        incremental: When True, short-circuit if wiki pages are older than
            the existing output. Default False preserves cycle-14 test
            contracts.

    Returns:
        The ``out_path`` that was written (or skipped).
    """
    # Cycle 15 T10c — partition ONCE before skip check so the same kept/excluded
    # lists feed both branches. Earlier PR R1 draft called _partition_pages twice
    # (once discarded, once kept) which wasted work AND meant the skip branch
    # short-circuited on an unfiltered page list, exposing retracted content if
    # mtime failed to advance (coarse-mtime FAT32/OneDrive edge case).
    pages = load_all_pages(wiki_dir, include_content_lower=False)
    kept, excluded = _partition_pages(pages)
    if incremental and _publish_skip_if_unchanged(wiki_dir, out_path):
        return out_path
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
    atomic_text_write("\n".join(lines) + "\n", out_path)
    return out_path


def build_llms_full_txt(wiki_dir: Path, out_path: Path, *, incremental: bool = False) -> Path:
    """Write full wiki body content separated by ``\\n\\n----\\n\\n``.

    UTF-8 byte-capped at ``LLMS_FULL_MAX_BYTES`` including separators,
    headers, and the truncation footer. Pages are emitted in page_id
    order; when appending the next page would exceed the cap, the loop
    stops and emits a ``[TRUNCATED — N pages remaining]`` footer. If the
    FIRST page alone exceeds cap, it is included truncated with an
    ``[!oversized]`` marker (graceful fallback — empty output is worse).

    Same T2 filter as ``build_llms_txt``. Cycle 15 AC10/AC12 — atomic
    write + incremental skip (see ``build_llms_txt`` docstring).

    Args:
        wiki_dir: Source wiki directory.
        out_path: Destination file path.
        incremental: Short-circuit if wiki unchanged since last write.

    Returns:
        The ``out_path`` that was written (or skipped).
    """
    # Cycle 15 T10c — partition ONCE before skip (see build_llms_txt comment).
    pages = load_all_pages(wiki_dir, include_content_lower=False)
    kept, excluded = _partition_pages(pages)
    if incremental and _publish_skip_if_unchanged(wiki_dir, out_path):
        return out_path
    kept = _sort_pages(kept)

    parts: list[str] = []
    current_bytes = 0
    cap = LLMS_FULL_MAX_BYTES
    truncated_count = 0
    pages_written = 0
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
                    pages_written = 1
            truncated_count = len(kept) - pages_written
            break
        parts.append(piece)
        current_bytes += piece_bytes
        pages_written = idx + 1

    footer_lines: list[str] = []
    if truncated_count > 0:
        # MINOR 4 fix: emit truncation footer even when first_page_oversized,
        # so operators reading the file know additional pages were omitted.
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
    atomic_text_write("".join(parts + footer_lines), out_path)
    return out_path


def build_graph_jsonld(wiki_dir: Path, out_path: Path, *, incremental: bool = False) -> Path:
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
    # Cycle 15 T10c — partition ONCE before skip (see build_llms_txt comment).
    pages = load_all_pages(wiki_dir, include_content_lower=False)
    kept, excluded = _partition_pages(pages)
    if incremental and _publish_skip_if_unchanged(wiki_dir, out_path):
        return out_path
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
    # Cycle 15 AC11 — atomic_text_write colocates temp file with out_path
    # (threat T4 — prevents os.replace degrading to copy+delete across
    # volumes on Windows/OneDrive). json.dumps preserves the cycle-14 T3
    # contract (no f-string JSON assembly).
    atomic_text_write(json.dumps(document, ensure_ascii=False, indent=2) + "\n", out_path)
    return out_path


# ── Cycle 16 AC20-AC22 — per-page siblings + sitemap ─────────────────────


def _sibling_paths_for(page_id: str, pages_dir: Path) -> tuple[Path, Path]:
    """Return (txt_path, json_path) for a page under the siblings base."""
    txt = pages_dir / f"{page_id}.txt"
    return txt, txt.with_suffix(".json")


def _is_contained(target: Path, base: Path) -> bool:
    """Safe containment check: target's resolved path must live under base."""
    try:
        resolved_target = target.resolve()
        resolved_base = base.resolve()
    except OSError:
        return False
    return str(resolved_target).startswith(str(resolved_base))


def build_per_page_siblings(
    wiki_dir: Path, out_dir: Path, *, incremental: bool = False
) -> list[Path]:
    """Emit one ``.txt`` + ``.json`` sibling pair per kept page.

    Cycle 16 AC20 / AC22 / T7 / T8 / T9 / T10.

    Layout::
        {out_dir}/pages/{page_id}.txt   # title + body plaintext
        {out_dir}/pages/{page_id}.json  # metadata (sort_keys=True determinism)

    Behaviour:
      - Retracted/contradicted/speculative pages EXCLUDED (T2/T10).
      - Cleanup (unlink ``.txt`` + ``.json``) for currently-excluded pages
        runs UNCONDITIONALLY on every call, BEFORE the incremental skip
        check — ``incremental=True`` cannot leak stale siblings (cycle 16
        Q2/C3 amendment).
      - Per-page target paths are resolve()-checked under ``{out_dir}/pages``
        before any write (T9). A page whose id escapes containment is
        skipped with a warning.
      - Incremental skip: when ``incremental=True`` and the output directory
        is newer than the newest wiki page mtime, returns the existing
        sibling paths without re-writing.

    Returns:
        Sorted list of paths written (or that exist after cleanup).
    """
    pages = load_all_pages(wiki_dir)
    kept, excluded = _partition_pages(pages)

    pages_dir = (out_dir / "pages").resolve()
    pages_dir.mkdir(parents=True, exist_ok=True)

    # T10 cycle 16 Q2/C3 — cleanup runs UNCONDITIONALLY (before skip).
    for page in excluded:
        page_id = str(page.get("id", "")).strip()
        if not page_id:
            continue
        txt_path, json_path = _sibling_paths_for(page_id, pages_dir)
        # Containment check: only unlink paths that LAND under pages_dir;
        # refuse to follow a hostile page_id elsewhere on disk.
        if _is_contained(txt_path, pages_dir):
            txt_path.unlink(missing_ok=True)
        if _is_contained(json_path, pages_dir):
            json_path.unlink(missing_ok=True)

    # Incremental short-circuit (cleanup already ran).
    if incremental and _publish_skip_if_unchanged(wiki_dir, pages_dir):
        logger.info("build_per_page_siblings skipped — output dir newer than wiki")
        return sorted(pages_dir.rglob("*.txt")) + sorted(pages_dir.rglob("*.json"))

    written: list[Path] = []
    for page in _sort_pages(kept):
        page_id = str(page.get("id", "")).strip()
        if not page_id:
            continue
        txt_path, json_path = _sibling_paths_for(page_id, pages_dir)
        # T9 — skip paths that resolve outside pages_dir.
        if not _is_contained(txt_path, pages_dir) or not _is_contained(json_path, pages_dir):
            logger.warning(
                "build_per_page_siblings skipping page_id=%r — path traversal risk", page_id
            )
            continue
        txt_path.parent.mkdir(parents=True, exist_ok=True)

        title = str(page.get("title", page_id))
        body = str(page.get("content", ""))
        plaintext = f"{title}\n\n{body}" if body else title + "\n"
        atomic_text_write(plaintext, txt_path)
        written.append(txt_path)

        # R1 amendment — stdlib json.dumps(sort_keys=True) for deterministic
        # cross-platform byte output (AC22 idempotency).
        meta = {
            "title": title,
            "page_id": page_id,
            "url": f"pages/{page_id}.txt",
            "updated": str(page.get("updated", "")),
            "confidence": str(page.get("confidence", "")),
            "belief_state": str(page.get("belief_state", "")),
            "authored_by": str(page.get("authored_by", "")),
            "status": str(page.get("status", "")),
            "source": list(page.get("sources", [])),
        }
        json_body = json.dumps(meta, indent=2, sort_keys=True, ensure_ascii=False)
        atomic_text_write(json_body + "\n", json_path)
        written.append(json_path)

    return sorted(written)


def build_sitemap_xml(wiki_dir: Path, out_path: Path, *, incremental: bool = False) -> Path:
    """Emit a ``sitemap.xml`` at ``out_path`` per sitemap.org/0.9 schema.

    Cycle 16 AC21 / AC22 / T7 / T8 / T10.

    Each ``<url>`` entry has:
      - ``<loc>`` — wiki-relative POSIX path ``pages/{page_id}.txt`` (T8).
      - ``<lastmod>`` — the page ``updated`` frontmatter value (ISO-8601
        YYYY-MM-DD) when present and non-empty.

    XML construction uses ``ET.SubElement(...).text = value`` so child
    text is escaped by the stdlib serializer — no f-string concat (T7).
    """
    pages = load_all_pages(wiki_dir)
    kept, _ = _partition_pages(pages)

    if incremental and _publish_skip_if_unchanged(wiki_dir, out_path):
        logger.info("build_sitemap_xml skipped — output newer than wiki")
        return out_path

    urlset = ET.Element("urlset", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})
    for page in _sort_pages(kept):
        page_id = str(page.get("id", "")).strip()
        if not page_id:
            continue
        url = ET.SubElement(urlset, "url")
        loc = ET.SubElement(url, "loc")
        loc.text = f"pages/{page_id}.txt"  # T8: relative POSIX only
        lastmod_value = str(page.get("updated", "")).strip()
        if lastmod_value:
            lastmod = ET.SubElement(url, "lastmod")
            lastmod.text = lastmod_value

    xml_body = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(urlset, encoding="unicode")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_text_write(xml_body + "\n", out_path)
    return out_path
