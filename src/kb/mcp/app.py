"""MCP application instance and shared helpers."""

import logging
import os
import re
from pathlib import Path

from fastmcp import FastMCP

from kb.config import MAX_NOTES_LEN, MAX_PAGE_ID_LEN, PROJECT_ROOT, WIKI_DIR

# Cycle 42 AC2 — `_rel` is re-exported for back-compat with `kb.mcp.core` and any
# downstream caller that previously imported from `kb.mcp.app`. Ruff autofix
# (`F401 unused-import`) will silently strip the line if the noqa is missing —
# class-of-bug per cycle-22 L2 / feedback_ruff_unused_import_monkeypatch.
from kb.utils.sanitize import _rel, sanitize_error_text  # noqa: F401

logger = logging.getLogger(__name__)

# Error tagging for MCP tools that call the Anthropic API.
# Categories: prompt_too_long, rate_limit, corrupt_page, invalid_input, internal.
ERROR_TAG_FORMAT = "Error[{category}]: {message}"


_INSTRUCTIONS_PREAMBLE = (
    "Knowledge base tools for a structured wiki compiled from raw sources. "
    "You (Claude Code) ARE the LLM — no API key needed.\n\n"
    "WORKFLOW:"
)

_TOOL_GROUPS = (
    (
        "Browse",
        (
            ("kb_search", "browse wiki."),
            ("kb_read_page", "browse wiki."),
            ("kb_list_pages", "browse wiki."),
            ("kb_list_sources", "browse wiki."),
        ),
    ),
    (
        "Ingest",
        (
            (
                "kb_ingest",
                "pass source_path + your extraction_json to create wiki pages. "
                "Omit extraction_json to get the extraction prompt first.",
            ),
            ("kb_ingest_content", "one-shot for content not yet saved to raw/."),
            ("kb_save_source", "save content to raw/ for later ingestion."),
            (
                "kb_capture",
                "extract discrete knowledge items from unstructured text into raw/captures/.",
            ),
            ("kb_compile_scan", "find changed sources, then kb_ingest each."),
            ("kb_compile", "run full compilation (requires ANTHROPIC_API_KEY)."),
        ),
    ),
    (
        "Health",
        (
            ("kb_stats", "health and gap analysis."),
            ("kb_lint", "health and gap analysis."),
            ("kb_evolve", "health and gap analysis."),
            ("kb_detect_drift", "find wiki pages stale due to raw source changes."),
            ("kb_graph_viz", "export knowledge graph as Mermaid diagram."),
            ("kb_verdict_trends", "show weekly quality trends from verdict history."),
        ),
    ),
    (
        "Quality",
        (
            ("kb_review_page", "quality review."),
            ("kb_refine_page", "quality review."),
            ("kb_lint_deep", "quality review."),
            ("kb_lint_consistency", "quality review."),
            ("kb_query_feedback", "feedback and trust scoring."),
            ("kb_reliability_map", "feedback and trust scoring."),
            ("kb_affected_pages", "find pages impacted by a change."),
            ("kb_save_lint_verdict", "persist lint/review verdicts."),
            ("kb_create_page", "create comparison/synthesis/any wiki page directly."),
            ("kb_refine_sweep", "sweep stale refine-pending rows (cycle 20 AC14)."),
            ("kb_refine_list_stale", "list stale refine-pending rows (cycle 20 AC17)."),
        ),
    ),
    (
        "Query",
        (("kb_query", "returns wiki context for you to synthesize an answer."),),
    ),
)


def _render_instructions() -> str:
    _lines = [_INSTRUCTIONS_PREAMBLE, "", "## Tool Groups"]
    for group_name, tools in _TOOL_GROUPS:
        _lines.append(f"\n### {group_name}")
        for name, desc in sorted(tools, key=lambda t: t[0]):
            _lines.append(f"- `{name}` — {desc}")
    return "\n".join(_lines)


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
    instructions=_render_instructions(),
)


