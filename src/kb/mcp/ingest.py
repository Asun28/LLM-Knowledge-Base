"""Ingest MCP tools — raw-source creation, capture, and ingestion."""

import json
import logging
import os
import re
from datetime import date
from pathlib import Path

from kb.capture import CaptureResult, capture_items
from kb.config import (
    MAX_INGEST_CONTENT_CHARS,
    PROJECT_ROOT,
    QUERY_CONTEXT_MAX_CHARS,
    RAW_DIR,
    SOURCE_TYPE_DIRS,
)
from kb.mcp.app import _format_ingest_result, _is_windows_reserved, _rel, mcp
from kb.utils.io import atomic_text_write
from kb.utils.sanitize import sanitize_error_text
from kb.utils.text import slugify, yaml_escape

logger = logging.getLogger(__name__)

# MCP-only whitelist — kept local so ingest tools do not import the heavy
# ingest pipeline merely to validate source extensions.
_TEXT_EXTENSIONS = frozenset({".md", ".txt", ".rst", ".csv", ".json", ".yaml", ".yml"})

_LEGACY_SYNC_NAMES = (
    "MAX_INGEST_CONTENT_CHARS",
    "PROJECT_ROOT",
    "QUERY_CONTEXT_MAX_CHARS",
    "RAW_DIR",
    "SOURCE_TYPE_DIRS",
    "_FILENAME_MAX_LEN",
    "_FILENAME_NON_ASCII_RE",
    "_TEXT_EXTENSIONS",
    "_format_ingest_result",
    "_is_windows_reserved",
    "_rel",
    "_validate_file_inputs",
    "_validate_filename_slug",
    "atomic_text_write",
    "logger",
    "os",
    "sanitize_error_text",
    "slugify",
    "yaml_escape",
)


def _refresh_legacy_bindings() -> None:
    """Honor legacy monkeypatches made through ``kb.mcp.core``."""
    import kb.mcp.core as core

    for name in _LEGACY_SYNC_NAMES:
        if hasattr(core, name):
            globals()[name] = getattr(core, name)


def _validate_file_inputs(filename: str, content: str) -> str | None:
    """Validate filename and content size. Returns error string or None if valid."""
    _refresh_legacy_bindings()
    if not filename or not filename.strip():
        return "Error: Filename cannot be empty."
    if len(filename) > _FILENAME_MAX_LEN:
        return f"Error: Filename too long (max {_FILENAME_MAX_LEN} chars)."
    # Cycle 35 AC13 — delegate the security-class checks (NUL / path-separator /
    # Windows-reserved / homoglyph / trailing-dot) to the shared helper. Public
    # return contract stays `str | None`.
    _, slug_err = _validate_filename_slug(filename)
    if slug_err:
        return slug_err
    if len(content) > MAX_INGEST_CONTENT_CHARS:
        return (
            f"Error: Content too large ({len(content)} chars). "
            f"Maximum: {MAX_INGEST_CONTENT_CHARS} chars."
        )
    return None


# Cycle 35 AC12 — free-form filename validator shared by `kb_ingest_content`
# and `kb_save_source` (called via `_validate_file_inputs`). Looser than
# `_validate_save_as_slug` because free-form filenames legitimately differ
# from their slug form (e.g. `My Document.md` slugifies to `my-document`).
# Returns `(filename, None)` on success; `("", error_msg)` on failure.
# Mirrors `_validate_save_as_slug` signature for caller-pattern consistency.
_FILENAME_NON_ASCII_RE = re.compile(r"[^\x00-\x7F]")
_FILENAME_MAX_LEN = 200


