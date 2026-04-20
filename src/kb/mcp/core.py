"""Core MCP tools — query, ingest, compile."""

import json
import logging
import os
import re
from datetime import date
from pathlib import Path

import anthropic
import frontmatter

from kb.capture import CaptureResult, capture_items
from kb.config import (
    MAX_INGEST_CONTENT_CHARS,
    MAX_QUESTION_LEN,
    MAX_SEARCH_RESULTS,
    PROJECT_ROOT,
    QUERY_CONTEXT_MAX_CHARS,
    RAW_DIR,
    SOURCE_TYPE_DIRS,
    WIKI_DIR,
)
from kb.feedback.reliability import compute_trust_scores
from kb.ingest.pipeline import _TEXT_EXTENSIONS, ingest_source
from kb.mcp.app import (
    _format_ingest_result,
    _is_windows_reserved,
    _rel,
    _sanitize_error_str,
    _validate_wiki_dir,
    error_tag,
    mcp,
)
from kb.query.engine import query_wiki, search_pages
from kb.query.rewriter import rewrite_query
from kb.utils.io import atomic_text_write
from kb.utils.llm import LLMError
from kb.utils.pages import save_page_frontmatter
from kb.utils.text import slugify, yaml_escape, yaml_sanitize

logger = logging.getLogger(__name__)


# Cycle 4 item #2 — conversation_context sanitizer. Strips <prior_turn> /
# </prior_turn> fences (and their fullwidth and case variants) so an
# attacker-controlled `conversation_context` cannot smuggle closer fences
# that escape our wrapping sentinel and inject instructions into the
# rewriter's scan-tier LLM prompt. Also strips control characters via the
# shared `yaml_sanitize` helper.
#
# The fullwidth angle-bracket fold (U+FF1C → <, U+FF1E → >) is applied
# ONLY to the match region — we do not NFKC-normalise the whole body,
# which would corrupt legitimate content (e.g. wiki pages about Unicode
# fullwidth examples). Pattern matches:
#   <prior_turn> / </prior_turn>    (ASCII, with optional attributes + ws)
#   ＜prior_turn＞ / ＜/prior_turn＞ (fullwidth brackets)
#   <PRIOR_TURN> etc.               (any case)
_PRIOR_TURN_FENCE_RE = re.compile(
    r"[<\uFF1C]\s*/?\s*prior_turn(?:\s[^>\uFF1E]*)?\s*[>\uFF1E]",
    re.IGNORECASE,
)


def _sanitize_conversation_context(ctx: str) -> str:
    """Strip prior_turn fences + control chars from attacker-controlled context.

    Applied before wrapping the context in our own ``<prior_turn>...</prior_turn>``
    sentinel for the rewriter prompt (cycle 4 threat-model item #2).
    """
    if not ctx:
        return ctx
    # Strip fence variants (opening + closing, case-insensitive, fullwidth).
    stripped = _PRIOR_TURN_FENCE_RE.sub("", ctx)
    # Strip control characters + BIDI marks via shared helper.
    return yaml_sanitize(stripped)


def _validate_file_inputs(filename: str, content: str) -> str | None:
    """Validate filename and content size. Returns error string or None if valid."""
    if not filename or not filename.strip():
        return "Error: Filename cannot be empty."
    if len(filename) > 200:
        return "Error: Filename too long (max 200 chars)."
    if len(content) > MAX_INGEST_CONTENT_CHARS:
        return (
            f"Error: Content too large ({len(content)} chars). "
            f"Maximum: {MAX_INGEST_CONTENT_CHARS} chars."
        )
    return None


# Cycle 16 AC17-AC19 — kb_query save_as validation.
# Returns (normalized_slug, None) on success; ("", error_msg) on failure.
# MUST NOT raise (T15/C2) — callers wrap the error_msg in an MCP error string.
_SAVE_AS_ASCII_SLUG_RE = re.compile(r"[a-z0-9-]+")
_SAVE_AS_MAX_LEN = 80


