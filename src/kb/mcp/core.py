"""Core MCP tools — query, ingest, compile.

Cycle 17 AC4 (narrowed): `kb.capture` remains the only direct deferral at
module level — it is NOT transitively loaded via any other kb.mcp.core import
chain and has no test monkeypatches on `kb.mcp.core.capture_items`. Function-
body imports for `anthropic`, `frontmatter`, `kb.utils.pages.save_page_frontmatter`,
and `kb.utils.llm.LLMError` remain inside tool bodies — these never had
test monkeypatches on `kb.mcp.core.*`.

Cycle 19 AC15 — owner-module-attribute call style for the four migrated callables
(`ingest_source`, `query_wiki`, `search_pages`, `compute_trust_scores`). The
imports now bring in the OWNER MODULES (`kb.ingest.pipeline as ingest_pipeline`,
`kb.query.engine as query_engine`, `kb.feedback.reliability as reliability`)
and the call sites use ``ingest_pipeline.ingest_source(...)`` /
``query_engine.query_wiki(...)`` / etc. This means tests should monkeypatch
the OWNER module attribute (e.g. ``patch("kb.ingest.pipeline.ingest_source")``);
the MCP tool's call resolves the patched attribute at call time, not at import
time. See `tests/test_cycle19_mcp_monkeypatch_migration.py` for the four
vacuity tests that pin this contract.

Cycle 19 AC16 — snapshot-binding asymmetry for CONSTANTS. Constants
(`PROJECT_ROOT`, `RAW_DIR`, `SOURCE_TYPE_DIRS`) are imported via
``from kb.config import X`` at module scope, which creates a snapshot binding.
Tests patching ``kb.config.X`` post-import will NOT propagate to
``kb.mcp.core.X`` because the local name still references the snapshot value.
For constants the tests MUST use ``monkeypatch.setattr("kb.mcp.core.X", ...)``
directly. The asymmetry is intentional: callables go through one extra
attribute lookup at call time (negligible cost — see R2 N2 in
`docs/superpowers/decisions/2026-04-21-cycle19-design.md`); constants are
hot-path values that the import-time snapshot caches for free.

Tests: tests/test_cycle17_lazy_imports.py enforces the `kb.capture` denylist;
tests/test_cycle19_mcp_monkeypatch_migration.py enforces the AC15 / AC16
owner-module patch contract.
"""

import logging
import os
import re
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Reserved for future cycle-17 AC4 re-try. Cycle 17 kept kb.capture at
    # module level because its import-time CAPTURES_DIR security check
    # must run under the REAL PROJECT_ROOT (before any test monkeypatch of
    # kb.config.CAPTURES_DIR redirects it to a tmp path). A dedicated cycle
    # needs to move the security check to runtime or provide a dev-only
    # opt-out before this can be lazy.
    pass

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
from kb.mcp.app import (
    _format_ingest_result,
    _is_windows_reserved,
    _rel,
    _validate_wiki_dir,
    error_tag,
    mcp,
)
from kb.query.rewriter import rewrite_query
from kb.utils.io import atomic_text_write
from kb.utils.sanitize import sanitize_error_text
from kb.utils.text import slugify, yaml_escape, yaml_sanitize

_INGEST_COMPAT_BINDINGS = (
    MAX_INGEST_CONTENT_CHARS,
    PROJECT_ROOT,
    QUERY_CONTEXT_MAX_CHARS,
    RAW_DIR,
    SOURCE_TYPE_DIRS,
    _format_ingest_result,
    atomic_text_write,
    yaml_escape,
    _validate_wiki_dir,
)

# Cycle 17 AC4 (narrowed): `anthropic` and `frontmatter` stay deferred to tool
# bodies even though they leak transitively — the direct deferral removes them
# from kb.mcp.core's self-reported import surface. `kb.utils.pages.save_page_frontmatter`
# and `kb.utils.llm.LLMError` also stay inside tool bodies (no test monkeypatch).

# Cycle 23 AC4 — PEP 562 module-level lazy-shim for heavy owner modules.
# Keeps ``kb.mcp.core.<name>`` reachable as an attribute (preserves the
# cycle-19 AC15 monkeypatch contract: ``monkeypatch.setattr(mcp_core.ingest_pipeline, ...)``)
# while deferring ``anthropic``/``networkx``/``sentence-transformers`` loads
# until the first MCP tool that actually needs them runs. Boot-time probes
# assert absence via ``tests/test_cycle23_mcp_boot_lean.py``.
#
# Closed allowlist — names NOT in this dict raise AttributeError through
# ``__getattr__`` rather than falling through to arbitrary ``importlib``
# lookups (threat I3 — closed allowlist for attacker-controlled names).
_LAZY_MODULES: dict[str, str] = {
    "ingest_pipeline": "kb.ingest.pipeline",
    "query_engine": "kb.query.engine",
    "reliability": "kb.feedback.reliability",
}

# MCP-only whitelist — previously in ``kb.ingest.pipeline`` but importing
# even a single constant from there forced the whole pipeline module (and
# anthropic transitively) to load. Relocated cycle-23 AC4 to a local
# ``frozenset`` so bare ``import kb.mcp`` stays lean.
_TEXT_EXTENSIONS = frozenset({".md", ".txt", ".rst", ".csv", ".json", ".yaml", ".yml"})