def _validate_filename_slug(filename: str) -> tuple[str, str | None]:
    """Validate a free-form user-supplied filename for kb_ingest_content / kb_save_source.

    Rejects:
      - non-string input
      - empty or whitespace-padded (existing `_validate_file_inputs` covers
        these; helper catches them too in case a future caller bypasses)
      - NUL byte (POSIX path truncation hazard)
      - path separators (``/``, ``\\``) or ``..`` (traversal)
      - trailing dot or trailing space (Windows trim aliasing — evades
        ``_is_windows_reserved`` because Windows silently strips them)
      - non-ASCII characters (homoglyph / RTL-override / zero-width attacks
        — slugify preserves Cyrillic via ``\\w`` so an explicit ASCII gate
        is required, mirroring cycle-16 L1)
      - length > ``_FILENAME_MAX_LEN`` (200)
      - Windows reserved basenames (``CON``, ``PRN``, ``NUL``, ``AUX``,
        ``COM1-9``, ``LPT1-9``) via the existing ``_is_windows_reserved``.

    Allows leading dot (``.env``) and leading dash (``-foo``) — both are
    POSIX-legitimate filename shapes and out of the helper's stated
    rejection set (Step-5 Q5).

    MUST NOT raise — callers (``_validate_file_inputs``) propagate the
    error_msg through MCP boundary as a string response.
    """
    _refresh_legacy_bindings()
    if not isinstance(filename, str):
        return "", "Error: filename must be a string"
    if not filename or filename.strip() != filename:
        return "", "Error: filename cannot be empty or have leading/trailing whitespace"
    if "\x00" in filename:
        return "", "Error: filename cannot contain NUL byte"
    if "/" in filename or "\\" in filename or ".." in filename:
        return "", "Error: filename cannot contain path separators or .."
    if filename.endswith("."):
        return "", "Error: filename cannot end with a dot (Windows trims silently)"
    if _FILENAME_NON_ASCII_RE.search(filename):
        return "", "Error: filename must be ASCII (homoglyphs / non-ASCII chars rejected)"
    if len(filename) > _FILENAME_MAX_LEN:
        return "", f"Error: filename too long (max {_FILENAME_MAX_LEN} chars)"
    if _is_windows_reserved(filename):
        return "", "Error: filename uses a Windows reserved device name"
    return filename, None