def _validate_save_as_slug(slug: str) -> tuple[str, str | None]:
    """Validate a save_as slug for synthesis file creation.

    Applies belt-and-suspenders character whitelist (cycle-15 L-style pattern):
      - length cap (80 chars)
      - no whitespace padding / empty
      - no path separators / ``..`` / absolute-path indicators
      - BOTH ``slugify(slug) == slug`` AND ``re.fullmatch(r"[a-z0-9-]+", slug)``
        (Q3/C4 — slugify alone is insufficient because it preserves CJK /
        Cyrillic via ``\\w`` without ``re.ASCII``; the explicit ASCII regex
        catches homoglyphs like Cyrillic ``а`` U+0430 that slugify returns
        unchanged.)
      - rejects Windows reserved basenames (``CON``, ``PRN``, etc.)
    """
    if not isinstance(slug, str):
        return "", "Error: save_as must be a string"
    if len(slug) > _SAVE_AS_MAX_LEN:
        return "", f"Error: save_as too long (max {_SAVE_AS_MAX_LEN} chars)"
    if not slug or slug.strip() != slug:
        return "", "Error: save_as cannot be empty or whitespace-padded"
    if ".." in slug or slug.startswith("/") or "\\" in slug or os.path.isabs(slug):
        return "", "Error: save_as cannot contain path separators or .."
    # Q3/C4 — two independent checks.
    if slugify(slug) != slug:
        return "", "Error: save_as must match slug form (lowercase, hyphenated)"
    if not _SAVE_AS_ASCII_SLUG_RE.fullmatch(slug):
        return "", "Error: save_as must be ASCII lowercase alphanumeric with hyphens only"
    if _is_windows_reserved(slug):
        return "", "Error: save_as uses a Windows reserved device name"
    return slug, None


def _save_synthesis(slug: str, result: dict) -> str:
    """Persist a synthesized answer to ``wiki/synthesis/{slug}.md``.

    Cycle 16 AC17-AC19 + T1/T2/T15/C1/C2/C4.

    Returns a single-line message for appending to the tool response:
      - Success: ``\\nSaved synthesis to: <rel_path>``
      - Skipped (refusal, collision, empty source): ``\\n[info|warn] <reason>``
      - Invalid state: ``\\n[warn] save_as failed: <reason>``

    Never raises past the boundary (T15/C2).
    """
    # Refusal path — skip save; the answer is the static refusal advisory.
    if result.get("low_confidence"):
        return "\n[info] save_as skipped: low-coverage refusal (no synthesis to persist)"

    # Q1/C1 — source list MUST be non-empty to pass validate_frontmatter.
    source_list = [str(p) for p in (result.get("source_pages") or [])]
    if not source_list:
        return "\n[warn] save_as skipped: query returned no source_pages"

    try:
        synthesis_dir = WIKI_DIR / "synthesis"
        synthesis_dir.mkdir(parents=True, exist_ok=True)
        target = synthesis_dir / f"{slug}.md"
        # Belt-and-suspenders containment check (T1) — uses path-component
        # comparison, NOT string prefix. A sibling directory named
        # `synthesis_evil` would falsely pass `.startswith(str(synthesis_dir))`
        # (Step-11 R1 review finding). `is_relative_to` rejects that cleanly.
        resolved_target = target.resolve()
        resolved_base = synthesis_dir.resolve()
        try:
            contained = resolved_target.is_relative_to(resolved_base)
        except ValueError:
            contained = False
        if not contained:
            return "\n[warn] save_as skipped: target escapes synthesis directory"
        if target.exists():
            return f"\n[warn] save_as skipped: target already exists ({_rel(target)})"

        answer_text = result.get("answer") or ""
        today = date.today().isoformat()
        post = frontmatter.Post(
            answer_text,
            title=slug.replace("-", " ").title(),
            source=source_list,
            created=today,
            updated=today,
            type="synthesis",
            confidence="inferred",
            authored_by="llm",
        )
        save_page_frontmatter(target, post)
        return f"\nSaved synthesis to: {_rel(target)}"
    except OSError as exc:
        logger.warning("save_as write failed for slug=%r: %s", slug, exc)
        return f"\n[warn] save_as failed: {_sanitize_error_str(exc)}"


