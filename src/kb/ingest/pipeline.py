"""Ingest pipeline — read raw sources, create wiki summaries, update indexes."""

import json
import logging
import os
import re
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import frontmatter
import yaml

from kb.config import (
    MAX_CONCEPTS_PER_INGEST,
    MAX_ENTITIES_PER_INGEST,
    PROJECT_ROOT,
    RAW_DIR,
    SMALL_SOURCE_THRESHOLD,
    SOURCE_TYPE_DIRS,
    SUPPORTED_SOURCE_EXTENSIONS,
    WIKI_DIR,
    WIKI_INDEX,
    WIKI_SOURCES,
    WIKI_SUBDIR_TO_TYPE,
)
from kb.errors import IngestError, KBError, StorageError, ValidationError
from kb.ingest.contradiction import (
    detect_contradictions_with_metadata,
)
from kb.ingest.evidence import append_evidence_trail
from kb.ingest.extractors import extract_from_source
from kb.utils.hashing import hash_bytes
from kb.utils.io import atomic_text_write, file_lock
from kb.utils.pages import load_all_pages, normalize_sources
from kb.utils.paths import make_source_ref
from kb.utils.sanitize import sanitize_text
from kb.utils.text import sanitize_extraction_field, slugify, wikilink_display_escape, yaml_escape
from kb.utils.wiki_log import (
    LOG_SIZE_WARNING_BYTES,
    append_wiki_log,
    rotate_if_oversized,
)

logger = logging.getLogger(__name__)

# Fix 2.3 (module-level): compiled once, reused in every _update_existing_page call.
# Uses [ \t]* (zero or more) to handle both indented (2/4-space) and PyYAML-dumped
# zero-indent list items. PyYAML normalises "  - item" to "- item" when round-tripping
# through frontmatter.dumps(), so requiring [ \t]+ would miss those entries and
# produce malformed YAML (mixed-indent source block).
_SOURCE_BLOCK_RE = re.compile(r"^(source:\s*\n(?:[ \t]*- [^\n]*\n)*)", re.MULTILINE)

# Adversarial-review fix (BLOCKER): tighter sentinel pattern — matches ONLY the
# untitled-<6 hex chars> fallback emitted by slugify() for pure-symbol/emoji input.
# The old startswith("untitled-") guard was a false positive for legitimate entity
# names like "Untitled-Reports" (slug "untitled-reports"). Exact 6-hex suffix ensures
# only the computed hash sentinel is suppressed.
_UNTITLED_SENTINEL_RE = re.compile(r"^untitled-[0-9a-f]{6}$")

_SUMMARY_STRING_FIELDS = (
    "title",
    "name",
    "author",
    "speaker",
    "core_argument",
    "abstract",
    "description",
    "problem_solved",
)


def _coerce_str_field(extraction: dict, field: str) -> str:
    """Return a string extraction field or fail fast on malformed values."""
    value = extraction.get(field)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    raise ValueError(f"extraction field {field!r} must be string, got {type(value).__name__}")


def _pre_validate_extraction(extraction: dict) -> None:
    """Validate string fields consumed by summary rendering before reservation."""
    for field in _SUMMARY_STRING_FIELDS:
        _coerce_str_field(extraction, field)


def _is_untitled_sentinel(slug: str) -> bool:
    """Return True iff slug matches the untitled-<hash6> fallback from slugify()."""
    return bool(_UNTITLED_SENTINEL_RE.fullmatch(slug))


def _find_affected_pages(
    page_ids: list[str],
    wiki_dir: Path | None = None,
    pages: list[dict] | None = None,
) -> list[str]:
    """Find existing pages affected by newly created/updated pages.

    Checks backlinks (pages that link to the new pages) and shared sources.
    Returns a deduplicated, sorted list of affected page IDs.

    Args:
        page_ids: Page IDs of newly created/updated pages.
        wiki_dir: Wiki directory (uses config default if None).
        pages: Pre-loaded list of all wiki pages. If None, loads from disk.
    """
    if not page_ids:
        return []

    page_id_set = set(page_ids)
    affected: set[str] = set()
    # Cycle 7 AC8: thread pre-loaded pages into build_backlinks so callers
    # that already walked wiki/ don't pay a second scan.
    all_pages = pages if pages is not None else None
    try:
        from kb.compile.linker import build_backlinks

        if all_pages is None:
            all_pages = load_all_pages(wiki_dir)
        backlinks_map = build_backlinks(wiki_dir, pages=all_pages)
        for pid in page_ids:
            for linker in backlinks_map.get(pid, []):
                if linker not in page_id_set:
                    affected.add(linker)
    except Exception as e:
        logger.debug("Failed to compute backlinks for cascade: %s", e)

    try:
        if all_pages is None:
            all_pages = load_all_pages(wiki_dir)
        new_sources: set[str] = set()
        for page in all_pages:
            if page["id"] in page_id_set:
                new_sources.update(page["sources"])

        if new_sources:
            for page in all_pages:
                if page["id"] not in page_id_set and set(page["sources"]) & new_sources:
                    affected.add(page["id"])
    except Exception as e:
        logger.debug("Failed to compute shared sources for cascade: %s", e)

    return sorted(affected)


