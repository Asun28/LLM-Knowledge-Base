"""Wikilink resolution, cross-referencing, and backlink management."""

import logging
import re
import uuid
from pathlib import Path

from kb.config import MAX_INJECT_TITLE_LEN, MAX_INJECT_TITLES_PER_BATCH, WIKI_DIR
from kb.utils.io import atomic_text_write, file_lock
from kb.utils.markdown import FRONTMATTER_RE as _FRONTMATTER_RE
from kb.utils.markdown import extract_wikilinks
from kb.utils.pages import load_all_pages, page_id, scan_wiki_pages
from kb.utils.text import wikilink_display_escape

logger = logging.getLogger(__name__)

# Cycle 18 AC7/Q21 — bounded per-page lock timeout for inject_wikilinks.
# Default 5s × N pages would stall ingest 100s+ on pathological stuck locks;
# 0.25s + skip + warn lets ingest progress and leaves the missed link for the
# next ingest or `kb lint` cycle to heal.
_INJECT_LOCK_TIMEOUT = 0.25


def _check_not_in_wikilink(match: re.Match, body: str, pid: str, replacement: str) -> str | None:
    """Return replacement text if match is not inside an open [[ ]], else None.

    Defined at module scope so inject_wikilinks does not re-create it on every
    loop iteration (avoids the function-redefinition-in-loop anti-pattern).
    """
    start = match.start()
    before = body[:start]
    open_count = before.count("[[") - before.count("]]")
    if open_count > 0:
        logger.warning(
            "inject_wikilinks: skipping replacement in %s — unmatched [[ before position %d",
            pid,
            start,
        )
        return None
    return replacement


# Regex for fenced code blocks (``` ... ```), inline code (`...`),
# markdown links ([text](url)), and images (![alt](url)).
_CODE_MASK_RE = re.compile(
    r"```.*?```|~~~.*?~~~|`[^`\n]+`"
    r"|!\[(?:[^\]]*)\]\((?:[^()]*|\([^()]*\))*\)"
    r"|\[(?:[^\]]*)\]\((?:[^()]*|\([^()]*\))*\)",
    re.DOTALL,
)


def _mask_code_blocks(text: str) -> tuple[str, list[str], str]:
    """Replace code blocks, inline code, and markdown links with null-byte placeholders.

    Returns:
        Tuple of (masked_text, list_of_originals, prefix) where prefix is a
        per-call UUID hex string used to prevent placeholder collisions.
    """
    masked: list[str] = []
    prefix = uuid.uuid4().hex[:8]

    def _replace(m: re.Match) -> str:
        masked.append(m.group(0))
        return f"\x00{prefix}{len(masked) - 1}\x00"

    return _CODE_MASK_RE.sub(_replace, text), masked, prefix


def _unmask_code_blocks(text: str, masked: list[str], prefix: str) -> str:
    """Restore code blocks and inline code from placeholders."""
    for i, code in enumerate(masked):
        text = text.replace(f"\x00{prefix}{i}\x00", code)
    return text


def resolve_wikilinks(wiki_dir: Path | None = None) -> dict:
    """Resolve all wikilinks across the wiki and report broken links.

    Returns:
        dict with keys: total_links, resolved, broken (list of {source, target}).
    """
    wiki_dir = wiki_dir or WIKI_DIR
    pages = scan_wiki_pages(wiki_dir)
    existing_ids = {page_id(p, wiki_dir).lower() for p in pages}

    total = 0
    resolved = 0
    broken = []

    for page_path in pages:
        try:
            content = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read %s for wikilink resolution: %s", page_path, e)
            continue
        # Strip frontmatter before extracting wikilinks to avoid false matches in YAML values
        fm_match = _FRONTMATTER_RE.match(content)
        body = fm_match.group(2) if fm_match else content
        links = extract_wikilinks(body)
        source_id = page_id(page_path, wiki_dir).lower()

        for link in links:
            total += 1
            target = link
            if target in existing_ids:
                resolved += 1
            else:
                broken.append({"source": source_id, "target": target})

    return {"total_links": total, "resolved": resolved, "broken": broken}