@mcp.tool()
def kb_query(
    question: str,
    max_results: int = 10,
    use_api: bool = False,
    conversation_context: str = "",
    output_format: str = "",
    save_as: str = "",
) -> str:
    """Query the knowledge base.

    Default (Claude Code mode): returns wiki search results with full page
    content. You (Claude Code) synthesize the answer and cite sources with
    [[page_id]] format.

    With use_api=true: calls the Anthropic API to synthesize the answer
    (requires ANTHROPIC_API_KEY).

    With output_format set (requires use_api=true): renders the synthesized
    answer to a file under outputs/ in one of: markdown, marp, html, chart,
    jupyter. Returns "Output written to: <path>" appended to the normal reply.

    NOTE (cycle 16 semantic shift): when ``save_as`` is non-empty, this tool
    performs a filesystem write to ``wiki/synthesis/{slug}.md`` — it becomes
    a write, not a read. Frontmatter is hardcoded (``type=synthesis``,
    ``confidence=inferred``, ``authored_by=llm``); ``source`` is derived
    from the query's ``source_pages`` list. Requires ``use_api=true`` so
    an actual synthesis exists to persist. Refusal (low-coverage) path
    skips the save.

    Args:
        question: Natural language question.
        max_results: Maximum pages to search (default 10).
        use_api: If true, call the Anthropic API for synthesis. Default false.
        conversation_context: Recent conversation history for follow-up query rewriting.
        output_format: One of markdown|marp|html|chart|jupyter to produce a file,
                       or empty/text for stdout-only response. Requires use_api=true.
        save_as: Optional slug to persist the synthesized answer to
                 ``wiki/synthesis/{slug}.md``. Requires ``use_api=true``.
                 Must match ``[a-z0-9-]+``; traversal / Unicode / Windows
                 reserved names rejected with error strings.
    """
    if not question or not question.strip():
        return "Error: Question cannot be empty."
    if len(question) > MAX_QUESTION_LEN:
        return f"Error: Question too long (max {MAX_QUESTION_LEN} chars)."
    if conversation_context and len(conversation_context) > MAX_QUESTION_LEN * 4:
        return f"Error: conversation_context too long (max {MAX_QUESTION_LEN * 4} chars)."
    # Cycle 4 item #2 — sanitise BEFORE use in either MCP branch so fence
    # injections never reach the rewriter LLM prompt.
    if conversation_context:
        conversation_context = _sanitize_conversation_context(conversation_context)

    # Validate output_format at MCP boundary (normalize case/whitespace)
    fmt_n = (output_format or "").strip().lower()
    if fmt_n and fmt_n != "text":
        from kb.query.formats import VALID_FORMATS

        if fmt_n not in VALID_FORMATS:
            return f"Error: unknown output_format '{output_format}'. Valid: {sorted(VALID_FORMATS)}"
        if not use_api:
            return (
                "Error: output_format requires use_api=true "
                "(default Claude Code mode returns raw context, "
                "not a synthesized answer)."
            )

    max_results = max(1, min(max_results, MAX_SEARCH_RESULTS))

    # Cycle 16 AC17-AC19 — validate save_as early so invalid input never
    # reaches query_wiki. Any save_as usage requires use_api=True so there
    # is an actual synthesised answer to persist.
    save_slug: str | None = None
    if save_as:
        if not use_api:
            return "Error: save_as requires use_api=true (synthesis needed)"
        slug, error = _validate_save_as_slug(save_as)
        if error:
            return error
        save_slug = slug

    if use_api:
        from kb.query.citations import format_citations

        try:
            result = query_wiki(
                question,
                max_results=max_results,
                conversation_context=conversation_context or None,
                output_format=fmt_n or None,
            )
            parts = [result["answer"]]
            if result.get("citations"):
                parts.append("\n" + format_citations(result["citations"]))
            parts.append(f"\n[Searched {len(result.get('source_pages', []))} pages]")
            if result.get("output_path"):
                parts.append(
                    f"\nOutput written to: {result['output_path']} ({result['output_format']})"
                )
            if result.get("output_error"):
                parts.append(f"\n[warn] Output format failed: {result['output_error']}")

            # Cycle 16 R3 NIT 2 — surface rephrasings on low-coverage refusal
            # path so MCP callers see the scan-tier suggestions instead of
            # having them silently swallowed by the response builder.
            rephrasings = result.get("rephrasings") or []
            if rephrasings:
                parts.append("\nSuggested rephrasings:")
                for r in rephrasings:
                    parts.append(f"  - {r}")

            # Cycle 16 AC17-AC19 — persist synthesis to wiki/synthesis/.
            if save_slug is not None:
                saved_msg = _save_synthesis(save_slug, result)
                if saved_msg:
                    parts.append(saved_msg)
            return "\n".join(parts)
        except anthropic.BadRequestError as e:
            logger.warning("kb_query API bad-request for %r: %s", question[:80], e)
            if "too long" in str(e).lower() or "context" in str(e).lower():
                return error_tag("prompt_too_long", _sanitize_error_str(e))
            return error_tag("invalid_input", _sanitize_error_str(e))
        except anthropic.RateLimitError as e:
            logger.warning("kb_query API rate-limited for %r: %s", question[:80], e)
            return error_tag("rate_limit", _sanitize_error_str(e))
        except LLMError as e:
            logger.error("kb_query API LLM failure for %r: %s", question[:80], e)
            return error_tag("internal", f"LLM call failed: {_sanitize_error_str(e)}")
        except Exception as e:
            logger.exception("kb_query API unexpected error for: %s", question)
            return error_tag("internal", f"unexpected error: {_sanitize_error_str(e)}")

    # Default: Claude Code mode — return context for synthesis
    # H18: apply multi-turn query rewriting when conversation context is present
    if conversation_context:
        question = rewrite_query(question, conversation_context)

    try:
        results = search_pages(question, max_results=max_results)
    except Exception as e:
        logger.exception("Error in kb_query search for: %s", question)
        return f"Error: Search failed — {_sanitize_error_str(e)}"

    if not results:
        return (
            "No relevant wiki pages found for this question. "
            "The knowledge base may not have content on this topic yet."
        )

    # Merge trust scores from feedback (fail-safe)
    pages_with_feedback: set[str] = set()
    try:
        scores = compute_trust_scores()
        pages_with_feedback = set(scores.keys())
        for r in results:
            trust_data = scores.get(r["id"], {})
            r["trust"] = trust_data.get("trust", 0.5)
    except Exception as e:
        logger.debug("Trust score merge failed: %s", e, exc_info=True)
        for r in results:
            r["trust"] = 0.5

    lines = [
        f"# Query Context for: {question}\n",
        f"Found {len(results)} relevant page(s). "
        "Synthesize an answer using this context. "
        "Cite sources with [[page_id]] format.\n",
    ]
    for r in results:
        trust = r.get("trust") or 0.5
        trust_label = f", trust: {trust:.2f}" if r["id"] in pages_with_feedback else ""
        stale_label = " [STALE]" if r.get("stale") else ""
        lines.append(
            f"--- Page: {r['id']} (type: {r['type']}, "
            f"confidence: {r['confidence']}, score: {r['score']}{trust_label}){stale_label} ---\n"
            f"Title: {r['title']}\n\n{r['content']}\n"
        )
    return "\n".join(lines)


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

    # ── API mode ──
    if use_api:
        try:
            result = ingest_source(path, source_type or None)
            return _format_ingest_result(
                _rel(Path(result["source_path"])),
                result["source_type"],
                result["content_hash"],
                result,
            )
        except Exception as e:
            logger.exception("Error ingesting %s (API mode)", source_path)
            return f"Error ingesting source: {_sanitize_error_str(e, path)}"

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
            result = ingest_source(path, source_type, extraction=extraction)
            return _format_ingest_result(
                _rel(path), result["source_type"], result["content_hash"], result
            )
        except Exception as e:
            logger.exception("Error ingesting %s", source_path)
            return f"Error ingesting source: {_sanitize_error_str(e, path)}"

    # ── Claude Code mode: without extraction → return prompt ──
    from kb.ingest.extractors import build_extraction_prompt, load_template

    try:
        template = load_template(source_type)
    except FileNotFoundError as e:
        return f"Error: {_sanitize_error_str(e)}"

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return f"Error reading source file: {_sanitize_error_str(e, path)}"

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
        logger.warning(
            "kb_ingest_content partial write to %s: %s; client must retry",
            _rel(file_path),
            write_err,
        )
        return (
            f"Error[partial]: write to {_rel(file_path)} failed ({write_err}); "
            "retry with kb_save_source(..., overwrite=true) then kb_ingest."
        )

    try:
        # Cycle 6 AC1 — when use_api=True, ``extraction`` is None so
        # ingest_source falls through to its LLM extraction path. Claude
        # Code mode stays default (explicit extraction dict).
        if extraction is None:
            result = ingest_source(file_path, source_type)
        else:
            result = ingest_source(file_path, source_type, extraction=extraction)
    except Exception as e:
        # Clean up orphaned file before returning error
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass
        logger.exception("Error ingesting %s after write", filename)
        return f"Error: Ingest failed — {_sanitize_error_str(e, file_path)}"

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
            return f"Error: Failed to write source file: {_sanitize_error_str(e, file_path)}"
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
            logger.warning(
                "kb_save_source partial write to %s: %s; client must retry",
                _rel(file_path),
                write_err,
            )
            return (
                f"Error[partial]: write to {_rel(file_path)} failed ({write_err}); "
                "retry with overwrite=true."
            )
    return (
        f"Saved: {_rel(file_path)} ({len(content)} chars)\n"
        f'To ingest: kb_ingest("{_rel(file_path)}", "{yaml_escape(source_type)}")'
    )


