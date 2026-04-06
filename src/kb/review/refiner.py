"""Page refinement — update content preserving frontmatter, log revisions."""

import json
import re
from datetime import date, datetime
from pathlib import Path

from kb.config import REVIEW_HISTORY_PATH, WIKI_DIR


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
    """Save revision history to JSON file."""
    path = path or REVIEW_HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")


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

    # Split frontmatter from content: ---\n<fm>\n---\n<body>
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {"error": f"Invalid frontmatter format in {page_id}"}

    frontmatter_text = parts[1]

    # Update the 'updated' date in frontmatter
    today = date.today().isoformat()
    if re.search(r"updated: \d{4}-\d{2}-\d{2}", frontmatter_text):
        frontmatter_text = re.sub(
            r"updated: \d{4}-\d{2}-\d{2}", f"updated: {today}", frontmatter_text
        )
    else:
        # Add updated field if missing
        frontmatter_text = frontmatter_text.rstrip("\n") + f"\nupdated: {today}\n"

    # Reconstruct page
    new_text = f"---{frontmatter_text}---\n\n{updated_content}\n"
    page_path.write_text(new_text, encoding="utf-8")

    # Append to review history
    history = load_review_history(history_path)
    history.append(
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "page_id": page_id,
            "revision_notes": revision_notes,
        }
    )
    save_review_history(history, history_path)

    # Append to wiki/log.md (create if missing)
    log_path = wiki_dir / "log.md"
    if not log_path.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("# Wiki Log\n\n", encoding="utf-8")
    log_content = log_path.read_text(encoding="utf-8")
    entry = f"- {today} | refine | Refined {page_id}: {revision_notes}\n"
    log_content += entry
    log_path.write_text(log_content, encoding="utf-8")

    return {
        "page_id": page_id,
        "updated": True,
        "revision_notes": revision_notes,
    }
