"""Page refinement — update content preserving frontmatter, log revisions.

## Concurrency notes (cycle 19 AC10)

`refine_page` acquires two locks. The order is **page_path FIRST, history_path SECOND**
(preserved from the cycle-1 H1 fix). Cycle-19 AC10 retains this order — flipping
to history-first would have introduced a liveness regression (every concurrent
refine across the wiki would serialize on the single history-lock) without
addressing any deadlock risk in the current call graph.

Inside the page-lock window, the history-lock is acquired ONCE and held across
the entire page-write window (cycle 19 AC9 — single-span semantic for
crash-safety). Within that span, `refine_page` writes a `status="pending"`
history entry tagged with a fresh `attempt_id = uuid4().hex[:8]` BEFORE the page
body atomic-write, then flips that exact row to `status="applied"` (or
`"failed"` on OSError) using `attempt_id` equality (cycle 19 AC8). A crash
between pending-write and the flip leaves the audit row visible as `pending`,
giving operators a self-describing forensic signal.

`list_stale_pending(hours=24)` (cycle 19 AC8b) is a pure-read reporter helper
that operators can run to surface pending rows older than a threshold. A full
sweep / auto-promote tool is deferred to a future cycle.
"""

import json
import logging
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from kb.config import (
    MAX_NOTES_LEN,
    MAX_REVIEW_HISTORY_ENTRIES,
    REVIEW_HISTORY_PATH,
    WIKI_DIR,
)
from kb.utils.io import atomic_text_write, file_lock
from kb.utils.markdown import FRONTMATTER_RE
from kb.utils.wiki_log import append_wiki_log

logger = logging.getLogger(__name__)


def load_review_history(path: Path | None = None) -> list[dict]:
    """Load revision history from JSON file."""
    path = path or REVIEW_HISTORY_PATH
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return data
    return []


def save_review_history(history: list[dict], path: Path | None = None) -> None:
    """Save revision history to JSON file (atomic write via temp file)."""
    from kb.utils.io import atomic_json_write

    path = path or REVIEW_HISTORY_PATH
    atomic_json_write(history, path)