def _validate_wiki_dir(
    wiki_dir: str | None, *, project_root: Path | None = None
) -> tuple[Path | None, str | None]:
    if wiki_dir is None:
        return None, None
    effective_project_root = project_root or PROJECT_ROOT
    try:
        path = Path(wiki_dir).expanduser()
    except (TypeError, ValueError) as e:
        return None, f"wiki_dir invalid: {sanitize_error_text(e)}"
    if not path.is_absolute():
        return None, f"wiki_dir must be an absolute path (got: {wiki_dir})"
    if not path.exists():
        return None, f"wiki_dir does not exist: {sanitize_error_text(str(path))}"
    if not path.is_dir():
        return None, f"wiki_dir is not a directory: {sanitize_error_text(str(path))}"
    path_resolved = path.resolve()
    root = effective_project_root.resolve()
    if path_resolved != root and not path_resolved.is_relative_to(root):
        return (
            None,
            f"wiki_dir must be inside project root — got {sanitize_error_text(str(path_resolved))}",
        )
    return path_resolved, None


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

# Cycle 5 redo T3: cap reconciled to config.MAX_PAGE_ID_LEN (200). Previously a
# local 255-char cap diverged from the feedback/verdict-store cap, producing a
# double-gate where page IDs of 201-255 chars passed MCP validation but later
# tripped the persistence layer. Single source of truth now in kb.config.
_CTRL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_NOTES_UNSAFE_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")

# Cycle 17 AC11-AC13 — shared run-id validator for `kb_lint(resume=...)`.
# Exact 8 hex chars eliminates `Path.glob` prefix-collision ambiguity
# (design gate Q8 decision): the augment manifest filename is
# `augment-run-<run_id[:8]>.json`, so a full exact-8-hex input matches
# a deterministic filename with no wildcard interpolation.
# `re.fullmatch` (not `re.match` + `$`) because Python's `$` matches before a
# trailing `\n` by default — `re.fullmatch` requires the pattern to cover the
# entire string, rejecting `"abc12345\n"` and similar trailing-junk inputs.
_RUN_ID_RE = re.compile(r"[0-9a-f]{8}")


def _validate_run_id(run_id: str) -> str | None:
    """Validate a resume run id for `kb_lint(resume=...)` / `kb lint --resume`.

    Empty string is the sentinel for "no resume" (bypasses validation).

    Args:
        run_id: Candidate id, either ``""`` (no resume) or exactly 8 hex chars.

    Returns:
        Error message string on invalid input (caller prepends ``"Error:"``
        for MCP surfaces or raises ``click.UsageError``/``ValueError``), or
        ``None`` when valid.
    """
    if run_id == "":
        return None
    if not _RUN_ID_RE.fullmatch(run_id):
        return f"Invalid resume id: {run_id!r}. Must be exactly 8 hex chars (0-9a-f)."
    return None


def _validate_notes(notes: str, field_name: str) -> str | None:
    """Validate free-text MCP notes after stripping control and bidi characters."""
    stripped = _NOTES_UNSAFE_RE.sub("", notes or "")
    if len(stripped) > MAX_NOTES_LEN:
        return f"Error: {field_name} too long ({len(stripped)} chars; max {MAX_NOTES_LEN})."
    return None


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


def _validate_page_id(
    page_id: str, *, check_exists: bool = True, wiki_dir: Path | None = None
) -> str | None:
    """Validate a page ID for security and optionally existence.

    Args:
        page_id: Page identifier (e.g., 'concepts/rag').
        check_exists: If True (default), also verify the page file exists.
            Set False when the caller handles existence separately.
        wiki_dir: Optional wiki directory to validate against. Defaults to the
            module-level WIKI_DIR.

    Returns:
        Error message string (caller prepends "Error:" before surfacing to MCP
        client), or None if valid.
    """
    if _CTRL_CHARS_RE.search(page_id):
        return "page_id contains control characters."
    if not page_id or not page_id.strip():
        return "page_id cannot be empty."
    # Cycle 4 item #13 — length cap before filesystem resolve.
    if len(page_id) > MAX_PAGE_ID_LEN:
        return f"page_id too long ({len(page_id)} chars; max {MAX_PAGE_ID_LEN})."
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
    effective_wiki_dir = wiki_dir or WIKI_DIR
    page_path = effective_wiki_dir / f"{page_id}.md"
    try:
        page_path.resolve().relative_to(effective_wiki_dir.resolve())
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
