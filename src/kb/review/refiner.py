"""Page refinement — update content preserving frontmatter, log revisions."""

import json
import re
from datetime import date, datetime
from pathlib import Path

from kb.config import REVIEW_HISTORY_PATH, WIKI_DIR
from kb.utils.wiki_log import append_wiki_log


def load_review_history(path: Path | None = None) -> list[dict]:
    """Load revision history from JSON file."""
    path = path or REVIEW_HISTORY_PATH
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def save_review_history(history: list[dict], path: Path | None = None) -> None:
    """Save revision history to JSON file (atomic write via temp file)."""
    import tempfile

    path = path or REVIEW_HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with open(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        Path(tmp_path).replace(path)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise


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

    if not page_path.exists():
        return {"error": f"Page not found: {page_id}"}

    text = page_path.read_text(encoding="utf-8")

    # Split frontmatter from content using regex for robust --- matching
    # Matches: start-of-file, optional whitespace, ---, newline, content, ---, rest
    fm_match = re.match(r"\A\s*---\n(.*?\n)---\n?(.*)", text, re.DOTALL)
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

    # Ensure updated content doesn't start with frontmatter delimiters
    stripped_content = updated_content.lstrip()
    if stripped_content.startswith("---"):
        return {"error": "Updated content must not start with '---' (frontmatter delimiter)"}

    # Reconstruct page
    new_text = f"---\n{frontmatter_text}---\n\n{updated_content}\n"
    page_path.write_text(new_text, encoding="utf-8")

    # Append to review history with context
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
    save_review_history(history, history_path)

    # Append to wiki/log.md (auto-creates if missing)
    log_path = wiki_dir / "log.md"
    append_wiki_log("refine", f"Refined {page_id}: {revision_notes}", log_path)

    return {
        "page_id": page_id,
        "updated": True,
        "revision_notes": revision_notes,
    }