def refine_page(
    page_id: str,
    updated_content: str,
    revision_notes: str = "",
    wiki_dir: Path | None = None,
    history_path: Path | None = None,
) -> dict:
    """Update a wiki page's content while preserving frontmatter.

    Args:
        page_id: Wiki page ID (e.g., 'concepts/rag').
        updated_content: New markdown body (replaces everything after frontmatter).
        revision_notes: What changed and why. Capped at MAX_NOTES_LEN
            chars before append_wiki_log to prevent pathological lengths
            collapsing to a single line in wiki/log.md.
        wiki_dir: Path to wiki directory.
        history_path: Path to review history JSON.

    Returns:
        Dict with page_id, updated, revision_notes. On error: dict with 'error' key.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    page_path = wiki_dir / f"{page_id}.md"

    # R1 (Phase 4.5 R4 LOW): cap revision_notes BEFORE any log/history
    # write. append_wiki_log collapses newlines to spaces, so a multi-
    # megabyte note becomes a single unreadable line otherwise.
    if len(revision_notes) > MAX_NOTES_LEN:
        revision_notes = revision_notes[:MAX_NOTES_LEN]

    # Guard against path traversal — page must resolve within wiki_dir
    try:
        page_path.resolve().relative_to(wiki_dir.resolve())
    except ValueError:
        return {"error": f"Invalid page_id: {page_id}. Path escapes wiki directory."}

    if not page_path.exists():
        return {"error": f"Page not found: {page_id}"}

    # H1 fix (Phase 4.5 HIGH): lock the page file for the entire read→write window so
    # concurrent refine_page calls on the same page don't overwrite each other's body.
    # Lock-order: page_path acquired FIRST; history_path acquired SECOND (below).
    # Cycle 19 AC10 — order PRESERVED (WITHDRAW of the proposed flip; see module
    # docstring for rationale). T-10 asserts this order.
    try:
        page_lock = file_lock(page_path)
        page_lock.__enter__()
    except TimeoutError as e:
        return {"error": f"Failed to acquire page lock for {page_id}: {e}"}

    # Cycle 19 AC8 — fresh per-refine attempt_id correlates pending → applied/failed.
    attempt_id = uuid.uuid4().hex[:8]

    try:
        try:
            text = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return {"error": f"Cannot read {page_id}: {e}"}
        # Phase 4.5 HIGH D2: strip UTF-8 BOM so frontmatter regex matches
        text = text.lstrip("\ufeff")
        # Normalize CRLF → LF for consistent frontmatter parsing on Windows
        text = text.replace("\r\n", "\n")

        # R1 (Phase 4.5 R4 HIGH): use the shared FRONTMATTER_RE from
        # utils/markdown. The previous local regex permitted leading
        # whitespace before the opening fence, which diverged from
        # load_all_pages / build_graph / BM25 — refine_page would succeed
        # while the same file was treated as "no frontmatter" elsewhere,
        # making the refined page's wikilinks disappear from the graph.
        fm_match = FRONTMATTER_RE.match(text)
        if not fm_match:
            return {"error": f"Invalid frontmatter format in {page_id}"}

        fm_block = fm_match.group(1)  # ---\n...\n---\n? (includes fences)
        # Extract inner YAML between the fences so downstream date-update
        # regex still matches `^updated:` at line starts.
        inner_match = re.match(r"---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", fm_block, re.DOTALL)
        if not inner_match:
            return {"error": f"Invalid frontmatter format in {page_id}"}
        frontmatter_text = inner_match.group(1) + "\n"

        # Cycle 7 AC22: validate the frontmatter block with ``yaml.safe_load``
        # BEFORE rewriting. Without this gate, a page with malformed
        # frontmatter (e.g. tab-indented keys that regex-match but fail
        # YAML parsing) would be laundered through a successful write with
        # fresh valid frontmatter, corrupting the page's original data.
        # PR #21 R1 Codex MAJOR 4: also verify the parsed value is a mapping —
        # well-formed YAML that parses to a scalar/list (e.g. `title: null`
        # alone at the top) would otherwise pass the syntax gate while
        # silently indicating a broken page.
        import yaml  # noqa: PLC0415 — library-boundary import

        try:
            parsed_fm = yaml.safe_load(frontmatter_text)
        except yaml.YAMLError as e:
            logger.warning(
                "refine_page(%s) rejected: malformed frontmatter YAML: %s",
                page_id,
                e,
            )
            return {
                "error": (
                    f"Malformed frontmatter YAML in {page_id} — "
                    f"refine rejected to prevent corruption: {e}"
                )
            }
        if parsed_fm is None or not isinstance(parsed_fm, dict):
            logger.warning(
                "refine_page(%s) rejected: frontmatter is not a mapping (%s)",
                page_id,
                type(parsed_fm).__name__,
            )
            return {
                "error": (
                    f"Frontmatter in {page_id} is not a YAML mapping — "
                    f"refine rejected to prevent corruption."
                )
            }
        # PR #21 R2 Codex — reject semantically broken frontmatter where the
        # required ``title`` field parses to a null / empty / non-string value.
        # ``title: null`` parses as a dict so the type gate above passes, but
        # launching through a refine rewrites the page with a null title that
        # silently breaks downstream ingest/graph consumers.
        title_val = parsed_fm.get("title")
        if title_val is None or (isinstance(title_val, str) and not title_val.strip()):
            logger.warning(
                "refine_page(%s) rejected: frontmatter title is null or empty",
                page_id,
            )
            return {
                "error": (
                    f"Frontmatter in {page_id} has null/empty title — "
                    f"refine rejected to prevent corruption."
                )
            }

        # Update the 'updated' date in frontmatter
        today = date.today().isoformat()
        if re.search(r"^updated: \d{4}-\d{2}-\d{2}", frontmatter_text, re.MULTILINE):
            frontmatter_text = re.sub(
                r"^updated: \d{4}-\d{2}-\d{2}",
                f"updated: {today}",
                frontmatter_text,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            # Add updated field if missing
            frontmatter_text = frontmatter_text.rstrip("\n") + f"\nupdated: {today}\n"

        # Guard against empty or whitespace-only content
        if not updated_content or not updated_content.strip():
            return {"error": "updated_content cannot be empty."}

        # Normalize CRLF in caller-supplied content before guard check
        updated_content = updated_content.replace("\r\n", "\n")

        # Phase 4.5 HIGH D1: reject frontmatter blocks (---\nkey: val\n---) but allow
        # horizontal rules (---\n). Require at least one YAML key: value line between fences.
        stripped_content = updated_content.lstrip()
        if re.match(r"---\n\s*\w+\s*:.*?\n---", stripped_content, re.DOTALL):
            return {"error": "Content looks like a frontmatter block — pass only the body text."}

        # Reconstruct page — strip only leading newlines (preserve indented code blocks).
        # Adversarial-review MAJOR: use [\r\n]+ for defense-in-depth; upstream CRLF→LF
        # normalization at line ~100 handles most cases, but this guard catches any remnants.
        body = re.sub(r"\A[\r\n]+", "", updated_content)
        new_text = f"---\n{frontmatter_text}---\n\n{body}\n"

        # Cycle 19 AC8/AC9/AC10 — TWO-PHASE WRITE under the existing page_lock.
        # Resolve the history path BEFORE acquiring history_lock so failure path
        # diagnostics can still mention the path. Lock-order remains
        # page_lock OUTER, history_lock INNER (cycle-1 H1 contract).
        if history_path is not None:
            resolved_history_path = history_path
        elif wiki_dir is not None:
            resolved_history_path = wiki_dir.parent / ".data" / "review_history.json"
        else:
            resolved_history_path = REVIEW_HISTORY_PATH

        # Single history_lock span covers pending-write + page-write + applied/failed flip.
        # (Hold-through semantic per cycle-19 AC9 — release-and-reacquire would race.)
        with file_lock(resolved_history_path):
            timestamp = datetime.now().isoformat(timespec="seconds")
            # Phase 1 — write pending row BEFORE the page body.
            history = load_review_history(resolved_history_path)
            history.append(
                {
                    "timestamp": timestamp,
                    "page_id": page_id,
                    "revision_notes": revision_notes,
                    "content_length": len(updated_content),
                    "status": "pending",
                    "attempt_id": attempt_id,
                }
            )
            if len(history) > MAX_REVIEW_HISTORY_ENTRIES:
                history = history[-MAX_REVIEW_HISTORY_ENTRIES:]
            save_review_history(history, resolved_history_path)

            # Phase 2 — write the page body. Exceptions flip pending → failed
            # under the SAME lock span (no release/re-acquire window).
            try:
                atomic_text_write(new_text, page_path)
            except OSError as e:
                history = load_review_history(resolved_history_path)
                for row in history:
                    if row.get("attempt_id") == attempt_id:
                        row["status"] = "failed"
                        row["error"] = str(e)
                        break
                save_review_history(history, resolved_history_path)
                return {"error": f"Failed to write page {page_id}: {e}"}

            # Phase 3 — flip pending → applied (cycle 19 AC8 attempt_id correlation).
            history = load_review_history(resolved_history_path)
            for row in history:
                if row.get("attempt_id") == attempt_id:
                    row["status"] = "applied"
                    break
            save_review_history(history, resolved_history_path)
    finally:
        page_lock.__exit__(None, None, None)

    # Append to wiki/log.md (best-effort — page + history already written successfully;
    # a log failure must not crash the caller or hide the successful refine result).
    log_path = wiki_dir / "log.md"
    try:
        append_wiki_log("refine", f"Refined {page_id}: {revision_notes}", log_path)
    except OSError as e:
        logger.warning("Failed to append wiki log after successful refine: %s", e)

    return {
        "page_id": page_id,
        "updated": True,
        "revision_notes": revision_notes,
    }


def list_stale_pending(
    hours: int = 24,
    *,
    history_path: Path | None = None,
) -> list[dict]:
    """Return review-history entries with status='pending' older than ``hours``.

    Cycle 19 AC8b — pure-read visibility helper that lets operators surface
    rows where ``refine_page`` crashed between the pending-write and the
    applied/failed flip (the rare two-phase-write hole). NO mutation, no
    locks beyond what ``load_review_history`` already does. A full sweep
    or auto-promote tool is deferred to a future cycle (this one ships
    visibility only — see ``docs/superpowers/decisions/2026-04-21-cycle19-design.md``
    AC8b rationale).

    Args:
        hours: Threshold in hours. Pending rows whose ``timestamp`` is older
            than ``now - hours`` are returned. Defaults to 24.
        history_path: Optional override for the review-history JSON file
            (defaults to ``REVIEW_HISTORY_PATH``).

    Returns:
        List of pending-status entries (dict copies — caller mutations do
        not affect the on-disk store).
    """
    cutoff = datetime.now() - timedelta(hours=hours)
    history = load_review_history(history_path)
    stale: list[dict] = []
    for row in history:
        if row.get("status") != "pending":
            continue
        ts_raw = row.get("timestamp")
        if not isinstance(ts_raw, str):
            continue
        try:
            ts = datetime.fromisoformat(ts_raw)
        except ValueError:
            continue
        if ts < cutoff:
            stale.append(row)
    return stale
