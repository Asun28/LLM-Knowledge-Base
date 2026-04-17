"""MCP application instance and shared helpers."""

import logging
import os
from pathlib import Path

from fastmcp import FastMCP

from kb.config import PROJECT_ROOT, WIKI_DIR

logger = logging.getLogger(__name__)

# Error tagging for MCP tools that call the Anthropic API.
# Categories: prompt_too_long, rate_limit, corrupt_page, invalid_input, internal.
ERROR_TAG_FORMAT = "Error[{category}]: {message}"


def error_tag(category: str, message: str) -> str:
    """Return a categorised error string for MCP tool responses.

    Categories:
      - ``prompt_too_long`` — request exceeded the model's context window.
      - ``rate_limit``       — API rate limit hit; caller should retry later.
      - ``corrupt_page``     — a wiki page could not be read or parsed.
      - ``invalid_input``    — bad request parameters (non-context 400 error).
      - ``internal``         — unexpected LLM or system failure.
    """
    return ERROR_TAG_FORMAT.format(category=category, message=message)


mcp = FastMCP(
    "LLM Knowledge Base",
    instructions=(
        "Knowledge base tools for a structured wiki compiled from raw sources. "
        "You (Claude Code) ARE the LLM — no API key needed.\n\n"
        "WORKFLOW:\n"
        "- kb_query: returns wiki context for you to synthesize an answer.\n"
        "- kb_ingest: pass source_path + your extraction_json to create wiki pages. "
        "Omit extraction_json to get the extraction prompt first.\n"
        "- kb_ingest_content: one-shot for content not yet saved to raw/.\n"
        "- kb_save_source: save content to raw/ for later ingestion.\n"
        "- kb_compile_scan: find changed sources, then kb_ingest each.\n"
        "- kb_compile: run full compilation (requires ANTHROPIC_API_KEY).\n"
        "- kb_search, kb_read_page, kb_list_pages, kb_list_sources: browse wiki.\n"
        "- kb_lint, kb_evolve, kb_stats: health and gap analysis.\n"
        "- kb_detect_drift: find wiki pages stale due to raw source changes.\n"
        "- kb_review_page, kb_refine_page, kb_lint_deep, kb_lint_consistency: quality review.\n"
        "- kb_query_feedback, kb_reliability_map: feedback and trust scoring.\n"
        "- kb_affected_pages: find pages impacted by a change.\n"
        "- kb_save_lint_verdict: persist lint/review verdicts.\n"
        "- kb_create_page: create comparison/synthesis/any wiki page directly.\n"
        "- kb_graph_viz: export knowledge graph as Mermaid diagram.\n"
        "- kb_verdict_trends: show weekly quality trends from verdict history."
    ),
)


def _rel(path: Path) -> str:
    """Return path relative to project root with forward slashes."""
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


# Cycle 4 item #13 — cross-platform reservation of Windows device names.
# These basenames (with or without extension) are UNABLE to be created as
# regular files on Windows — NTFS aliases them to DOS devices. A wiki file
# written on Linux with one of these names breaks the entire Windows sync
# path. Cross-platform rejection at the MCP boundary is cheap insurance
# against corpus portability failures.
_WINDOWS_RESERVED_BASENAMES: frozenset[str] = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }
)

# Cap: NTFS / ext4 / APFS filename limit is 255 bytes; page IDs traverse a
# subdirectory plus a suffix, so accepting 255 chars for the ID itself is
# comfortably within any supported filesystem's ceiling.
_MAX_PAGE_ID_LEN: int = 255


