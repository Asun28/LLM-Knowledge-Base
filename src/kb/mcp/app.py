"""MCP application instance and shared helpers."""

import logging
from pathlib import Path

from fastmcp import FastMCP

from kb.config import PROJECT_ROOT, WIKI_DIR

logger = logging.getLogger(__name__)

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
        "- kb_compile_scan: find changed sources, then kb_ingest each.\n"
        "- kb_search, kb_read_page, kb_list_pages, kb_list_sources: browse wiki.\n"
        "- kb_lint, kb_evolve, kb_stats: health and gap analysis."
    ),
)


def _rel(path: Path) -> str:
    """Return path relative to project root with forward slashes."""
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _validate_page_id(page_id: str) -> str | None:
    """Validate that a page ID exists. Returns error message or None."""
    page_path = WIKI_DIR / f"{page_id}.md"
    if not page_path.exists():
        return f"Page not found: {page_id}. Use kb_list_pages to see available pages."
    return None


def _format_ingest_result(rel_path: str, source_type: str, source_hash: str, result: dict) -> str:
    """Format ingest result as readable text."""
    lines = [
        f"Ingested: {rel_path}",
        f"Type: {source_type}",
        f"Hash: {source_hash}",
        f"Pages created ({len(result['pages_created'])}):",
    ]
    for p in result["pages_created"]:
        lines.append(f"  + {p}")
    lines.append(f"Pages updated ({len(result['pages_updated'])}):")
    for p in result["pages_updated"]:
        lines.append(f"  ~ {p}")
    return "\n".join(lines)