def __getattr__(name: str):
    """PEP 562 lazy loader for the heavy owner modules.

    The cached ``globals()[name] = module`` write is idempotent — Python's
    import system returns the same module object across concurrent calls, so
    even if two threads race through this function they write the same value.
    No explicit lock required (cycle-6 L2 converse: locks prevent duplicate
    construction; here construction is already idempotent).
    """
    module_path = _LAZY_MODULES.get(name)
    if module_path is None:
        raise AttributeError(f"module 'kb.mcp.core' has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_path)
    globals()[name] = module
    return module


def __dir__():
    return sorted(set(list(globals())) | set(_LAZY_MODULES))


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

    # Cycle 33 R1 Codex MAJOR A1 + R2 Codex C33-R2-01 — assign `target` BEFORE
    # the try block (NOT just before mkdir). The `except OSError as exc:`
    # handler references `target` for path-redaction; if any operation INSIDE
    # the try raises OSError before `target` is bound — including the lazy
    # imports of `frontmatter` / `save_page_frontmatter` (R2 reproduced via
    # forced OSError on import) OR the mkdir call (R1 original finding) — the
    # handler would raise UnboundLocalError and bypass the AC4 contract.
    # `Path / str` arithmetic is pure object construction and cannot fail, so
    # both bindings are safe to live above the try.
    synthesis_dir = WIKI_DIR / "synthesis"
    target = synthesis_dir / f"{slug}.md"

    try:
        # Cycle 17 AC4 — lazy imports keep cold-boot out of frontmatter.
        import frontmatter

        from kb.utils.pages import save_page_frontmatter

        synthesis_dir.mkdir(parents=True, exist_ok=True)
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
        # Cycle 33 AC4 — pass `target` to both log AND return so the exception's
        # filename attribute is path-redacted (not just regex-swept). Symmetric
        # depth match for kb_ingest_content / kb_save_source AC1+AC2 fixes.
        sanitized_err = sanitize_error_text(exc, target)
        logger.warning("save_as write failed for slug=%r: %s", slug, sanitized_err)
        return f"\n[warn] save_as failed: {sanitized_err}"


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

    # Cycle 23 AC4 — function-local bindings to PEP-562 lazy-shim targets so
    # bare ``query_engine.X`` / ``reliability.X`` resolve under function scope.
    # The cycle-19 AC15 contract is preserved: test patches on
    # ``kb.query.engine.*`` / ``kb.feedback.reliability.*`` intercept these
    # call sites because the local binding resolves to the same cached module.
    from kb.feedback import reliability
    from kb.query import engine as query_engine

    if use_api:
        # Cycle 17 AC4 — lazy import keeps cold-boot out of anthropic.
        import anthropic

        from kb.query.citations import format_citations
        from kb.utils.llm import LLMError

        try:
            # Cycle 19 AC15 — owner-module attribute call so tests patching
            # ``kb.query.engine.query_wiki`` intercept this call site.
            result = query_engine.query_wiki(
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
                return error_tag("prompt_too_long", sanitize_error_text(e))
            return error_tag("invalid_input", sanitize_error_text(e))
        except anthropic.RateLimitError as e:
            logger.warning("kb_query API rate-limited for %r: %s", question[:80], e)
            return error_tag("rate_limit", sanitize_error_text(e))
        except LLMError as e:
            logger.error("kb_query API LLM failure for %r: %s", question[:80], e)
            return error_tag("internal", f"LLM call failed: {sanitize_error_text(e)}")
        except Exception as e:
            logger.exception("kb_query API unexpected error for: %s", question)
            return error_tag("internal", f"unexpected error: {sanitize_error_text(e)}")

    # Default: Claude Code mode — return context for synthesis.
    # H18: apply multi-turn query rewriting when conversation context is present
    if conversation_context:
        question = rewrite_query(question, conversation_context)

    try:
        # Cycle 19 AC15 — owner-module attribute call so tests patching
        # ``kb.query.engine.search_pages`` intercept this call site.
        results = query_engine.search_pages(question, max_results=max_results)
    except Exception as e:
        logger.exception("Error in kb_query search for: %s", question)
        return f"Error: Search failed — {sanitize_error_text(e)}"

    if not results:
        return (
            "No relevant wiki pages found for this question. "
            "The knowledge base may not have content on this topic yet."
        )

    # Merge trust scores from feedback (fail-safe)
    pages_with_feedback: set[str] = set()
    try:
        # Cycle 19 AC15 — owner-module attribute call so tests patching
        # ``kb.feedback.reliability.compute_trust_scores`` intercept this site.
        scores = reliability.compute_trust_scores()
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

from kb.mcp.compile import (  # noqa: E402, F401  # re-exported for backward compat (cycle-23 L5)
    kb_compile,
    kb_compile_scan,
)
from kb.mcp.ingest import (  # noqa: E402, F401  # re-exported for backward compat (cycle-23 L5)
    _FILENAME_MAX_LEN,
    _FILENAME_NON_ASCII_RE,
    _format_capture_result,
    _validate_file_inputs,
    _validate_filename_slug,
    kb_capture,
    kb_ingest,
    kb_ingest_content,
    kb_save_source,
)

