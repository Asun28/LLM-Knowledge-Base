"""Page refinement — update content preserving frontmatter, log revisions."""

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path

from kb.config import MAX_REVIEW_HISTORY_ENTRIES, REVIEW_HISTORY_PATH, WIKI_DIR
from kb.utils.io import atomic_text_write, file_lock
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
        revision_notes: What changed and why.
        wiki_dir: Path to wiki directory.
        history_path: Path to review history JSON.

    Returns:
        Dict with page_id, updated, revision_notes. On error: dict with 'error' key.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    page_path = wiki_dir / f"{page_id}.md"

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
    try:
        page_lock = file_lock(page_path)
        page_lock.__enter__()
    except TimeoutError as e:
        return {"error": f"Failed to acquire page lock for {page_id}: {e}"}

    try:
        try:
            text = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return {"error": f"Cannot read {page_id}: {e}"}
        # Normalize CRLF → LF for consistent frontmatter parsing on Windows
        text = text.replace("\r\n", "\n")

        # Split frontmatter from content using regex for robust --- matching
        # Matches: start-of-file, optional whitespace, ---, newline (LF or CRLF), content, ---, rest
        fm_match = re.match(r"\A\s*---\r?\n(.*?\r?\n)---\r?\n?(.*)", text, re.DOTALL)
        if not fm_match:
            return {"error": f"Invalid frontmatter format in {page_id}"}

        frontmatter_text = fm_match.group(1)

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

        # Reject full frontmatter blocks (---\nkey: val\n---) but allow horizontal rules (---\n)
        stripped_content = updated_content.lstrip()
        if re.match(r"---\n.*?\n?---", stripped_content, re.DOTALL):
            return {"error": "Content looks like a frontmatter block — pass only the body text."}

        # Reconstruct page — strip only leading newlines (preserve indented code blocks).
        # Adversarial-review MAJOR: use [\r\n]+ for defense-in-depth; upstream CRLF→LF
        # normalization at line ~100 handles most cases, but this guard catches any remnants.
        body = re.sub(r"\A[\r\n]+", "", updated_content)
        new_text = f"---\n{frontmatter_text}---\n\n{body}\n"

        # Write the page FIRST — if this fails, no history entry is created.
        try:
            atomic_text_write(new_text, page_path)
        except OSError as e:
            return {"error": f"Failed to write page {page_id}: {e}"}
    finally:
        page_lock.__exit__(None, None, None)

    # Persist audit trail AFTER successful page write (cross-process-safe via file_lock).
    # Adversarial-review MAJOR: derive history path from wiki_dir when history_path is
    # not explicit, so tests calling refine_page(wiki_dir=tmp) don't pollute
    # production .data/review_history.json. Pattern mirrors the project layout:
    # REVIEW_HISTORY_PATH = PROJECT_ROOT / ".data" / "review_history.json"
    # wiki_dir = PROJECT_ROOT / "wiki" → wiki_dir.parent = PROJECT_ROOT.
    if history_path is not None:
        resolved_history_path = history_path
    elif wiki_dir is not None:
        resolved_history_path = wiki_dir.parent / ".data" / "review_history.json"
    else:
        resolved_history_path = REVIEW_HISTORY_PATH
    with file_lock(resolved_history_path):
        history = load_review_history(resolved_history_path)
        history.append(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "page_id": page_id,
                "revision_notes": revision_notes,
                "content_length": len(updated_content),
                "status": "applied",
            }
        )
        if len(history) > MAX_REVIEW_HISTORY_ENTRIES:
            history = history[-MAX_REVIEW_HISTORY_ENTRIES:]
        save_review_history(history, resolved_history_path)

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