@mcp.tool()
def kb_compile_scan(incremental: bool = True, wiki_dir: str | None = None) -> str:
    """Scan for new/changed raw sources that need ingestion.

    Returns source files to process. For each, call kb_ingest with extraction_json.
    Note: each call also writes current template hashes to the hash manifest.

    Args:
        incremental: If True (default), only new/changed sources. If False, all.
        wiki_dir: Optional wiki directory override. When provided, raw sources
            and the hash manifest are resolved from the same project root.
    """
    try:
        from kb.compile.compiler import find_changed_sources, scan_raw_sources
    except Exception as e:
        return f"Error loading compile module: {_sanitize_error_str(e)}"

    try:
        wiki_path, err = _validate_wiki_dir(wiki_dir)
        if err:
            return f"Error: {err}"
        raw_dir = wiki_path.parent / "raw" if wiki_path else None
        manifest_path = wiki_path.parent / ".data" / "hashes.json" if wiki_path else None
        if incremental:
            # save_hashes=True (default): marks templates as seen so repeated calls
            # to kb_compile_scan de-duplicate work between invocations.
            new_sources, changed_sources = find_changed_sources(
                raw_dir=raw_dir, manifest_path=manifest_path
            )
            if not new_sources and not changed_sources:
                return "No new or changed sources found. Wiki is up to date."

            lines = ["# Compile Scan (incremental)\n"]
            if new_sources:
                lines.append(f"## New sources ({len(new_sources)})\n")
                for s in new_sources:
                    lines.append(f"- {_rel(s)}")
            if changed_sources:
                lines.append(f"\n## Changed sources ({len(changed_sources)})\n")
                for s in changed_sources:
                    lines.append(f"- {_rel(s)}")

            total = len(new_sources) + len(changed_sources)
            lines.append(
                f"\n**Total: {total} source(s) to process.** "
                "For each: call kb_ingest(source_path) to get the extraction prompt, "
                "then call kb_ingest(source_path, extraction_json=...) with your extraction."
            )
        else:
            all_sources = scan_raw_sources(raw_dir=raw_dir)
            if not all_sources:
                return "No source files found in raw/."
            lines = [
                "# Compile Scan (full)\n",
                f"**Total: {len(all_sources)} source(s)**\n",
            ]
            for s in all_sources:
                lines.append(f"- {_rel(s)}")
            lines.append(
                "\nFor each: call kb_ingest(source_path) to get the extraction prompt, "
                "then call kb_ingest(source_path, extraction_json=...) with your extraction."
            )
    except Exception as e:
        return f"Error scanning sources: {_sanitize_error_str(e)}"

    return "\n".join(lines)