def _is_windows_reserved(page_id: str) -> bool:
    """Check each path segment's stem (before final dot) against Windows reserved names.

    `CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9` with or without an extension
    all resolve to DOS devices on Windows. Case-insensitive. Strips at most one
    trailing dot-separated suffix so `CON.backup` is also rejected (matches
    Windows API semantics — anything matching the pattern `RESERVED(\\.[^.]*)?`
    that resolves at CreateFile time).
    """
    for segment in page_id.replace("\\", "/").split("/"):
        if not segment:
            continue
        # Strip extension(s); per Windows rules, `CON.foo.bar` is reserved too
        # because the OS only compares the stem before the first dot.
        stem = segment.split(".", 1)[0].casefold()
        if stem in _WINDOWS_RESERVED_BASENAMES:
            return True
    return False


def _validate_page_id(page_id: str, *, check_exists: bool = True) -> str | None:
    """Validate a page ID for security and optionally existence.

    Args:
        page_id: Page identifier (e.g., 'concepts/rag').
        check_exists: If True (default), also verify the page file exists.
            Set False when the caller handles existence separately.

    Returns:
        Error message string (caller prepends "Error:" before surfacing to MCP
        client), or None if valid.
    """
    if not page_id or not page_id.strip():
        return "page_id cannot be empty."
    if "\x00" in page_id:
        return "page_id contains null byte."
    # Cycle 4 item #13 — length cap before filesystem resolve.
    if len(page_id) > _MAX_PAGE_ID_LEN:
        return f"page_id too long ({len(page_id)} chars; max {_MAX_PAGE_ID_LEN})."
    if (
        ".." in page_id
        or page_id.startswith("/")
        or page_id.startswith("\\")
        or os.path.isabs(page_id)
    ):
        return f"Invalid page_id: {page_id}. Must not contain '..' or start with '/'."
    # Cycle 4 item #13 — reject Windows reserved basenames cross-platform.
    if _is_windows_reserved(page_id):
        return (
            f"page_id uses a Windows reserved device name "
            f"(CON, PRN, AUX, NUL, COM1-9, LPT1-9): {page_id}. "
            "Rename to avoid cross-platform filesystem failures."
        )
    page_path = WIKI_DIR / f"{page_id}.md"
    try:
        page_path.resolve().relative_to(WIKI_DIR.resolve())
    except ValueError:
        return f"Invalid page_id: {page_id}. Path escapes wiki directory."
    if check_exists and not page_path.exists():
        return f"Page not found: {page_id}. Use kb_list_pages to see available pages."
    return None


def _format_ingest_result(rel_path: str, source_type: str, source_hash: str, result: dict) -> str:
    """Format ingest result as readable text."""
    # Duplicate content: surface clearly instead of showing "0 pages created"
    if result.get("duplicate"):
        return (
            f"Duplicate content detected: {rel_path}\n"
            f"Type: {source_type}\n"
            f"Hash: {source_hash}\n"
            "This file has identical content to an already-ingested source. "
            "Skipped to avoid duplicate pages."
        )

    pages_created = result.get("pages_created", [])
    pages_updated = result.get("pages_updated", [])
    lines = [
        f"Ingested: {rel_path}",
        f"Type: {source_type}",
        f"Hash: {source_hash}",
        f"Pages created ({len(pages_created)}):",
    ]
    for p in pages_created:
        lines.append(f"  + {p}")
    lines.append(f"Pages updated ({len(pages_updated)}):")
    for p in pages_updated:
        lines.append(f"  ~ {p}")
    if result.get("pages_skipped"):
        lines.append(f"Pages skipped ({len(result['pages_skipped'])}):")
        for p in result["pages_skipped"]:
            lines.append(f"  ! {p}")

    # Wikilinks injected into existing pages
    wikilinks_injected = result.get("wikilinks_injected", [])
    if wikilinks_injected:
        lines.append(f"Wikilinks injected ({len(wikilinks_injected)}):")
        for p in wikilinks_injected:
            lines.append(f"  -> {p}")

    # Affected pages (cascade update detection) — pipeline returns flat list[str]
    affected = result.get("affected_pages", [])
    if affected:
        lines.append(f"Affected pages ({len(affected)}) — may need review:")
        for p in affected:
            lines.append(f"  ~ {p}")

    return "\n".join(lines)