@mcp.tool()
def kb_ingest(
    source_path: str,
    source_type: str = "",
    extraction_json: str = "",
    use_api: bool = False,
) -> str:
    """Ingest a raw source file into the knowledge base.

    Default (Claude Code mode):
    - With extraction_json: creates wiki pages immediately using your extraction.
    - Without extraction_json: returns the extraction prompt. Read it, extract
      the JSON, then call kb_ingest again with extraction_json.

    With use_api=true: calls the Anthropic API for extraction (requires
    ANTHROPIC_API_KEY). Ignores extraction_json.

    Args:
        source_path: Path to source file (absolute or relative to project root).
        source_type: One of: article, paper, repo, video, podcast, book, dataset,
                     conversation, capture. Auto-detected from path if empty.
        extraction_json: JSON string with extracted fields. Required keys:
            title (str), entities_mentioned (list[str]), concepts_mentioned (list[str]).
            Optional: author, core_argument, key_claims, abstract, evidence.
            Omit to get the extraction prompt instead.
        use_api: If true, use the Anthropic API for extraction. Default false.
    """
    _refresh_legacy_bindings()
    path = Path(source_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()

    # Validate source path stays within raw/ directory (normcase for Windows)
    raw_norm = Path(os.path.normcase(str(RAW_DIR.resolve())))
    path_norm = Path(os.path.normcase(str(path)))
    try:
        path_norm.relative_to(raw_norm)
    except ValueError:
        return f"Error: Source path must be within raw/ directory: {source_path}"

    if not path.exists():
        # Cycle 4 item #1 — use _rel() to avoid leaking absolute filesystem
        # paths in MCP error responses.
        return f"Error: Source file not found: {_rel(path)}"

    # Reject binary file types
    if path.suffix.lower() not in _TEXT_EXTENSIONS:
        return f"Error: Unsupported file type '{path.suffix}'."

    # H1 (Phase 4.5 HIGH): stat-based size pre-check before read. Prevents
    # OOM from an attacker-controlled large raw/ file. Align the cap with
    # the downstream QUERY_CONTEXT_MAX_CHARS truncation: chars*4 bytes is a
    # conservative UTF-8 upper bound for 80KB of text. PR review round 1
    # noted the earlier MAX_INGEST_CONTENT_CHARS*4 was 8× this, making the
    # "OOM protection" framing loose.
    try:
        file_bytes = path.stat().st_size
    except OSError as e:
        # Cycle 4 PR R1 Codex MINOR 4 — strip absolute path from OSError text
        # so the MCP response does not leak filesystem layout. `e.filename`
        # may include a D:\... Windows UNC path; substitute with _rel(path).
        e_msg = str(e).replace(str(path), _rel(path))
        return f"Error: cannot stat source {_rel(path)}: {e_msg}"
    max_bytes = QUERY_CONTEXT_MAX_CHARS * 4
    if file_bytes > max_bytes:
        return f"Error: Source too large ({file_bytes} bytes; max {max_bytes} bytes)."

    # H2 (Phase 4.5 R4 HIGH): reject unknown source_type before template
    # loading or ingest. Previously `source_type='totally_bogus'` with a
    # valid extraction_json wrote `type: totally_bogus` into wiki frontmatter.
    if source_type and source_type not in SOURCE_TYPE_DIRS:
        if source_type in {"comparison", "synthesis"}:
            return (
                'Error: source_type "comparison" and "synthesis" are wiki page types, '
                "not ingest source types. Use kb_create_page to create those pages directly."
            )
        valid = ", ".join(sorted(SOURCE_TYPE_DIRS))
        return f"Error: Unknown source_type '{source_type}'. Valid: {valid}"

    # Cycle 23 AC4 — function-local binding to PEP-562 lazy-shim target.
    # Cycle 19 AC15 monkeypatch contract preserved — test patches on
    # `kb.ingest.pipeline.ingest_source` intercept every call site below
    # because the local `ingest_pipeline` binding resolves to the same
    # cached module object the tests patched.
    from kb.ingest import pipeline as ingest_pipeline

    # ── API mode ──
    if use_api:
        try:
            # Cycle 19 AC15 — owner-module attribute call.
            result = ingest_pipeline.ingest_source(path, source_type or None)
            return _format_ingest_result(
                _rel(Path(result["source_path"])),
                result["source_type"],
                result["content_hash"],
                result,
            )
        except Exception as e:
            logger.exception("Error ingesting %s (API mode)", source_path)
            return f"Error ingesting source: {sanitize_error_text(e, path)}"

    # ── Detect source type ──
    if not source_type:
        from kb.ingest.pipeline import detect_source_type

        try:
            source_type = detect_source_type(path)
        except ValueError as e:
            return f"Error: {e}. Please specify source_type."

    # ── Claude Code mode: with extraction → apply ──
    if extraction_json:
        try:
            extraction = json.loads(extraction_json)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON — {e}"

        # Validate required extraction fields
        if not isinstance(extraction, dict):
            return "Error: extraction_json must be a JSON object."
        if not extraction.get("title") and not extraction.get("name"):
            return (
                "Error: extraction_json must contain 'title' (or 'name'). "
                "Required keys: title, entities_mentioned, concepts_mentioned."
            )

        try:
            # Cycle 19 AC15 — owner-module attribute call.
            result = ingest_pipeline.ingest_source(path, source_type, extraction=extraction)
            return _format_ingest_result(
                _rel(path), result["source_type"], result["content_hash"], result
            )
        except Exception as e:
            logger.exception("Error ingesting %s", source_path)
            return f"Error ingesting source: {sanitize_error_text(e, path)}"

    # ── Claude Code mode: without extraction → return prompt ──
    from kb.ingest.extractors import build_extraction_prompt, load_template

    try:
        template = load_template(source_type)
    except FileNotFoundError as e:
        return f"Error: {sanitize_error_text(e)}"

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return f"Error reading source file: {sanitize_error_text(e, path)}"

    if len(content) > QUERY_CONTEXT_MAX_CHARS:
        return (
            f"Error: source too long ({len(content)} chars; "
            f"max {QUERY_CONTEXT_MAX_CHARS} chars). "
            f"Split the file or pass extraction_json inline."
        )
    prompt = build_extraction_prompt(content, template)

    rel_path = _rel(path)
    return (
        f"# Extraction needed for: {rel_path}\n\n"
        f"**Type:** {source_type}\n"
        f"**Template:** {template['name']} — {template['description']}\n\n"
        f"Read the source below, extract the JSON, then call kb_ingest again with:\n"
        f'  source_path="{yaml_escape(rel_path)}"\n'
        f'  source_type="{yaml_escape(source_type)}"\n'
        f"  extraction_json=<your JSON>\n\n"
        f"---\n\n{prompt}"
    )


@mcp.tool()
def kb_ingest_content(
    content: str,
    filename: str,
    source_type: str,
    extraction_json: str,
    url: str = "",
    use_api: bool = False,
) -> str:
    """One-shot ingest: save raw content + create wiki pages in a single call.

    Use this when you have content that isn't saved to raw/ yet (fetched URL,
    pasted text, etc.). Saves the source and creates all wiki pages.

    Args:
        content: The full raw source text.
        filename: Filename slug (e.g., 'karpathy-llm-knowledge-bases').
        source_type: One of: article, paper, repo, video, podcast, book, dataset,
                     conversation, capture.
        extraction_json: JSON string with extracted fields. Required keys:
            title (str), entities_mentioned (list[str]), concepts_mentioned (list[str]).
            Ignored when ``use_api=True`` — the Anthropic API performs extraction.
        url: Optional source URL for metadata.
        use_api: Cycle 6 AC1. If True, call the Anthropic API for extraction
            instead of requiring ``extraction_json``. Defaults to False to
            preserve the Claude-Code-mode contract where the client supplies
            the extraction dict. Mirrors the ``use_api`` parameter already on
            ``kb_query`` and ``kb_ingest``.
    """
    _refresh_legacy_bindings()
    err = _validate_file_inputs(filename, content)
    if err:
        return err

    slug = slugify(filename) or "untitled"
    type_dir = SOURCE_TYPE_DIRS.get(source_type)
    if not type_dir:
        if source_type in {"comparison", "synthesis"}:
            return (
                'Error: source_type "comparison" and "synthesis" are wiki page types, '
                "not ingest source types. Use kb_create_page to create those pages directly."
            )
        return (
            f"Error: Unknown source_type '{source_type}'. Use one of: {', '.join(SOURCE_TYPE_DIRS)}"
        )

    type_dir.mkdir(parents=True, exist_ok=True)
    file_path = type_dir / f"{slug}.md"

    extraction: dict | None = None
    if not use_api:
        # Validate extraction JSON BEFORE writing file to avoid orphaned files
        try:
            extraction = json.loads(extraction_json)
        except json.JSONDecodeError as e:
            return f"Error: Invalid extraction JSON — {e}"

        if not isinstance(extraction, dict):
            return "Error: extraction_json must be a JSON object."
        if not extraction.get("title") and not extraction.get("name"):
            return (
                "Error: extraction_json must contain 'title' (or 'name'). "
                "Required keys: title, entities_mentioned, concepts_mentioned."
            )

    save_content = content
    if url:
        header = f'---\nurl: "{yaml_escape(url)}"\nfetched: {date.today().isoformat()}\n---\n\n'
        save_content = header + content

    # Atomic exclusive create — avoid TOCTOU race between existence check and write
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(str(file_path), flags, 0o644)
    except FileExistsError:
        return (
            f"Error: Source file already exists: {file_path.name}. "
            "Use kb_save_source with overwrite=true to replace it."
        )
    # Cycle 4 item #5 — convert post-create OSError into Error[partial]
    # string per MCP contract (MCP tools return strings, never raise).
    # The earlier `raise` path violated the docs and prevented the agent
    # from retrying with overwrite=true on transient write failures.
    fd_transferred = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            fd_transferred = True
            f.write(save_content)
    except (KeyboardInterrupt, SystemExit):
        # Developer-controlled interruptions: clean up but re-raise per stdlib norms.
        if not fd_transferred:
            try:
                os.close(fd)
            except OSError:
                pass
        file_path.unlink(missing_ok=True)
        raise
    except OSError as write_err:
        # Bytes may have been partially flushed; unlink to avoid partial files.
        if not fd_transferred:
            try:
                os.close(fd)
            except OSError:
                pass
        file_path.unlink(missing_ok=True)
        # Cycle 33 AC1 + AC3 — pre-compute redacted error string ONCE so the
        # paired logger.warning + Error[partial]: return cannot drift apart.
        # Raw OSError.__str__ on Windows includes the absolute filename
        # (`[WinError 5] Access is denied: 'D:\\...'`); cycle-32 AC3 widening
        # routes Error[partial]: to CLI stderr where this would surface.
        sanitized_err = sanitize_error_text(write_err, file_path)
        logger.warning(
            "kb_ingest_content partial write to %s: %s; client must retry",
            _rel(file_path),
            sanitized_err,
        )
        return (
            f"Error[partial]: write to {_rel(file_path)} failed ({sanitized_err}); "
            "retry with kb_save_source(..., overwrite=true) then kb_ingest."
        )

    # Cycle 23 AC4 — function-local binding to PEP-562 lazy-shim target.
    from kb.ingest import pipeline as ingest_pipeline

    try:
        # Cycle 6 AC1 — when use_api=True, ``extraction`` is None so
        # ingest_source falls through to its LLM extraction path. Claude
        # Code mode stays default (explicit extraction dict).
        if extraction is None:
            # Cycle 19 AC15 — owner-module attribute call.
            result = ingest_pipeline.ingest_source(file_path, source_type)
        else:
            result = ingest_pipeline.ingest_source(file_path, source_type, extraction=extraction)
    except Exception as e:
        # Clean up orphaned file before returning error
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass
        logger.exception("Error ingesting %s after write", filename)
        return f"Error: Ingest failed — {sanitize_error_text(e, file_path)}"

    source_ref = _rel(file_path)
    return f"Saved source: {source_ref} ({len(save_content)} chars)\n" + _format_ingest_result(
        source_ref, result["source_type"], result["content_hash"], result
    )


@mcp.tool()
def kb_save_source(
    content: str,
    filename: str,
    source_type: str = "article",
    url: str = "",
    overwrite: bool = False,
) -> str:
    """Save content to raw/ as a source file without ingesting.

    Use when you want to save content now and ingest later.

    Args:
        content: The full text content to save.
        filename: Filename without extension (e.g., 'karpathy-llm-knowledge-bases').
        source_type: Determines which raw/ subdirectory. Default 'article'.
        url: Optional source URL to include as metadata.
        overwrite: If true, overwrite existing file. Default false (returns error).
    """
    _refresh_legacy_bindings()
    err = _validate_file_inputs(filename, content)
    if err:
        return err

    slug = slugify(filename) or "untitled"
    # Cycle 11 AC2 (same-class completeness with kb_ingest / kb_ingest_content):
    # comparison and synthesis are wiki page types, not raw source types — guide
    # the caller toward kb_create_page before the generic unknown-type branch.
    if source_type in {"comparison", "synthesis"}:
        return (
            f"Error: source_type '{source_type}' is a wiki page type, not a raw source "
            f"type; use kb_create_page to create comparison or synthesis pages directly."
        )
    type_dir = SOURCE_TYPE_DIRS.get(source_type)
    if not type_dir:
        return (
            f"Error: Unknown source_type '{source_type}'. Use one of: {', '.join(SOURCE_TYPE_DIRS)}"
        )

    type_dir.mkdir(parents=True, exist_ok=True)
    file_path = type_dir / f"{slug}.md"

    if url:
        header = f'---\nurl: "{yaml_escape(url)}"\nfetched: {date.today().isoformat()}\n---\n\n'
        content = header + content

    if overwrite:
        try:
            atomic_text_write(content, file_path)
        except OSError as e:
            return f"Error: Failed to write source file: {sanitize_error_text(e, file_path)}"
    else:
        # Atomic exclusive create — avoid TOCTOU race between existence check and write
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(str(file_path), flags, 0o644)
        except FileExistsError:
            return (
                f"Error: Source file already exists: {_rel(file_path)}. "
                "Use overwrite=true to replace it."
            )
        # Cycle 4 item #5 — convert post-create OSError into Error[partial]
        # string per MCP contract.
        fd_transferred = False
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                fd_transferred = True
                f.write(content)
        except (KeyboardInterrupt, SystemExit):
            if not fd_transferred:
                try:
                    os.close(fd)
                except OSError:
                    pass
            file_path.unlink(missing_ok=True)
            raise
        except OSError as write_err:
            if not fd_transferred:
                try:
                    os.close(fd)
                except OSError:
                    pass
            file_path.unlink(missing_ok=True)
            # Cycle 33 AC2 + AC3 — same pattern as kb_ingest_content above.
            sanitized_err = sanitize_error_text(write_err, file_path)
            logger.warning(
                "kb_save_source partial write to %s: %s; client must retry",
                _rel(file_path),
                sanitized_err,
            )
            return (
                f"Error[partial]: write to {_rel(file_path)} failed ({sanitized_err}); "
                "retry with overwrite=true."
            )
    return (
        f"Saved: {_rel(file_path)} ({len(content)} chars)\n"
        f'To ingest: kb_ingest("{_rel(file_path)}", "{yaml_escape(source_type)}")'
    )


@mcp.tool()
def kb_capture(content: str, provenance: str | None = None) -> str:
    """Extract discrete knowledge items (decisions, discoveries, corrections, gotchas)
    from up to 50KB of unstructured text and write each to raw/captures/<slug>.md.

    The scan-tier LLM atomizes the input; bodies are kept verbatim. Returns a list
    of file paths. Run kb_ingest on each path to promote items to wiki/.

    Args:
        content: up to 50KB of UTF-8 text (chat logs, notes, transcripts).
        provenance: optional grouping label. None → auto-generated session id.

    Returns:
        Plain-text summary of items written and noise filtered, or an Error: message.
    """
    _refresh_legacy_bindings()
    try:
        result = capture_items(content, provenance=provenance)
    except Exception as e:
        return f"Error: {type(e).__name__}: {sanitize_error_text(e)}"
    return _format_capture_result(result)


def _format_capture_result(result: CaptureResult) -> str:
    """Format CaptureResult per spec §7 MCP response formats."""
    n_items = len(result.items)

    if n_items > 0:
        head = (
            f"Captured {n_items} item{'s' if n_items != 1 else ''}, "
            f"filtered {result.filtered_out_count} as noise."
        )
        lines = [f"{head} Provenance: {result.provenance}", ""]
        for item in result.items:
            # capture_items always writes under CAPTURES_DIR; display the
            # logical path directly rather than reconstructing via string
            # search on path parts (which could mismatch on nested dirs
            # whose own name happens to be 'captures').
            rel = f"raw/captures/{item.path.name}"
            lines.append(f"- {rel}  [{item.kind}]")
        if result.rejected_reason:
            lines.append("")
            lines.append(result.rejected_reason)
        else:
            lines.append("")
            lines.append("Next: run kb_ingest on each path to promote to wiki/.")
        return "\n".join(lines)

    # Zero items
    if result.rejected_reason is not None:
        return result.rejected_reason  # already starts with "Error: ..."
    # Successful zero-items (LLM filtered everything as noise)
    return (
        f"Captured 0 items, filtered {result.filtered_out_count} as noise. "
        f"Provenance: {result.provenance}\n"
        f"(No items met the decision/discovery/correction/gotcha bar.)"
    )
