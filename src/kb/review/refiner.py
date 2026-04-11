"""Page refinement — update content preserving frontmatter, log revisions."""

import json
import re
import threading
from datetime import date, datetime
from pathlib import Path

from kb.config import MAX_REVIEW_HISTORY_ENTRIES, REVIEW_HISTORY_PATH, WIKI_DIR
from kb.utils.io import atomic_text_write
from kb.utils.wiki_log import append_wiki_log

_history_lock = threading.Lock()


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
    if re.search(r"updated: \d{4}-\d{2}-\d{2}", frontmatter_text):
        frontmatter_text = re.sub(
            r"updated: \d{4}-\d{2}-\d{2}", f"updated: {today}", frontmatter_text
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

    # Reconstruct page — strip leading whitespace from body for clean output
    new_text = f"---\n{frontmatter_text}---\n\n{updated_content.lstrip()}\n"

    # Write the page FIRST — if this fails, no history entry is created.
    try:
        atomic_text_write(new_text, page_path)
    except OSError as e:
        return {"error": f"Failed to write page {page_id}: {e}"}

    # Persist audit trail AFTER successful page write (thread-safe).
    with _history_lock:
        history = load_review_history(history_path)
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
        save_review_history(history, history_path)

    # Append to wiki/log.md (auto-creates if missing)
    log_path = wiki_dir / "log.md"
    append_wiki_log("refine", f"Refined {page_id}: {revision_notes}", log_path)

    return {
        "page_id": page_id,
        "updated": True,
        "revision_notes": revision_notes,
    }