def build_backlinks(
    wiki_dir: Path | None = None,
    *,
    pages: list[dict] | None = None,
) -> dict[str, list[str]]:
    """Build a backlink index: for each page, list all pages that link to it.

    Args:
        wiki_dir: Path to wiki directory. Uses config default if None.
        pages: Pre-loaded page dicts (id, path, content keys). When provided,
            skips disk I/O — avoids redundant reads when callers already
            loaded pages. Cycle 7 AC10.

    Returns:
        dict mapping page ID to list of page IDs that link to it.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    backlinks: dict[str, set[str]] = {}

    if pages is not None:
        # Cycle 7 AC10: use pre-loaded bundle. Expected dict keys: id, content.
        existing_ids = {p["id"].lower() for p in pages}
        for p in pages:
            content = p.get("content", "")
            fm_match = _FRONTMATTER_RE.match(content)
            body = fm_match.group(2) if fm_match else content
            links = extract_wikilinks(body)
            source_id = p["id"].lower()
            for link in links:
                if link not in existing_ids:
                    continue
                backlinks.setdefault(link, set()).add(source_id)
    else:
        page_paths = scan_wiki_pages(wiki_dir)
        existing_ids = {page_id(p, wiki_dir).lower() for p in page_paths}

        for page_path in page_paths:
            try:
                content = page_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Failed to read %s for backlink index: %s", page_path, e)
                continue
            # Strip frontmatter before extracting wikilinks to avoid false matches in YAML values
            fm_match = _FRONTMATTER_RE.match(content)
            body = fm_match.group(2) if fm_match else content
            links = extract_wikilinks(body)
            # Lowercase source_id to match the lowercased keys in existing_ids
            source_id = page_id(page_path, wiki_dir).lower()

            for link in links:
                target = link
                if target not in existing_ids:
                    continue  # Skip broken links (consistent with build_graph)
                backlinks.setdefault(target, set()).add(source_id)

    return {k: sorted(v) for k, v in backlinks.items()}


def inject_wikilinks(
    title: str,
    target_page_id: str,
    wiki_dir: Path | None = None,
) -> list[str]:
    """Scan existing pages and inject wikilinks for mentions of a new page's title.

    Uses word-boundary matching (case-insensitive) to find plain-text mentions
    of the title in existing page bodies (not frontmatter). Skips pages that
    already link to the target or are the target page itself.

    Args:
        title: The title of the newly created page.
        target_page_id: Page ID of the new page (e.g., 'concepts/rag').
        wiki_dir: Path to wiki directory.

    Returns:
        List of page IDs that were updated with new wikilinks.
    """
    if not title or not title.strip():
        return []

    wiki_dir = wiki_dir or WIKI_DIR
    target_page_id = target_page_id.lower()
    pages = scan_wiki_pages(wiki_dir)
    updated = []

    # Build regex for word-boundary match of the title (case-insensitive).
    # \b fails for titles starting/ending with non-word chars (C++, .NET, GPT-4o).
    # Use lookahead/lookbehind based on whether the first/last char is a word char.
    escaped_title = re.escape(title)
    starts_with_word = bool(title) and (title[0].isalnum() or title[0] == "_")
    ends_with_word = bool(title) and (title[-1].isalnum() or title[-1] == "_")
    left = r"\b" if starts_with_word else r"(?<![a-zA-Z0-9_])"
    right = r"\b" if ends_with_word else r"(?![a-zA-Z0-9_])"
    pattern = re.compile(left + escaped_title + right, re.IGNORECASE)

    for page_path in pages:
        pid = page_id(page_path, wiki_dir)

        # Skip self — no lock needed.
        if pid == target_page_id:
            continue

        # Cycle 18 AC7 — pre-lock cheap read + no-match / already-linked fast-
        # path. Pages that will NOT be modified acquire ZERO locks (threat T8
        # lock-overhead mitigation for large wikis). The post-lock re-read
        # below is the authoritative decision; this pre-scan only gates lock
        # acquisition.
        try:
            peek_content = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        peek_fm_match = _FRONTMATTER_RE.match(peek_content)
        peek_body = peek_fm_match.group(2) if peek_fm_match else peek_content
        if target_page_id in extract_wikilinks(peek_body):
            continue  # already linked — no lock
        peek_masked_body, _peek_mc, _peek_mp = _mask_code_blocks(peek_body)
        if not pattern.search(peek_masked_body):
            continue  # title does not appear in body — no lock

        # Cycle 18 AC7 — under-lock RMW. Acquire per-page lock with bounded
        # timeout (Q21), re-read content, re-validate every fast-path check on
        # the fresh content (defensive against concurrent injector winning the
        # race), and only then write. The pre-lock check above skipped pages
        # that are CERTAINLY no-op; pages reaching this block MIGHT still be
        # no-op by the time the lock is acquired (TOCTOU). Skip the write in
        # that case.
        try:
            with file_lock(page_path, timeout=_INJECT_LOCK_TIMEOUT):
                try:
                    content = page_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue

                # Item 26 (cycle 2): match frontmatter ONCE per page and reuse the
                # result for both the "existing links" guard and the body/frontmatter
                # split. At 5k pages × N titles per ingest this halves FRONTMATTER_RE
                # cost in the inject_wikilinks hot path.
                fm_match = _FRONTMATTER_RE.match(content)
                if fm_match:
                    frontmatter_section = fm_match.group(1)
                    body = fm_match.group(2)
                else:
                    frontmatter_section = ""
                    body = content
                existing_links = extract_wikilinks(body)
                if target_page_id in existing_links:
                    continue  # race lost — concurrent injector won

                # Save original body for final comparison, then mask code blocks
                # so wikilink injection cannot touch content inside ``` ``` or
                # `...` spans.
                original_body = body
                body, masked_code, mask_prefix = _mask_code_blocks(body)

                # Check if title appears in body (outside code blocks) on fresh
                # content — race may have removed the match.
                if not pattern.search(body):
                    continue

                # Replace first plain-text occurrence in body with wikilink.
                # Use finditer loop so a blocked match (already inside [[ ]])
                # doesn't silently skip all subsequent occurrences.
                safe_title = wikilink_display_escape(title)
                replacement = f"[[{target_page_id}|{safe_title}]]"

                new_body = body
                for match in pattern.finditer(body):
                    start = match.start()

                    result = _check_not_in_wikilink(match, body, pid, replacement)
                    if result is None:
                        # This match is inside a wikilink — continue scanning
                        continue
                    new_body = body[:start] + replacement + body[match.end() :]
                    break

                # Restore code blocks before writing (compare against original
                # to avoid spurious writes when the only match was inside a
                # code block).
                new_body = _unmask_code_blocks(new_body, masked_code, mask_prefix)
                if new_body != original_body:
                    atomic_text_write(frontmatter_section + new_body, page_path)
                    updated.append(pid)
                    logger.info("Injected wikilink to %s in %s", target_page_id, pid)
        except TimeoutError:
            # Cycle 18 AC7/Q21 — stuck lock; skip this page and continue. The
            # missed wikilink will retry on the next ingest or be caught by the
            # kb_lint dead-link pass.
            logger.warning(
                "Skipping inject_wikilinks on %s: lock timeout after %.2fs",
                pid,
                _INJECT_LOCK_TIMEOUT,
            )
            continue

    return updated


def _build_title_pattern(title: str) -> re.Pattern[str]:
    """Compile a single-title regex with the same word-boundary semantics as inject_wikilinks."""
    escaped_title = re.escape(title)
    starts_with_word = bool(title) and (title[0].isalnum() or title[0] == "_")
    ends_with_word = bool(title) and (title[-1].isalnum() or title[-1] == "_")
    left = r"\b" if starts_with_word else r"(?<![a-zA-Z0-9_])"
    right = r"\b" if ends_with_word else r"(?![a-zA-Z0-9_])"
    return re.compile(left + escaped_title + right, re.IGNORECASE)


def inject_wikilinks_batch(
    new_pages: list[tuple[str, str]],
    wiki_dir: Path | None = None,
    *,
    pages: list[dict] | None = None,
) -> dict[str, list[str]]:
    """Batch-inject wikilinks for many new pages with single-pass page scanning.

    Replaces N separate :func:`inject_wikilinks` calls with one pass that
    reads each existing wiki page AT MOST ONCE per chunk (chunk size capped
    by ``MAX_INJECT_TITLES_PER_BATCH``). Within each chunk a per-title regex
    is compiled once and tested against the page body; a candidate-match
    triggers per-page ``file_lock`` acquisition + under-lock re-derivation
    of the winning title from FRESH content (cycle 19 AC1b — pre-lock scan
    is candidate-gathering only). At most one wikilink is injected per
    existing page per batch call (parity with single-target ``inject_wikilinks``).

    Args:
        new_pages: list of (title, target_page_id) tuples. Order matters for
            tie-break: the first matching candidate (longest title wins after
            applying the same ``(-len, pid)`` sort the pipeline already uses)
            is injected. Titles longer than ``MAX_INJECT_TITLE_LEN`` are
            skipped with ``log.warning``; ``\\x00`` characters in titles are
            stripped at entry (T2 mitigation — defends the
            ``_mask_code_blocks`` ``\\x00{prefix}{n}\\x00`` placeholder
            scheme even though per-call UUID prefix already mitigates).
        wiki_dir: override for default wiki root (used by ``scan_wiki_pages``
            when ``pages`` is None).
        pages: pre-loaded page bundle (dicts with ``id``, ``path``,
            ``content`` keys — see :func:`load_all_pages`). When provided,
            skips disk walk entirely. Mirrors :func:`build_backlinks`'s
            cycle-7 AC10 contract.

    Returns:
        dict mapping ``target_page_id.lower()`` → list of updated existing
        page IDs. Targets with zero updates have empty lists; targets with no
        candidate matches are absent from the dict.

    Concurrency:
        - Pre-lock scan is CANDIDATE-GATHERING ONLY (cycle 19 AC1b). Winner
          selected UNDER lock from fresh body to defend against concurrent
          injectors that may have changed the page mid-batch.
        - Chunk-level ``try/except`` (cycle 19 AC6) — one chunk failure does
          not abort remaining chunks. Per-page ``TimeoutError`` from stuck
          lock is logged and skipped (mirrors single-target behavior).

    See also: :func:`inject_wikilinks` (single-target, kept for legacy
    callers) — batch is preferred for new callers.
    """
    if not new_pages:
        return {}

    wiki_dir = wiki_dir or WIKI_DIR

    # Cycle 19 T2 mitigation — sanitize null bytes from titles BEFORE alternation.
    # The per-call UUID prefix in `_mask_code_blocks` is the primary defense,
    # but stripping `\x00` at entry is defense-in-depth that also protects the
    # log line and any downstream display.
    sanitized_pages: list[tuple[str, str]] = []
    for title, target_pid in new_pages:
        if not title or not title.strip():
            continue
        clean_title = title.replace("\x00", "")
        if not clean_title:
            continue
        if len(clean_title) > MAX_INJECT_TITLE_LEN:
            logger.warning(
                "inject_wikilinks_batch: skipping overlength title (len=%d, first 64 chars=%r)",
                len(clean_title),
                clean_title[:64],
            )
            continue
        sanitized_pages.append((clean_title, target_pid.lower()))

    if not sanitized_pages:
        return {}

    # Resolve page bundle (or walk disk if absent).
    if pages is not None:
        page_records = [
            {"id": p["id"].lower(), "path": Path(p["path"]), "content": p.get("content", "")}
            for p in pages
        ]
    else:
        page_paths = scan_wiki_pages(wiki_dir)
        page_records = []
        for pp in page_paths:
            try:
                content = pp.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            page_records.append(
                {"id": page_id(pp, wiki_dir).lower(), "path": pp, "content": content}
            )

    # Pre-compile per-title regex once for the whole batch (re-used per chunk).
    title_patterns: dict[str, re.Pattern[str]] = {
        title: _build_title_pattern(title) for title, _ in sanitized_pages
    }

    # Result dict — initialise with empty lists for all target_pids so callers can
    # detect "title processed but no candidates" vs "title not in batch".
    result: dict[str, list[str]] = {target_pid: [] for _, target_pid in sanitized_pages}

    # Chunk loop (cycle 19 AC4) — process up to MAX_INJECT_TITLES_PER_BATCH per round.
    chunk_size = MAX_INJECT_TITLES_PER_BATCH
    total_chunks = (len(sanitized_pages) + chunk_size - 1) // chunk_size
    for chunk_idx in range(total_chunks):
        chunk = sanitized_pages[chunk_idx * chunk_size : (chunk_idx + 1) * chunk_size]
        try:
            _process_inject_chunk(chunk, page_records, title_patterns, result)
        except Exception as exc:
            # Cycle 19 AC6 — chunk-level try/except. One chunk failure does
            # not block remaining chunks. Log and continue.
            logger.warning(
                "inject_wikilinks_batch: chunk %d/%d failed: %r",
                chunk_idx + 1,
                total_chunks,
                exc,
            )

    return result


def _process_inject_chunk(
    chunk: list[tuple[str, str]],
    page_records: list[dict],
    title_patterns: dict[str, re.Pattern[str]],
    result: dict[str, list[str]],
) -> None:
    """Process one chunk of (title, target_pid) tuples against all page_records.

    Mutates ``result`` in place. Pre-lock scan (per-page) gathers candidate
    matches; under-lock re-read picks the winning title from FRESH content.
    """
    # Tie-break order: longest title first, then alphabetical on target_pid.
    # Mirrors `_sort_new_pages_by_title_length` in pipeline.py.
    sorted_chunk = sorted(chunk, key=lambda pt: (-len(pt[0]), pt[1]))

    for record in page_records:
        pid = record["id"]
        page_path: Path = record["path"]
        peek_content = record["content"]

        # Skip self-page for any title in this chunk targeting it.
        # (a single page might be a target if listed in new_pages mid-batch.)
        # Pre-lock peek: any candidate title has at least one match in masked body?
        if peek_content == "":
            continue

        peek_fm_match = _FRONTMATTER_RE.match(peek_content)
        peek_body = peek_fm_match.group(2) if peek_fm_match else peek_content
        existing_links = set(extract_wikilinks(peek_body))

        # Collect candidate titles whose target is not already linked AND title appears in body.
        peek_masked_body, _peek_mc, _peek_mp = _mask_code_blocks(peek_body)
        candidates: list[tuple[str, str]] = []
        for title, target_pid in sorted_chunk:
            if pid == target_pid:
                continue  # never inject a self-link
            if target_pid in existing_links:
                continue
            if title_patterns[title].search(peek_masked_body):
                candidates.append((title, target_pid))

        if not candidates:
            continue  # no-lock fast path (cycle 18 AC7 / cycle 19 AC5)

        # Acquire per-page lock with bounded timeout. Re-read body, re-validate
        # candidates against FRESH content, pick winner from fresh data.
        try:
            with file_lock(page_path, timeout=_INJECT_LOCK_TIMEOUT):
                try:
                    fresh_content = page_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue

                fm_match = _FRONTMATTER_RE.match(fresh_content)
                if fm_match:
                    frontmatter_section = fm_match.group(1)
                    body = fm_match.group(2)
                else:
                    frontmatter_section = ""
                    body = fresh_content

                fresh_links = set(extract_wikilinks(body))
                original_body = body
                body_masked, masked_code, mask_prefix = _mask_code_blocks(body)

                # Cycle 19 AC1b — re-derive winner from FRESH body. Filter the
                # snapshot candidate list against fresh content; pick the first
                # surviving candidate (sorted_chunk's longest-first order).
                winner: tuple[str, str] | None = None
                for title, target_pid in candidates:
                    if target_pid in fresh_links:
                        continue  # race lost — concurrent injector won
                    if not title_patterns[title].search(body_masked):
                        continue  # title no longer in fresh body
                    winner = (title, target_pid)
                    break

                if winner is None:
                    continue

                title, target_pid = winner
                pattern = title_patterns[title]
                safe_title = wikilink_display_escape(title)
                replacement = f"[[{target_pid}|{safe_title}]]"

                new_body = body_masked
                for match in pattern.finditer(body_masked):
                    start = match.start()
                    if _check_not_in_wikilink(match, body_masked, pid, replacement) is None:
                        continue
                    new_body = body_masked[:start] + replacement + body_masked[match.end() :]
                    break

                new_body = _unmask_code_blocks(new_body, masked_code, mask_prefix)
                if new_body != original_body:
                    atomic_text_write(frontmatter_section + new_body, page_path)
                    result[target_pid].append(pid)
                    # Update in-memory record so subsequent chunk iterations
                    # observe the post-write state.
                    record["content"] = frontmatter_section + new_body
                    logger.info(
                        "inject_wikilinks_batch: injected %s in %s (winner=%r)",
                        target_pid,
                        pid,
                        title,
                    )
        except TimeoutError:
            logger.warning(
                "inject_wikilinks_batch: lock timeout on %s after %.2fs",
                pid,
                _INJECT_LOCK_TIMEOUT,
            )
            continue
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning(
                "inject_wikilinks_batch: I/O error on %s: %r",
                pid,
                exc,
            )
            continue


# Cycle 19 AC7 — pages bundle threading. Re-export load_all_pages alongside
# inject_wikilinks_batch so callers in ingest/pipeline.py can import both
# from the linker module without an extra import line.
__all__ = [
    "build_backlinks",
    "inject_wikilinks",
    "inject_wikilinks_batch",
    "load_all_pages",
    "resolve_wikilinks",
]