def _sort_new_pages_by_title_length(
    pairs: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Sort ``(page_id, title)`` pairs descending by title length (tie-break on page_id).

    Cycle 4 item #29: longer titles must inject wikilinks FIRST so a shorter
    overlap like ``RAG`` does not swallow body text that ``Retrieval-Augmented
    Generation`` should own. Extracted as a helper so the ordering contract
    is directly unit-testable (PR R1 Sonnet MAJOR 1).
    """
    return sorted(pairs, key=lambda pt: (-len(pt[1]), pt[0]))


def _emit_contradiction_telemetry(
    metadata: dict,
    source_ref: str,
    logger_: "logging.Logger",
) -> list[dict]:
    """Return ``metadata["contradictions"]`` and emit truncation warning when flagged.

    Cycle 4 item #22 + PR R1 Sonnet MAJOR 2 — extracted from ``ingest_source``
    so the migration contract (truncation produces a WARNING; contradictions
    list is surfaced) is directly unit-testable without a full ingest setup.
    """
    contradictions = metadata.get("contradictions", []) or []
    if metadata.get("truncated"):
        logger_.warning(
            "Contradiction detection truncated for %s: checked %d of %d claims",
            source_ref,
            metadata.get("claims_checked", 0),
            metadata.get("claims_total", 0),
        )
    return contradictions


def _persist_contradictions(
    contradictions: list[dict],
    source_ref: str,
    effective_wiki_dir: Path,
) -> None:
    """Append contradiction warnings to wiki/contradictions.md (file-locked).

    H3 fix (Phase 4.5 HIGH): wraps read→append→write in file_lock(contradictions_path)
    so concurrent ingests on the same wiki don't overwrite each other's blocks.
    """
    contradictions_path = effective_wiki_dir / "contradictions.md"
    header = "# Contradictions\n\nAppend-only log of conflicts detected during ingest.\n\n"
    try:
        with file_lock(contradictions_path):
            existing = (
                contradictions_path.read_text(encoding="utf-8")
                if contradictions_path.exists()
                else header
            )
            # H13 fix: take only the FIRST line of source_ref (everything after the first
            # \n is attacker-controlled injection). Then strip leading # characters and
            # surrounding whitespace to prevent header injection.
            first_line = source_ref.split("\n")[0].split("\r")[0]
            safe_ref = first_line.strip().lstrip("#").strip()
            block = f"\n## {safe_ref} — {date.today().isoformat()}\n"
            for w in contradictions:
                raw_claim = w.get("claim", str(w)) if isinstance(w, dict) else str(w)
                claim = sanitize_extraction_field(raw_claim)
                block += f"- {claim}\n"
            if existing.find(block) != -1:
                logger.debug(
                    "Skipping duplicate contradiction block for %s on %s",
                    safe_ref,
                    date.today().isoformat(),
                )
                return
            atomic_text_write(existing + block, contradictions_path)
    except Exception as write_err:
        logger.warning("Failed to write contradictions.md: %s", write_err)


def _is_duplicate_content(source_hash: str, source_ref: str) -> bool:
    """Check if a source with this content hash was already ingested.

    Compares against the compile manifest to detect duplicate content
    from different file paths. Skips template entries. Only flags as
    duplicate if the other source file still exists on disk.

    DEPRECATED path: direct callers should use _check_and_reserve_manifest instead
    so the duplicate check + reservation are atomic. Kept for backward compatibility
    with tests that call this function directly.
    """
    try:
        # Lazy import: kb.compile.compiler imports kb.ingest.pipeline (circular)
        from kb.compile.compiler import load_manifest

        manifest = load_manifest()
        for ref, stored_hash in manifest.items():
            if ref.startswith("_template/"):
                continue
            if stored_hash == source_hash and ref != source_ref:
                # Verify the other source still exists (avoid stale manifest entries)
                other_path = PROJECT_ROOT / ref
                if other_path.exists():
                    return True
    except Exception as e:
        logger.debug("Duplicate check skipped: %s", e)
    return False


def _check_and_reserve_manifest(
    source_hash: str,
    source_ref: str,
    manifest_path: "Path | None" = None,
) -> bool:
    """Q_A fix (Phase 4.5 HIGH): Atomic duplicate check + manifest reservation.

    Acquires file_lock(manifest_path) once, checks for duplicate hash, and if
    not a duplicate, reserves the slot (manifest[source_ref] = source_hash) before
    releasing the lock. This prevents the RMW race where two concurrent ingests of
    the same content both pass the duplicate check and both write pages.

    Returns True if the content is a duplicate (caller should return early).
    Returns False if not a duplicate; the reservation has been written to manifest.
    """
    try:
        from kb.compile.compiler import HASH_MANIFEST, load_manifest, save_manifest

        effective_manifest_path = manifest_path or HASH_MANIFEST
        with file_lock(effective_manifest_path):
            manifest = load_manifest(effective_manifest_path)
            for ref, stored_hash in manifest.items():
                if ref.startswith("_template/"):
                    continue
                if stored_hash == source_hash and ref != source_ref:
                    other_path = PROJECT_ROOT / ref
                    if other_path.exists():
                        return True  # Duplicate detected — caller returns early
            # Not a duplicate — reserve the slot atomically
            manifest[source_ref] = source_hash
            save_manifest(manifest, effective_manifest_path)
    except Exception as e:
        logger.debug("Duplicate check/reservation skipped: %s", e)
    return False


def detect_source_type(source_path: Path, raw_dir: Path | None = None) -> str:
    """Auto-detect source type from the raw/ subdirectory path."""
    effective_raw = (raw_dir or RAW_DIR).resolve()
    rel = source_path.resolve().relative_to(effective_raw)
    first_part = rel.parts[0] if rel.parts else ""
    if first_part == "assets":
        raise ValueError(
            "raw/assets/ files are not ingestable — assets are referenced by other sources"
        )
    # Map plural directory names to singular source types
    type_map = {v.name: k for k, v in SOURCE_TYPE_DIRS.items()}
    if first_part in type_map:
        return type_map[first_part]
    raise ValueError(f"Cannot detect source type from path: {source_path}")


def _write_wiki_page(
    page_path: Path | None = None,
    title: str = "",
    page_type: str = "",
    source_ref: str = "",
    confidence: str = "",
    content: str = "",
    path: Path | None = None,
    *,
    exclusive: bool = False,
) -> None:
    """Write a wiki page with proper YAML frontmatter.

    Cycle 7 AC29: migrated from hand-rolled f-string YAML to
    ``frontmatter.Post`` + ``frontmatter.dumps()``. YAML-escaping is now the
    library's responsibility, eliminating the residual risk in ``yaml_escape``
    for titles containing YAML-special characters.

    Accepts either ``page_path=`` or ``path=`` for backward compatibility
    with existing callers; ``page_path`` is preferred.

    Cycle 20 AC8: when ``exclusive=True``, uses ``os.open(O_CREAT|O_EXCL)`` to
    atomically reserve the target path — preventing the slug-collision
    last-writer-wins race HIGH #16 identified. On ``FileExistsError`` raises
    ``kb.errors.StorageError(kind="summary_collision", path=...)`` so the
    caller can pivot to ``_update_existing_page`` for merge semantics. On
    POSIX systems the ``O_NOFOLLOW`` flag is added if available to defeat
    symlink-target swap; Windows ``CreateFileW(CREATE_NEW)`` refuses existing
    reparse points by default. Default ``exclusive=False`` preserves the
    legacy byte-identical ``atomic_text_write`` behaviour.

    Note: ``append_evidence_trail`` is called AFTER the write in both branches;
    it acquires its own ``file_lock(page_path)`` internally, so callers MUST
    NOT wrap the ``_write_wiki_page`` call in ``file_lock(page_path)`` — the
    non-re-entrant sidecar lock would self-deadlock on the nested acquire.
    """
    import frontmatter  # noqa: PLC0415 — library-boundary import

    effective_path = page_path if page_path is not None else path
    if effective_path is None:
        raise ValueError("_write_wiki_page requires page_path (or path)")
    today = date.today().isoformat()
    post = frontmatter.Post(
        content,
        title=title,
        source=[source_ref],
        created=today,
        updated=today,
        type=page_type,
        confidence=confidence,
    )
    # PR #21 R1 Codex MAJOR 3: sort_keys=False preserves insertion order.
    rendered = frontmatter.dumps(post, sort_keys=False) + "\n"
    if exclusive:
        # Cycle 20 AC8 — atomic reserve-or-fail via O_EXCL.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            # POSIX symlink-swap hardening. Windows CPython does not define
            # O_NOFOLLOW; the default CreateFileW path refuses reparse points.
            flags |= os.O_NOFOLLOW  # pragma: no cover — branched in Task 3 tests
        try:
            fd = os.open(str(effective_path), flags, 0o644)
        except FileExistsError as e:
            raise StorageError(
                "summary_collision",
                kind="summary_collision",
                path=effective_path,
            ) from e
        fd_closed = False
        try:
            try:
                os.write(fd, rendered.encode("utf-8"))
                os.fsync(fd)
            except Exception:
                # Write-phase failure AFTER successful O_EXCL reservation —
                # unlink the zero-byte poison so retries can re-reserve.
                os.close(fd)
                fd_closed = True
                try:
                    os.unlink(str(effective_path))
                except OSError:
                    pass
                raise
        finally:
            if not fd_closed:
                os.close(fd)
    else:
        atomic_text_write(rendered, effective_path)
    append_evidence_trail(
        effective_path, source_ref, f"Initial extraction: {page_type} page created"
    )


def _build_summary_content(extraction: dict, source_type: str) -> str:
    """Build summary page content from extracted data."""
    lines = []
    title = (
        _coerce_str_field(extraction, "title")
        or _coerce_str_field(extraction, "name")
        or "Untitled"
    )
    safe_title = title.replace("\n", " ").replace("\r", "")
    lines.append(f"# {safe_title}\n")

    # Author/speaker info
    author = _coerce_str_field(extraction, "author") or _coerce_str_field(extraction, "speaker")
    authors = extraction.get("authors")
    if authors and isinstance(authors, list):
        safe_authors = []
        for a in authors:
            if isinstance(a, str):
                safe_authors.append(sanitize_extraction_field(a))
            elif isinstance(a, dict) and a.get("name"):
                safe_authors.append(sanitize_extraction_field(str(a["name"])))
            else:
                logger.warning("Dropping non-string author value: %r", a)
        if safe_authors:
            lines.append(f"**Authors:** {', '.join(safe_authors)}\n")
    elif author:
        lines.append(f"**Author:** {sanitize_extraction_field(author)}\n")

    # Core argument / abstract / description
    for field in ("core_argument", "abstract", "description", "problem_solved"):
        val = _coerce_str_field(extraction, field)
        if val:
            lines.append(f"\n## Overview\n\n{sanitize_extraction_field(val)}\n")
            break

    # Key claims / key points / key arguments
    key_claims = extraction.get("key_claims")
    key_points = extraction.get("key_points")
    key_args = extraction.get("key_arguments")
    claims = (
        key_claims if key_claims is not None else key_points if key_points is not None else key_args
    )
    if claims and isinstance(claims, list):
        lines.append("\n## Key Claims\n")
        for claim in claims:
            safe_claim = sanitize_extraction_field(claim) if isinstance(claim, str) else claim
            lines.append(f"- {safe_claim}")
        lines.append("")

    # Entities
    entities = extraction.get("entities_mentioned")
    if entities and isinstance(entities, list):
        lines.append("\n## Entities Mentioned\n")
        for e in entities:
            slug = slugify(e)
            # Fix 2.8: skip empty slugs; Fix 2.15: sanitize display name
            # Adversarial-review BLOCKER: use exact 6-hex sentinel pattern, not startswith
            if slug and not _is_untitled_sentinel(slug):
                safe_name = wikilink_display_escape(e)
                lines.append(f"- [[entities/{slug}|{safe_name}]]")
        lines.append("")

    # Concepts
    concepts = extraction.get("concepts_mentioned")
    if concepts and isinstance(concepts, list):
        lines.append("\n## Concepts\n")
        for c in concepts:
            slug = slugify(c)
            # Fix 2.8: skip empty slugs; Fix 2.15: sanitize display name
            # Adversarial-review BLOCKER: use exact 6-hex sentinel pattern, not startswith
            if slug and not _is_untitled_sentinel(slug):
                safe_name = wikilink_display_escape(c)
                lines.append(f"- [[concepts/{slug}|{safe_name}]]")
        lines.append("")

    return "\n".join(lines)


def _build_item_content(name: str, source_ref: str, context: str, verb: str) -> str:
    """Build entity or concept page content."""
    safe_name = name.replace("\n", " ").replace("\r", "")
    lines = [
        f"# {safe_name}\n",
        "## References\n",
        f"- {verb} in {source_ref}",
    ]
    if context:
        lines.insert(1, f"{context}\n")
    return "\n".join(lines)


def _extract_entity_context(name: str, extraction: dict) -> str:
    """Build context snippet for an entity from extraction data.

    Searches key_claims, core_argument, and abstract for mentions of the entity.
    Returns a brief description or empty string if nothing relevant found.
    """
    name_lower = name.lower()
    relevant = []

    context_values = [
        _coerce_str_field(extraction, field)
        for field in ("core_argument", "abstract", "description", "problem_solved")
    ]
    for val in context_values:
        if val and bool(re.search(rf"\b{re.escape(name_lower)}\b", val.lower())):
            relevant.append(val)
            break

    key_claims = extraction.get("key_claims")
    key_points = extraction.get("key_points")
    for claim in key_claims if key_claims is not None else key_points or []:
        if isinstance(claim, str) and bool(
            re.search(rf"\b{re.escape(name_lower)}\b", claim.lower())
        ):
            relevant.append(claim)

    if not relevant:
        return ""

    lines = ["## Context\n"]
    for item in relevant[:3]:
        lines.append(f"- {sanitize_extraction_field(item)}")
    return "\n".join(lines)


def _update_existing_page(
    page_path: Path,
    source_ref: str,
    name: str = "",
    extraction: dict | None = None,
    verb: str = "Mentioned",
    ctx: str | None = None,
) -> None:
    """Add a new source reference to an existing wiki page.

    Updates both the YAML frontmatter source: list and the References section.
    When name and extraction are provided, enriches page with context from the new source.

    Cycle 7 AC5 + AC7:
    - References insertion masks fenced code blocks first so `## References`
      appearing literally inside a markdown example does not misdirect the
      regex-anchored insertion point.
    - When the page already has a ``## Context`` section, new context from
      the re-ingest source is now appended as a ``### From {source_ref}``
      subsection under the existing header rather than silently dropped.
    - ``ctx`` kwarg (optional) lets callers inject context directly when
      ``extraction=`` is unavailable; ``_extract_entity_context`` is still
      used when ``ctx is None`` and ``name`` + ``extraction`` are supplied.

    Cycle 20 AC11 / D-NEW-1: the read → modify → atomic_text_write span is now
    wrapped unconditionally in ``file_lock(page_path)`` so concurrent callers
    (including the new AC9/AC10 O_EXCL collision fallback) serialise cleanly.
    ``append_evidence_trail`` stays OUTSIDE the lock block because it acquires
    its own ``file_lock(page_path)`` internally and the sidecar lock is NOT
    re-entrant — nesting would self-deadlock. The lock is released after the
    body write and before evidence append, letting `append_evidence_trail`
    re-acquire cleanly.
    """
    _wrote_page = _update_existing_page_body(
        page_path=page_path,
        source_ref=source_ref,
        name=name,
        extraction=extraction,
        verb=verb,
        ctx=ctx,
    )
    if _wrote_page:
        # Evidence trail acquires its own file_lock(page_path); the body-write
        # lock is released by this point so no nested-lock self-deadlock.
        append_evidence_trail(
            page_path,
            source_ref,
            f"{verb} in new source — source reference added",
        )


def _update_existing_page_body(
    *,
    page_path: Path,
    source_ref: str,
    name: str = "",
    extraction: dict | None = None,
    verb: str = "Mentioned",
    ctx: str | None = None,
) -> bool:
    """Body of `_update_existing_page` under `file_lock(page_path)`.

    Returns True when the page body was modified + written to disk; caller
    uses that signal to decide whether to append an evidence-trail entry.
    Returns False when no update was needed (source already present) OR when
    frontmatter parsing failed and we skipped the write.

    Cycle 20 AC11 / D-NEW-1 — split out so the lock span is visible and so
    the early-return paths exit the lock cleanly via the `with` context.
    """
    with file_lock(page_path):
        # Fix 2.2: Read file exactly once; parse frontmatter from in-memory content (avoids TOCTOU).
        content = page_path.read_text(encoding="utf-8")
        # Cycle 6 AC7 — normalize CRLF → LF so `_SOURCE_BLOCK_RE` (LF-only, line 45)
        # matches CRLF-encoded frontmatter. Without this, CRLF files fall through
        # to the weak fallback at line ~456 which doesn't match either ending,
        # producing silent double `source:` keys. `atomic_text_write` writes LF.
        content = content.replace("\r\n", "\n")
        # Check frontmatter sources specifically, not full content
        try:
            post = frontmatter.loads(content)
            existing_sources = normalize_sources(post.metadata.get("source"))
            if source_ref in existing_sources:
                return False  # Already referenced in frontmatter
        except (ValueError, AttributeError, yaml.YAMLError) as e:
            logger.warning("Failed to parse frontmatter for %s: %s", page_path, e)
            return False

        # 1. Update frontmatter source: list
        safe_ref = yaml_escape(source_ref)
        # Split on the closing '---' to scope the regex to the frontmatter section only
        fm_match = re.match(r"\A(---\r?\n.*?\r?\n---\r?\n?)(.*)", content, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            body_text = fm_match.group(2)
        else:
            # Fix 2.9: warn and return early — falling back to full-file treatment risks
            # corrupting body text that contains "updated: ..." patterns.
            logger.warning("Could not parse frontmatter block in %s; skipping update", page_path)
            return False

        # Fix 2.3: Target only the source: block — not any other YAML list (e.g. tags:)
        source_match = _SOURCE_BLOCK_RE.search(fm_text)
        if source_match:
            block_end = source_match.end()
            # Detect indentation from the first existing entry to preserve style (2- or 4-space).
            block_lines = source_match.group(1).split("\n")
            first_entry_line = block_lines[1] if len(block_lines) > 1 else ""
            indent = (
                len(first_entry_line) - len(first_entry_line.lstrip())
                if first_entry_line.strip()
                else 2
            )
            new_source_line = " " * indent + f'- "{safe_ref}"\n'
            fm_text = fm_text[:block_end] + new_source_line + fm_text[block_end:]
        elif "source:" in fm_text:
            fm_text = fm_text.replace("source:\n", f'source:\n  - "{safe_ref}"\n', 1)

        # Fix 2.17: Apply updated date substitution only to fm_text, not body
        today = date.today().isoformat()
        fm_text = re.sub(r"updated: \d{4}-\d{2}-\d{2}", f"updated: {today}", fm_text)

        content = fm_text + body_text

        # 2. Append to References section (Fix 2.10: append after last ref, Fix 2.11: scope to body)
        ref_line = f"- {verb} in {source_ref}"
        # Cycle 7 AC5: mask fenced code blocks / inline code / markdown links
        # before running the `## References` regex so literal `## References`
        # text inside a code example cannot misdirect the insertion point. The
        # `_mask_code_blocks` helper already ships in compile/linker and is the
        # battle-tested pattern for regex-on-body operations.
        from kb.compile.linker import _mask_code_blocks, _unmask_code_blocks  # noqa: PLC0415

        masked_body, masked_code, mask_prefix = _mask_code_blocks(body_text)
        if "## References" in masked_body:
            # Cycle 3 L7: the regex requires each matched line to end with `\n`
            # and the whole References block to terminate with either `\n## ` or
            # end-of-string. Files saved by editors that strip the trailing
            # newline (common for VSCode + `files.insertFinalNewline` off)
            # matched zero characters after the header, so the new reference
            # appeared BEFORE any existing refs — silently reversing order and
            # sometimes dropping the new entry entirely. Normalize by ensuring
            # body ends with `\n` before substitution.
            if not masked_body.endswith("\n"):
                masked_body = masked_body + "\n"
            # Append new reference at end of References block. PR #21 R1 Codex
            # MAJOR 2: use ``re.subn`` so we can detect whether the regex
            # actually matched (header variant like ``## References   `` with
            # trailing whitespace would otherwise silently no-op, leaving the
            # frontmatter source updated but the body unchanged).
            masked_body_new, n_sub = re.subn(
                r"(## References\n(?:[^\n].*\n|[ \t]*\n)*?)(?=\n## |\Z)",
                lambda m: m.group(1).rstrip("\n") + "\n" + ref_line + "\n",
                masked_body,
                count=1,
                flags=re.MULTILINE,
            )
            if n_sub == 0:
                # Heading present but didn't match the strict regex — append a
                # fresh References block at the end instead of silently dropping
                # the new reference.
                masked_body_new = masked_body.rstrip("\n") + f"\n\n## References\n\n{ref_line}\n"
            body_text = _unmask_code_blocks(masked_body_new, masked_code, mask_prefix)
            content = fm_text + body_text
        elif "## References" not in masked_body:
            # Preserve the old unmasked body (no need to re-unmask a pure-append).
            content += f"\n## References\n\n{ref_line}\n"

        # 4. Enrich with context from new source (if extraction provided OR direct ctx)
        # Cycle 7 AC7: when a ``## Context`` section already exists, append a new
        # ``### From {source_ref}`` subsection instead of silently dropping the
        # new context. Compounds with AC5 by masking code blocks first.
        if ctx is None and name and extraction:
            ctx = _extract_entity_context(name, extraction)
        if ctx:
            masked_c, masked_codes, mask_pfx = _mask_code_blocks(content)
            if "## Context" in masked_c:
                # Strip any leading `## Context` header that `_extract_entity_context`
                # prepends so the incoming ``ctx`` is just the body — the existing
                # section header stays authoritative. Without this strip a duplicate
                # `## Context` header would land under the existing one.
                ctx_body = re.sub(r"\A##\s*Context\s*\n+", "", ctx).rstrip("\n")
                if not ctx_body:
                    # Nothing left after stripping the header — skip.
                    pass
                else:
                    subsection = f"\n### From {source_ref}\n\n{ctx_body}\n"
                    # Find END of Context section (next ## header OR end-of-string).
                    match = re.search(
                        r"(^## Context\n(?:.*\n)*?)(?=^## |\Z)",
                        masked_c,
                        flags=re.MULTILINE,
                    )
                    if match:
                        end = match.end()
                        masked_c = masked_c[:end].rstrip("\n") + subsection + masked_c[end:]
                        content = _unmask_code_blocks(masked_c, masked_codes, mask_pfx)
                    else:
                        # Fallback: append subsection at end of content.
                        content += subsection
            else:
                # No existing Context section — insert before References (or append).
                ref_match = re.search(r"^## References", content, re.MULTILINE)
                if ref_match:
                    insert_pos = ref_match.start()
                    content = content[:insert_pos] + f"{ctx}\n\n" + content[insert_pos:]
                else:
                    content += f"\n{ctx}\n"

        # Fix 2.1: Use atomic write. Cycle 20 AC11 — still inside file_lock(page_path).
        atomic_text_write(content, page_path)
    # Lock released — caller (`_update_existing_page`) now safely invokes
    # `append_evidence_trail`, which acquires its own `file_lock(page_path)`.
    return True


def _update_sources_mapping(
    source_ref: str, wiki_pages: list[str], wiki_dir: Path | None = None
) -> None:
    """Update wiki/_sources.md with source -> wiki page mapping.

    First ingest: appends new entry. Re-ingest: merges new page IDs into
    the existing line rather than silently skipping.
    """
    sources_file = (wiki_dir / "_sources.md") if wiki_dir is not None else WIKI_SOURCES
    pages_str = ", ".join(f"[[{p}]]" for p in wiki_pages)
    escaped_ref = source_ref.replace("`", r"\`")
    entry = f"- `{escaped_ref}` → {pages_str}\n"
    if not sources_file.exists():
        logger.warning("_sources.md not found — skipping source mapping for %s", source_ref)
        return
    content = sources_file.read_text(encoding="utf-8")
    if f"`{source_ref}`" not in content:
        content += entry
        atomic_text_write(content, sources_file)
        return
    # Re-ingest: merge new page IDs into the existing line
    lines = content.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if f"`{source_ref}`" in line:
            existing_ids = set(re.findall(r"\[\[([^\]]+)\]\]", line))
            missing = [p for p in wiki_pages if p not in existing_ids]
            if missing:
                extra = ", ".join(f"[[{p}]]" for p in missing)
                lines[i] = line.rstrip("\n") + f", {extra}\n"
                atomic_text_write("".join(lines), sources_file)
            return


# Fix 2.18: Derive from WIKI_SUBDIR_TO_TYPE at module load time — single source of truth.
_SUBDIR_MAP: dict[str, str] = {v: k for k, v in WIKI_SUBDIR_TO_TYPE.items()}
_SECTION_HEADERS: dict[str, str] = {
    page_type: f"## {subdir.capitalize()}" for subdir, page_type in WIKI_SUBDIR_TO_TYPE.items()
}


def _update_index_batch(entries: list[tuple[str, str, str]], wiki_dir: Path | None = None) -> None:
    """Update wiki/index.md with multiple new page entries in a single read/write."""
    if not entries:
        return
    index_path = (wiki_dir / "index.md") if wiki_dir is not None else WIKI_INDEX
    if not index_path.exists():
        logger.warning("index.md not found — skipping index update for %d entries", len(entries))
        return
    content = index_path.read_text(encoding="utf-8")
    changed = False
    for page_type, slug, title in entries:
        section = _SECTION_HEADERS.get(page_type)
        if not section or section not in content:
            continue
        subdir = _SUBDIR_MAP.get(page_type)
        if not subdir:
            continue
        if f"[[{subdir}/{slug}|" in content or f"[[{subdir}/{slug}]]" in content:
            continue
        safe_title = wikilink_display_escape(title)
        entry = f"- [[{subdir}/{slug}|{safe_title}]]"
        placeholder = f"{section}\n\n*No pages yet.*"
        if placeholder in content:
            content = content.replace(placeholder, f"{section}\n\n{entry}")
        else:
            content = content.replace(f"{section}\n", f"{section}\n{entry}\n", 1)
        changed = True
    if changed:
        atomic_text_write(content, index_path)


# Cycle 18 AC14 — `_write_index_files` helper consolidates the two index-file
# writes with a documented ordering contract (sources BEFORE index — the index
# is the human-facing catalog and references sources that the map already
# knows about). Each call has its OWN try/except (Q10 decision, R2 BLOCKER)
# so failure of one does NOT abort the other; preserves the existing
# `logger.warning` pass-through.
def _write_index_files(
    created_entries: list[tuple[str, str, str]],
    source_ref: str,
    all_pages: list[str],
    wiki_dir: Path | None = None,
) -> None:
    """Write _sources.md then index.md with independent per-call error handling.

    Ordering contract (cycle 18 AC14): `_update_sources_mapping` runs FIRST;
    `_update_index_batch` runs SECOND and is attempted even if sources fails.
    The helper does NOT retry or roll back; partial writes are surfaced via
    `logger.warning` only (matches existing best-effort semantics).

    Symbol constraint (threat T10): `_update_sources_mapping` and
    `_update_index_batch` MUST remain callable as module attributes for legacy
    test monkeypatches — this helper delegates, never inlines.
    """
    try:
        _update_sources_mapping(source_ref, all_pages, wiki_dir=wiki_dir)
    except Exception as e:  # noqa: BLE001 — best-effort write, warn and continue
        logger.warning("Failed to update _sources.md for %s: %s", source_ref, e)
    try:
        _update_index_batch(created_entries, wiki_dir=wiki_dir)
    except Exception as e:  # noqa: BLE001 — best-effort write, warn and continue
        logger.warning("Failed to update index.md for %s: %s", source_ref, e)


# Cycle 18 AC11/AC12/AC13 — structured ingest audit log at
# `.data/ingest_log.jsonl`. One JSON row per emission. Two rows per ingest:
# `start` + one terminal (`duplicate_skip` | `success` | `failure`).
# Best-effort (Q8 decision): disk-full / fsync errors are logged at WARNING
# and do NOT mask the ingest outcome. Use direct `file_lock + open("a")`
# — NOT `atomic_text_write` (whose temp+rename semantics would destroy the
# append history). Field allowlist enforced at the writer (Q19).
_INGEST_JSONL_STAGES = frozenset({"start", "duplicate_skip", "success", "failure"})
_INGEST_JSONL_ERROR_SUMMARY_MAX = 2048
_INGEST_JSONL_ALLOWED_OUTCOME_KEYS = frozenset(
    {"pages_created", "pages_updated", "pages_skipped", "error_summary"}
)


def _emit_ingest_jsonl(
    stage: str,
    request_id: str,
    source_ref: str,
    source_hash: str,
    outcome: dict,
) -> None:
    """Append one audit row to `<PROJECT_ROOT>/.data/ingest_log.jsonl`.

    Cycle 18 AC11/AC12/AC13 — structured ingest observability.

    Args:
        stage: One of `start`, `duplicate_skip`, `success`, `failure`.
            Validated against `_INGEST_JSONL_STAGES`; unknown stage raises
            `ValueError` at the writer boundary (Q19 field-allowlist).
        request_id: 16-hex correlation id (uuid4-derived).
        source_ref: Relative path from `RAW_DIR`.
        source_hash: SHA-256 hex.
        outcome: Dict with allowed keys from `_INGEST_JSONL_ALLOWED_OUTCOME_KEYS`.
            Unexpected keys are DROPPED (WARNING logged) per T1 allowlist.
            `error_summary` is redacted via `sanitize_text` and truncated to
            `_INGEST_JSONL_ERROR_SUMMARY_MAX` bytes.

    Writer mechanics (Q8 best-effort): `file_lock(jsonl_path)` wraps rotation
    + append + fsync. On `OSError`, a WARNING is logged and the caller is not
    disturbed — JSONL write failure MUST NOT mask an otherwise successful
    ingest or replace the original exception on the failure path.
    """
    if stage not in _INGEST_JSONL_STAGES:
        raise ValueError(
            f"Unknown ingest_jsonl stage: {stage!r}; expected one of {_INGEST_JSONL_STAGES}"
        )

    # Q19 field allowlist — build row from EXPLICIT keys only; never passthrough
    # a caller-controlled dict. Prevents raw_content / PII / secret leakage.
    unexpected = set(outcome) - _INGEST_JSONL_ALLOWED_OUTCOME_KEYS
    if unexpected:
        logger.warning(
            "Dropping unexpected ingest_log outcome fields: %s",
            ", ".join(sorted(unexpected)),
        )
    safe_outcome: dict = {}
    for key in ("pages_created", "pages_updated", "pages_skipped"):
        if key in outcome:
            try:
                safe_outcome[key] = int(outcome[key])
            except (TypeError, ValueError):
                pass  # non-integer — silently drop; allowlist enforcement
    err = outcome.get("error_summary")
    if isinstance(err, str) and err:
        # PR #32 R1 Sonnet M1 fix: truncate by UTF-8 BYTES, not characters.
        # Python `str[:n]` counts code points; a 2048-char CJK string encodes
        # to ~6144 UTF-8 bytes and would exceed PIPE_BUF atomicity (threat T7).
        # `errors="ignore"` drops the trailing partial byte sequence.
        safe_outcome["error_summary"] = (
            sanitize_text(err)
            .encode("utf-8")[:_INGEST_JSONL_ERROR_SUMMARY_MAX]
            .decode("utf-8", errors="ignore")
        )

    row = {
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "request_id": request_id,
        "source_ref": source_ref,
        "source_hash": source_hash,
        "stage": stage,
        "outcome": safe_outcome,
    }

    # Read PROJECT_ROOT dynamically so `tmp_kb_env`-style monkeypatches of
    # `kb.config.PROJECT_ROOT` are always honoured, even when the mirror-
    # rebind loop's snapshot missed this module (e.g. stale sys.modules state
    # across test boundaries).
    from kb import config as _config  # noqa: PLC0415

    jsonl_path = _config.PROJECT_ROOT / ".data" / "ingest_log.jsonl"
    try:
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(jsonl_path):
            # AC12 — rotate INSIDE the same lock that wraps the append, symmetric
            # with AC4's wiki-log fix. Rotation first so the append lands in a
            # fresh file when the threshold is crossed.
            rotate_if_oversized(jsonl_path, LOG_SIZE_WARNING_BYTES, "ingest_log")
            with jsonl_path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
    except OSError as e:
        # Q8 — best-effort. JSONL write failure must not mask ingest outcome.
        logger.warning("Failed to write ingest_log.jsonl (best-effort): %s", e)


def _process_item_batch(
    items_raw: object,
    field_name: str,
    max_count: int,
    page_type: str,
    source_ref: str,
    extraction: dict,
    wiki_dir: Path | None = None,
    *,
    shared_seen: dict[str, tuple[str, str]] | None = None,
) -> tuple[list[str], list[str], list[str], list[tuple[str, str]], list[str]]:
    """Validate, deduplicate, and create/update wiki pages for a list of names.

    Returns (created, updated, skipped, new_with_titles, valid_items).
    valid_items is the deduplicated list of names that passed all guards
    (empty-name, empty-slug, collision), for both created and updated pages.
    Used by the caller to build index entries.

    Cycle 6 AC8: when ``shared_seen`` is provided, slug collisions are detected
    across batches (entity + concept). Entity batch runs first in the caller,
    so a concept slug colliding with an existing entity slug is logged as a
    cross-type collision and appended to ``skipped`` — the concept page is NOT
    created or updated. Default ``None`` preserves the per-batch-scoped
    behavior for any legacy caller.
    """
    if page_type not in _SUBDIR_MAP:
        raise ValueError(f"Unknown page_type: {page_type!r}. Valid: {list(_SUBDIR_MAP)}")
    verb = "Mentioned" if page_type == "entity" else "Discussed"
    subdir = _SUBDIR_MAP[page_type]
    items: list = []
    if not isinstance(items_raw, list):
        logger.warning("%s is not a list (%s), skipping", field_name, type(items_raw).__name__)
    else:
        items = items_raw
    if len(items) > max_count:
        logger.warning("%s has %d items, truncating to %d", field_name, len(items), max_count)
        items = items[:max_count]

    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []
    new_with_titles: list[tuple[str, str]] = []
    valid_items: list[str] = []
    # Cycle 6 AC8 (PR #20 R1 Codex NEW-ISSUE fix): store ``(item, page_type)``
    # tuples so we can differentiate same-batch duplicates (silent dedup)
    # from cross-type cross-batch collisions (AC8 WARNING). Previously values
    # were bare ``item`` strings — ``entities_mentioned=["RAG", "RAG"]`` hit
    # ``prev == item`` with ``shared_seen is not None`` and fired the
    # cross-type warning on what was actually an intra-batch duplicate.
    seen_slugs: dict[str, tuple[str, str]] = shared_seen if shared_seen is not None else {}

    effective_wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR

    for item in items:
        if not isinstance(item, str):
            logger.warning("Skipping non-string %s in %s: %r", page_type, field_name, item)
            continue
        if not item or not item.strip():
            continue
        item_slug = slugify(item)
        # B1: treat untitled-<hash> as sentinel for nonsense-punctuation names;
        # empty slug (pre-item-11) and untitled-hash (post-item-11) both mean "skip".
        # Adversarial-review BLOCKER: use exact 6-hex sentinel pattern, not startswith,
        # so legitimate names like "Untitled-Reports" are not falsely filtered.
        if not item_slug or _is_untitled_sentinel(item_slug):
            logger.warning("Skipping %s with empty/untitled slug: %r", page_type, item)
            continue
        if item_slug in seen_slugs:
            prev_item, prev_type = seen_slugs[item_slug]
            # Cycle 6 AC8 (revised post-R1): three distinct cases.
            #   (a) prev_type != page_type → cross-type collision (AC8 case)
            #   (b) same type, prev_item != item → slug-variant collision
            #   (c) same type, same item → intra-batch duplicate, silent dedup
            if prev_type != page_type:
                logger.warning(
                    "Cross-type slug collision: %r already present as %s; skipping %s/%s",
                    item,
                    prev_type,
                    subdir,
                    item_slug,
                )
                skipped.append(f"{subdir}/{item_slug} (cross-type collision)")
            elif prev_item != item:
                logger.warning(
                    "Slug collision: %r and %r both slug to %r", prev_item, item, item_slug
                )
                skipped.append(f"{subdir}/{item_slug} (collision: {item!r})")
            # else: same type + same item → silent dedup (legacy behavior)
            continue
        seen_slugs[item_slug] = (item, page_type)
        valid_items.append(item)
        item_path = effective_wiki_dir / subdir / f"{item_slug}.md"
        if item_path.exists():
            _update_existing_page(
                item_path, source_ref, name=item, extraction=extraction, verb=verb
            )
            updated.append(f"{subdir}/{item_slug}")
        else:
            ctx = _extract_entity_context(item, extraction)
            content = _build_item_content(item, source_ref, ctx, verb)
            # Cycle 20 AC10 — O_EXCL reservation defeats slug-collision
            # last-writer-wins. On StorageError(kind="summary_collision")
            # pivot to the merge path; _update_existing_page acquires its own
            # page-lock (AC11 / D-NEW-1) so serialisation is deterministic.
            try:
                _write_wiki_page(
                    item_path, item, page_type, source_ref, "stated", content, exclusive=True
                )
                created.append(f"{subdir}/{item_slug}")
                new_with_titles.append((f"{subdir}/{item_slug}", item))
            except StorageError as err:
                if err.kind != "summary_collision":
                    raise
                _update_existing_page(
                    item_path, source_ref, name=item, extraction=extraction, verb=verb
                )
                updated.append(f"{subdir}/{item_slug}")

    return created, updated, skipped, new_with_titles, valid_items


def ingest_source(
    source_path: Path,
    source_type: str | None = None,
    extraction: dict | None = None,
    *,
    defer_small: bool = False,
    wiki_dir: Path | None = None,
    raw_dir: Path | None = None,
    manifest_key: str | None = None,
    _skip_vector_rebuild: bool = False,
) -> dict:
    """Ingest a single raw source into the knowledge base.

    Args:
        source_path: Path to the raw source file.
        source_type: Source type (auto-detected from path if omitted).
        extraction: Pre-extracted data dict. If None, calls LLM to extract.
        defer_small: If True, sources under SMALL_SOURCE_THRESHOLD chars get
            summary-only processing (no entity/concept pages).
        wiki_dir: Output wiki directory override (defaults to WIKI_DIR).
        raw_dir: Source root override used for path-traversal validation plus
            source-type detection plus source_ref canonicalization. Defaults to
            module-level ``RAW_DIR``. Required for custom-project isolation
            (kb_lint --augment auto_ingest mode, multi-project test harnesses).
        manifest_key: Cycle 19 AC12. Optional opaque dict-key for the
            ``.data/hashes.json`` manifest. NOT a filesystem path — produced
            by ``kb.compile.compiler.manifest_key_for(source, raw_dir)`` for
            ``compile_wiki`` callers, ensuring the duplicate-check reservation
            and the tail confirmation both write under the same key (closes
            the case-sensitivity / symlink divergence class). Defense-in-depth:
            rejects ``..``, leading ``/`` or ``\\``, ``\\x00``, and lengths
            above 512 chars. Defaults to ``None`` — legacy callers continue
            using the legacy ``source_ref``-derived key.
        _skip_vector_rebuild: If True, suppress the tail-call to
            ``rebuild_vector_index``. Batch callers (e.g. ``compile_wiki``) pass
            True in the per-source loop and invoke ``rebuild_vector_index`` once
            after the loop completes (H17 fix).

    Returns:
        dict with guaranteed keys:
            source_path, source_type, content_hash, pages_created, pages_updated,
            pages_skipped, affected_pages, wikilinks_injected, contradictions.
            Also includes ``duplicate: True`` when the source has identical content
            to an already-ingested file (all contract keys still present, as empty
            lists for affected_pages / wikilinks_injected / contradictions).
    """
    # Cycle 19 AC12 — defense-in-depth validation of the opaque manifest_key.
    # Even though .data/hashes.json keys are NEVER FS-resolved today, validate
    # against future call sites that might accidentally pass it through
    # ``Path(manifest_key).resolve()``.
    # PR #33 R1 Sonnet NIT — empty string previously passed all 4 traversal
    # checks; reject explicitly so an empty manifest_key cannot create a
    # false-positive duplicate via the manifest[""] key collision class.
    if manifest_key is not None:
        if (
            not manifest_key
            or ".." in manifest_key
            or manifest_key.startswith(("/", "\\"))
            or "\x00" in manifest_key
            or len(manifest_key) > 512
        ):
            raise ValueError(f"invalid manifest_key: {manifest_key!r}")
    source_path = Path(source_path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Source not found: {source_path}")

    effective_raw_dir = raw_dir if raw_dir is not None else RAW_DIR
    effective_wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR

    if source_type in {"comparison", "synthesis"}:
        raise ValueError(
            f"source_type={source_type!r} is not valid for ingest_source; "
            "use kb_create_page for comparison and synthesis pages"
        )

    # C2 (Phase 4.5 MEDIUM): reject extensions not in SUPPORTED_SOURCE_EXTENSIONS
    # at the library boundary, not only at the MCP wrapper, so internal callers
    # cannot slip suffix-less files (README, LICENSE) through. Uses the broad
    # allowlist (includes .pdf) so PDFs still hit the UTF-8 decode path where
    # they fail with the helpful "convert to markdown first" message.
    if source_path.suffix.lower() not in SUPPORTED_SOURCE_EXTENSIONS:
        raise ValueError(
            f"Unsupported source extension: {source_path.suffix!r}. "
            f"Expected one of: {sorted(SUPPORTED_SOURCE_EXTENSIONS)}"
        )

    # Verify source_path is within raw/ — use normcase on both sides for
    # reliable case-insensitive comparison on Windows (Python 3.12+).
    raw_dir_nc = Path(os.path.normcase(str(effective_raw_dir.resolve())))
    source_path_nc = Path(os.path.normcase(str(source_path)))

    # Cycle 22 AC1-AC4 — reject paths inside wiki_dir FIRST (before the raw-dir
    # check) so a caller passing a wiki page gets the specific "not inside wiki
    # directory" ValidationError instead of the generic "must be within raw/"
    # ValueError. Both sides are normcase'd + resolved so symlinks / junctions
    # (T1) and Windows case variants (T2) cannot bypass. Message is a FIXED
    # string — no path interpolation — so an absolute wiki path never leaks
    # through CLI / MCP logs (T3). Placement is BEFORE the later
    # ``_emit_ingest_jsonl("start", ...)`` call so a rejected wiki path never
    # produces an orphan ``stage="start"`` row (cycle-18 L3 orphan-start rule).
    #
    # Cycle-18 L1 compliance: this NEW guard is a helper reading WIKI_DIR at
    # call time, so it looks up ``kb.config.WIKI_DIR`` dynamically (attribute
    # access on the module object) rather than using the module-top snapshot.
    # This defeats the reload-leak class where a sibling test's
    # ``importlib.reload(kb.config)`` leaves this module's snapshot pointing
    # at a stale Path object while the test's ``tmp_kb_env`` fixture patches
    # the new ``kb.config.WIKI_DIR``. The existing ``effective_wiki_dir`` is
    # retained unchanged for downstream use (per the cycle-18 L1 "do not
    # refactor working patterns proactively" rule — only the new-code site
    # adopts dynamic lookup).
    import kb.config as _kb_config  # noqa: PLC0415 — lazy import for test robustness

    _wiki_dir_for_guard = wiki_dir if wiki_dir is not None else _kb_config.WIKI_DIR
    wiki_dir_nc = Path(os.path.normcase(str(_wiki_dir_for_guard.resolve())))
    try:
        source_path_nc.relative_to(wiki_dir_nc)
    except ValueError:
        pass  # source is OUTSIDE wiki_dir — guard passes
    else:
        raise ValidationError("Source path must not resolve inside wiki/ directory")

    try:
        source_path_nc.relative_to(raw_dir_nc)
    except ValueError as e:
        # NOTE: this raw-dir guard message still embeds ``source_path`` for
        # backwards compatibility — cycle-22 Q1 design gate accepted the
        # asymmetry and deferred the raw-dir ``ValidationError`` migration +
        # path-redaction to cycle 23 (so existing ``except ValueError`` callers
        # of ``ingest_source`` are not silently broken mid-cycle).
        raise ValueError(f"Source path must be within raw/ directory: {source_path}") from e

    if source_type is None:
        source_type = detect_source_type(source_path, raw_dir=effective_raw_dir)

    # Fix 2.13: Read bytes once; derive both text and hash from the same read (avoids double read).
    raw_bytes = source_path.read_bytes()
    try:
        raw_content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(
            f"Binary file cannot be ingested: {source_path.name}. "
            "Convert to markdown first (e.g., markitdown or docling)."
        ) from e
    source_hash = hash_bytes(raw_bytes)

    # Spec §10 — strip leading YAML frontmatter for capture sources only.
    # Universal stripping would regress sources like Obsidian Web Clipper whose
    # frontmatter (url, author, abstract, tags) carries metadata the write-tier
    # LLM legitimately extracts from. Handles both LF and CRLF delimiters —
    # capture files written on Windows may use CRLF.
    if source_type == "capture":
        for prefix, closer, closer_len in (
            ("---\n", "\n---\n", 5),
            ("---\r\n", "\r\n---\r\n", 7),
        ):
            if raw_content.startswith(prefix):
                end = raw_content.find(closer, len(prefix))
                if end != -1:
                    raw_content = raw_content[end + closer_len :].lstrip("\r\n")
                break

    # Build source reference early for duplicate check
    source_ref = make_source_ref(source_path, raw_dir=effective_raw_dir)
    # Cycle 19 AC12/AC13 — derive manifest_ref ONCE; thread to BOTH the Phase-1
    # reservation AND the Phase-2 confirmation. source_ref is unchanged for
    # provenance / log entries / page frontmatter.
    manifest_ref = manifest_key if manifest_key is not None else source_ref

    # Cycle 18 AC9 — per-ingest correlation ID. 16-hex (64 bits entropy) is
    # sufficient for per-process correlation between wiki/log.md lines and
    # `.data/ingest_log.jsonl` rows; uuid4 is thread-safe and fork-safe.
    request_id = uuid.uuid4().hex[:16]

    # Cycle 18 AC11 — emit `stage="start"` immediately after request_id + source_ref
    # are known. `outcome={}` for this stage; counts unknown until the ingest body
    # completes. PR #32 R1 Codex BLOCKER fix: the try/except wrapping the body
    # MUST start HERE so extraction + validation + duplicate-reservation +
    # body-run all emit `stage="failure"` on exception — previously only
    # _run_ingest_body was wrapped, leaving orphan `start` rows when
    # extract_from_source or _pre_validate_extraction raised.
    _emit_ingest_jsonl("start", request_id, source_ref, source_hash, outcome={})

    try:
        # Validate caller-provided extractions before manifest reservation. In
        # Claude Code mode, extraction is produced here first, then validated
        # before the same reservation point.
        if extraction is None:
            extraction = extract_from_source(raw_content, source_type, wiki_dir=effective_wiki_dir)
        _pre_validate_extraction(extraction)

        # Q_A fix (Phase 4.5 HIGH) — Phase 1: atomic duplicate check + manifest reservation.
        # Acquires file_lock(HASH_MANIFEST), checks for duplicate hash, and if not a duplicate,
        # reserves manifest[manifest_ref] = source_hash before releasing. This prevents the RMW
        # race where two concurrent ingests of the same content both pass the duplicate check.
        # Cycle 19 AC12 — pass manifest_ref (= manifest_key or source_ref) so caller-supplied
        # keys from compile_wiki (manifest_key_for) match the Phase-2 confirmation key below.
        if _check_and_reserve_manifest(source_hash, manifest_ref):
            logger.warning("Duplicate content detected: %s (hash: %s)", source_ref, source_hash)
            # Cycle 18 AC11 — duplicate path emits terminal `stage="duplicate_skip"`.
            # Per Q15 decision, wiki/log.md stays success-only; JSONL is the ONLY
            # correlation surface for duplicate/failure paths.
            _emit_ingest_jsonl("duplicate_skip", request_id, source_ref, source_hash, outcome={})
            return {
                "source_path": str(source_path),
                "source_type": source_type,
                "content_hash": source_hash,
                "pages_created": [],
                "pages_updated": [],
                "pages_skipped": [],
                "duplicate": True,
                "affected_pages": [],  # fix item 6: contract key always present
                "wikilinks_injected": [],  # fix item 6: contract key always present
                "contradictions": [],  # fix item 6: contract key always present
            }

        # PR #32 R1 Codex MAJOR fix: success emission moved OUT of
        # _run_ingest_body and INTO ingest_source so all 4 JSONL stage calls
        # are wired at the same level (start / duplicate_skip / success /
        # failure), keeping the telemetry envelope symmetric.
        result = _run_ingest_body(
            source_path=source_path,
            source_type=source_type,
            source_ref=source_ref,
            manifest_ref=manifest_ref,
            source_hash=source_hash,
            request_id=request_id,
            raw_content=raw_content,
            extraction=extraction,
            effective_wiki_dir=effective_wiki_dir,
            effective_raw_dir=effective_raw_dir,
            defer_small=defer_small,
            _skip_vector_rebuild=_skip_vector_rebuild,
        )
        _emit_ingest_jsonl(
            "success",
            request_id,
            source_ref,
            source_hash,
            outcome={
                "pages_created": len(result.get("pages_created", [])),
                "pages_updated": len(result.get("pages_updated", [])),
                "pages_skipped": len(result.get("pages_skipped", [])),
            },
        )
        return result
    except BaseException as exc:
        err_summary = sanitize_text(str(exc))
        _emit_ingest_jsonl(
            "failure",
            request_id,
            source_ref,
            source_hash,
            outcome={"error_summary": err_summary},
        )
        # Cycle 20 AC5 / AC7 — wrap unexpected exceptions into IngestError so
        # callers get a stable taxonomy. Expected ingest-path kinds
        # (KBError subclasses, OSError, ValueError) pass through unchanged so
        # existing call sites keep working. BaseException subclasses that are
        # NOT Exception (KeyboardInterrupt, SystemExit, GeneratorExit) also
        # propagate unchanged to preserve control-flow semantics — they are
        # BaseException but NOT Exception, so `isinstance(exc, Exception)`
        # gates the wrap cleanly.
        if isinstance(exc, Exception) and not isinstance(exc, (KBError, OSError, ValueError)):
            raise IngestError(str(exc)) from exc
        raise


def _run_ingest_body(
    *,
    source_path: Path,
    source_type: str,
    source_ref: str,
    manifest_ref: str,
    source_hash: str,
    request_id: str,
    raw_content: str,
    extraction: dict,
    effective_wiki_dir: Path,
    effective_raw_dir: Path,
    defer_small: bool,
    _skip_vector_rebuild: bool,
) -> dict:
    """Cycle 18 AC11 — ingest body wrapped by `ingest_source`'s try/except.

    Split out of `ingest_source` so the outer function's try/except around this
    body cleanly captures exceptions for JSONL telemetry without mutating the
    entry/validation/duplicate-check sequence above.

    Cycle 19 AC12: `manifest_ref` threads through from `ingest_source` as the
    opaque dict-key for the Phase-2 manifest confirmation write (same key as
    Phase-1 reservation). `source_ref` remains the unchanged identity used
    for page frontmatter, log entries, and provenance.
    """
    # Track created/updated pages
    pages_created = []
    pages_updated = []
    pages_skipped = []
    # (page_id, title) for newly created pages — used by inject_wikilinks
    new_pages_with_titles: list[tuple[str, str]] = []

    # 1. Create summary page (preserve created: date on re-ingest)
    title = (
        _coerce_str_field(extraction, "title")
        or _coerce_str_field(extraction, "name")
        or source_path.stem
    )
    summary_slug = slugify(title)
    if not summary_slug:
        # Fix 2.19: use "untitled" as final fallback if stem also produces empty slug
        summary_slug = slugify(source_path.stem) or "untitled"
        logger.warning(
            "Title %r produced empty slug; falling back to source stem %r",
            title,
            summary_slug,
        )
    elif _is_untitled_sentinel(summary_slug):
        # Adversarial-review MAJOR: title was pure-symbol/emoji — prefer file stem for
        # discoverability (e.g. CJK or emoji titles). If stem also yields a sentinel or
        # empty slug, keep the sentinel (it's the best we can do).
        stem_slug = slugify(source_path.stem)
        if stem_slug and not _is_untitled_sentinel(stem_slug):
            logger.warning(
                "Title %r produced sentinel slug %r; using source stem slug %r instead",
                title,
                summary_slug,
                stem_slug,
            )
            summary_slug = stem_slug
    summary_path = effective_wiki_dir / "summaries" / f"{summary_slug}.md"
    if summary_path.exists():
        _update_existing_page(summary_path, source_ref, verb="Summarized")
        pages_updated.append(f"summaries/{summary_slug}")
        # Do NOT add to new_pages_with_titles — wikilinks for this page already exist
    else:
        summary_content = _build_summary_content(extraction, source_type)
        # Cycle 20 AC9 — O_EXCL reservation prevents concurrent summary writes
        # from dropping one source silently. On StorageError(kind="summary_collision")
        # fall through to _update_existing_page which acquires its own page-lock
        # (AC11 / D-NEW-1).
        try:
            _write_wiki_page(
                summary_path,
                title,
                "summary",
                source_ref,
                "stated",
                summary_content,
                exclusive=True,
            )
            pages_created.append(f"summaries/{summary_slug}")
            new_pages_with_titles.append((f"summaries/{summary_slug}", title))
        except StorageError as err:
            if err.kind != "summary_collision":
                raise
            _update_existing_page(summary_path, source_ref, verb="Summarized")
            pages_updated.append(f"summaries/{summary_slug}")

    # Content-length-aware tiering: short sources get summary only when
    # defer_small is enabled (entity/concept pages deferred to avoid stub proliferation).
    is_small_source = defer_small and len(raw_content) < SMALL_SOURCE_THRESHOLD
    if is_small_source:
        logger.info(
            "Small source (%d chars < %d threshold): deferring entity/concept pages",
            len(raw_content),
            SMALL_SOURCE_THRESHOLD,
        )

    # Cycle 6 AC8 — shared slug namespace across entity + concept batches so a
    # single extraction with overlapping `entities_mentioned` + `concepts_mentioned`
    # collapses to ONE wiki page (entity-first per OQ5) rather than creating
    # a pair of identical-content pages (entities/rag.md AND concepts/rag.md).
    # R1 fix: tuple values (item, page_type) so we can distinguish same-batch
    # dupes from cross-type collisions.
    shared_seen: dict[str, tuple[str, str]] = {}

    # 2. Create or update entity pages (skip for small sources)
    e_created, e_updated, e_skipped, e_new, e_valid = _process_item_batch(
        [] if is_small_source else (extraction.get("entities_mentioned") or []),
        "entities_mentioned",
        MAX_ENTITIES_PER_INGEST,
        "entity",
        source_ref,
        extraction,
        wiki_dir=effective_wiki_dir,
        shared_seen=shared_seen,
    )
    pages_created.extend(e_created)
    pages_updated.extend(e_updated)
    pages_skipped.extend(e_skipped)
    new_pages_with_titles.extend(e_new)

    # 3. Create or update concept pages (skip for small sources)
    c_created, c_updated, c_skipped, c_new, c_valid = _process_item_batch(
        [] if is_small_source else (extraction.get("concepts_mentioned") or []),
        "concepts_mentioned",
        MAX_CONCEPTS_PER_INGEST,
        "concept",
        source_ref,
        extraction,
        wiki_dir=effective_wiki_dir,
        shared_seen=shared_seen,
    )
    pages_created.extend(c_created)
    pages_updated.extend(c_updated)
    pages_skipped.extend(c_skipped)
    new_pages_with_titles.extend(c_new)

    # 4 + 5. Update index files (cycle 18 AC14 — helper wraps the sources-then-
    # index pair with independent per-call try/except and documented ordering).
    # Fix 2.7: use page IDs from created pages for slug consistency (avoids
    # re-slugify divergence). Precompute slug→display-name dicts (O(n)) to
    # avoid O(n²) linear scans below.
    e_name_by_slug: dict[str, str] = {slugify(e): e for e in e_valid}
    c_name_by_slug: dict[str, str] = {slugify(c): c for c in c_valid}
    index_entries: list[tuple[str, str, str]] = [("summary", summary_slug, title)]
    for pid in e_created:
        slug = pid.split("/", 1)[-1] if "/" in pid else pid
        name = e_name_by_slug.get(slug, slug)
        index_entries.append(("entity", slug, name))
    for pid in e_updated:
        slug = pid.split("/", 1)[-1] if "/" in pid else pid
        name = e_name_by_slug.get(slug, slug)
        index_entries.append(("entity", slug, name))
    for pid in c_created:
        slug = pid.split("/", 1)[-1] if "/" in pid else pid
        name = c_name_by_slug.get(slug, slug)
        index_entries.append(("concept", slug, name))
    for pid in c_updated:
        slug = pid.split("/", 1)[-1] if "/" in pid else pid
        name = c_name_by_slug.get(slug, slug)
        index_entries.append(("concept", slug, name))
    all_pages = pages_created + pages_updated
    _write_index_files(
        created_entries=index_entries,
        source_ref=source_ref,
        all_pages=all_pages,
        wiki_dir=effective_wiki_dir,
    )

    # 6. Q_A fix (Phase 4.5 HIGH) — Phase 2: idempotent manifest confirmation.
    # Re-acquires file_lock(HASH_MANIFEST) to write the final hash (Phase 1 already
    # reserved it, but this re-confirms after all ingest work completes, consistent with C5).
    # Cycle 19 AC12 — Phase 2 uses the SAME manifest_ref the Phase-1 reservation
    # used (R2 M1 fix), so a caller-supplied manifest_key writes to a single key
    # both times, eliminating the dual-write divergence under non-default raw_dir.
    try:
        from kb.compile.compiler import HASH_MANIFEST, load_manifest, save_manifest

        with file_lock(HASH_MANIFEST):
            manifest = load_manifest()
            manifest[manifest_ref] = source_hash  # idempotent — same value as Phase 1 reservation
            save_manifest(manifest)
    except (OSError, json.JSONDecodeError) as e:
        # Fix 2.14: narrow bare except — log at WARNING, not DEBUG
        logger.warning("Failed to update hash manifest: %s", e)
    except Exception as e:
        logger.debug("Failed to update hash manifest (unexpected): %s", e)

    # 7. Append to log (best-effort — page writes already succeeded; a log failure
    # must not crash the caller or hide the successful ingest result).
    # Cycle 18 AC10 — prefix the message with `[req={request_id}]` so the
    # wiki/log.md line correlates 1:1 with the JSONL `request_id` field.
    # The prefix is hex-only (no markdown markers, no `|`/newline) so it flows
    # through `_escape_markdown_prefix` untouched — verified by regression test.
    try:
        append_wiki_log(
            "ingest",
            f"[req={request_id}] Ingested {source_ref} → created {len(pages_created)} pages, "
            f"updated {len(pages_updated)} pages",
            effective_wiki_dir / "log.md",
        )
    except OSError as e:
        logger.warning("Failed to append wiki log after successful ingest: %s", e)

    # Load all pages once — shared by affected-pages analysis and contradiction detection
    all_wiki_pages = load_all_pages(wiki_dir=effective_wiki_dir)

    # 8. Compute affected pages (cascade update detection)
    affected_pages = _find_affected_pages(
        pages_created + pages_updated,
        wiki_dir=effective_wiki_dir,
        pages=all_wiki_pages,
    )

    # 9. Retroactive wikilink injection — cycle-19 AC6: switched from N
    # per-title `inject_wikilinks` calls to a single `inject_wikilinks_batch`
    # call that scans each existing page AT MOST ONCE (per chunk). Reduces
    # 100·N disk reads at 50 entities + 50 concepts × N existing pages to
    # ≤ 2·N. Pages bundle `all_wiki_pages` is already pre-loaded above for
    # affected-pages analysis (cycle-19 AC7 — re-use, don't re-walk disk).
    wikilinks_injected: list[str] = []
    sorted_new_pages = _sort_new_pages_by_title_length(new_pages_with_titles)
    if sorted_new_pages:
        try:
            from kb.compile.linker import inject_wikilinks_batch

            # _sort_new_pages_by_title_length returns [(pid, title), ...];
            # inject_wikilinks_batch expects [(title, pid), ...].
            batch_input = [(title, pid) for pid, title in sorted_new_pages]
            batch_result = inject_wikilinks_batch(
                batch_input,
                wiki_dir=effective_wiki_dir,
                pages=all_wiki_pages,
            )
            # Flatten batch result dict to a single list (preserves existing
            # `wikilinks_injected` shape for downstream consumers).
            for updated_list in batch_result.values():
                wikilinks_injected.extend(updated_list)
            # Cycle-19 AC20: single audit-log line via append_wiki_log.
            # Inherits cycle-2 _escape_markdown_prefix sanitizer — titles
            # containing leading #/-/>/!  or [[/]] markers are neutralised.
            if wikilinks_injected:
                injected_summary = ", ".join(sorted(set(wikilinks_injected)))
                if len(injected_summary) > 100:
                    injected_summary = injected_summary[:100] + "..."
                try:
                    log_path = effective_wiki_dir / "log.md"
                    append_wiki_log(
                        "inject_wikilinks_batch",
                        f"injected {len(wikilinks_injected)} link(s): {injected_summary}",
                        log_path,
                    )
                except OSError as log_exc:
                    logger.warning("inject_wikilinks_batch log append failed: %s", log_exc)
        except Exception as e:
            logger.debug("inject_wikilinks_batch failed: %s", e)

    # Auto-contradiction detection. Cycle 4 item #22 — migrate to the
    # sibling `detect_contradictions_with_metadata` so truncation is
    # observable at WARNING level. The legacy `detect_contradictions`
    # signature is preserved for other callers (tests, downstream users).
    contradiction_warnings: list[dict] = []
    if extraction:
        key_claims = extraction.get("key_claims") or extraction.get("key_points") or []
        if key_claims and isinstance(key_claims, list):
            try:
                # Phase 4.5 HIGH D6: exclude pages created in THIS ingest to prevent
                # noisy self-comparison (new summary vs new entities from same source).
                pages_created_set = set(pages_created)
                preexisting_pages = [p for p in all_wiki_pages if p["id"] not in pages_created_set]
                metadata = detect_contradictions_with_metadata(
                    [str(c) for c in key_claims if isinstance(c, str)],
                    preexisting_pages,
                )
                contradiction_warnings = _emit_contradiction_telemetry(metadata, source_ref, logger)
                if contradiction_warnings:
                    logger.warning(
                        "Detected %d potential contradiction(s) during ingest of %s",
                        len(contradiction_warnings),
                        source_ref,
                    )
                    # H3 fix: delegate to _persist_contradictions (file-locked RMW).
                    _persist_contradictions(contradiction_warnings, source_ref, effective_wiki_dir)
            except (KeyError, TypeError, re.error) as e:
                # C3 (Phase 4.5 R4 HIGH) + Cycle 7 AC6: narrow further — bug-
                # indicating errors (ValueError, AttributeError, ImportError,
                # NameError) must propagate instead of being silently masked
                # as "non-fatal". Detection throwing ValueError indicates
                # extractor malformation, not a data-quality skip.
                logger.warning(
                    "Contradiction detection skipped for %s (non-fatal): %s",
                    source_ref,
                    e,
                )

    # Fix 2.21: deduplicate wikilinks_injected
    result = {
        "source_path": str(source_path),
        "source_type": source_type,
        "content_hash": source_hash,
        "pages_created": pages_created,
        "pages_updated": pages_updated,
        "pages_skipped": pages_skipped,
        "affected_pages": affected_pages,
        "wikilinks_injected": sorted(set(wikilinks_injected)),
    }
    if is_small_source:
        result["deferred_entities"] = True
    if contradiction_warnings:
        result["contradictions"] = contradiction_warnings

    # H17 fix: rebuild vector index at ingest tail so hybrid search stays live.
    # Batch callers (compile_wiki) suppress this with _skip_vector_rebuild=True
    # and invoke rebuild_vector_index once after the loop.
    if not _skip_vector_rebuild:
        try:
            from kb.query.embeddings import rebuild_vector_index

            rebuild_vector_index(effective_wiki_dir)
        except Exception as e:
            logger.warning("Vector index rebuild at ingest tail failed: %s", e)

    # PR #32 R1 Codex MAJOR fix: `stage="success"` emission moved OUT of
    # _run_ingest_body and into `ingest_source` so all 4 stage calls are
    # wired at the same telemetry boundary (start/duplicate_skip/success/
    # failure). _run_ingest_body is now a pure body — its caller owns the
    # JSONL envelope.
    return result