@mcp.tool()
def kb_compile(incremental: bool = True) -> str:
    """Compile wiki pages from raw sources.

    In incremental mode, only processes new and changed sources.
    In full mode, recompiles everything.

    Note: Each source requires LLM extraction (ANTHROPIC_API_KEY needed).
    For Claude Code mode, use kb_compile_scan() to get the list, then
    kb_ingest() each source with your own extraction.

    Args:
        incremental: If True (default), only new/changed sources. If False, all.
    """
    try:
        from kb.compile.compiler import compile_wiki

        result = compile_wiki(incremental=incremental)
    except Exception as e:
        logger.exception("Error running compile")
        return f"Error running compile: {_sanitize_error_str(e)}"

    mode = result["mode"]
    lines = [
        f"# Compile Complete ({mode})\n",
        f"**Sources processed:** {result['sources_processed']}",
        f"**Pages created:** {len(result['pages_created'])}",
        f"**Pages updated:** {len(result['pages_updated'])}",
    ]
    if result["pages_created"]:
        lines.append("\n## Created")
        for p in result["pages_created"]:
            lines.append(f"  + {p}")
    if result["pages_updated"]:
        lines.append("\n## Updated")
        for p in result["pages_updated"]:
            lines.append(f"  ~ {p}")
    if result.get("pages_skipped"):
        lines.append(f"\n## Skipped ({len(result['pages_skipped'])})")
        for p in result["pages_skipped"]:
            lines.append(f"  ! {p}")
    if result.get("wikilinks_injected"):
        lines.append(f"\n## Wikilinks Injected ({len(result['wikilinks_injected'])})")
        for p in result["wikilinks_injected"]:
            lines.append(f"  -> {p}")
    if result.get("duplicates"):
        lines.append(f"\n**Duplicates skipped:** {result['duplicates']}")
    if result["errors"]:
        lines.append(f"\n## Errors ({len(result['errors'])})")
        for err in result["errors"]:
            lines.append(f"  ! {err['source']}: {err['error']}")
    return "\n".join(lines)


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
    try:
        result = capture_items(content, provenance=provenance)
    except Exception as e:
        return f"Error: {type(e).__name__}: {_sanitize_error_str(e)}"
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
