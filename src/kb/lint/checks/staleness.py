"""Staleness lint checks."""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from kb.lint import checks
from kb.lint.checks.frontmatter import _effective_max_days
from kb.utils.pages import load_page_frontmatter, page_id, scan_wiki_pages

logger = logging.getLogger(__name__)


def check_staleness(
    wiki_dir: Path | None = None,
    max_days: int | None = None,
    pages: list[Path] | None = None,
) -> list[dict]:
    """Find pages whose ``updated`` date exceeds their decay window.

    Cycle 15 AC4 — when ``max_days`` is ``None`` (default), the per-page
    threshold is computed from the page's source list via
    ``decay_days_for(source, topics=...)`` with lenient max-over-sources.
    An explicit ``max_days`` override (e.g. ``max_days=30`` from a test)
    still forces every page to use the caller-supplied window.

    Returns:
        List of dicts: {page, last_updated, message}.
    """
    wiki_dir = wiki_dir or checks.WIKI_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)
    today = date.today()
    issues = []

    for page_path in pages:
        try:
            metadata, body = load_page_frontmatter(page_path)
            del body
            updated = metadata.get("updated")
            if isinstance(updated, str):
                if not updated:
                    updated = None
                else:
                    try:
                        updated = date.fromisoformat(updated)
                    except ValueError:
                        logger.warning("Could not parse updated date %r in %s", updated, page_path)
                        continue
            if isinstance(updated, datetime):
                updated = updated.date()
            if updated is None:
                pid = page_id(page_path, wiki_dir)
                issues.append(
                    {
                        "check": "staleness",
                        "severity": "warning",
                        "page": pid,
                        "message": f"Page {pid} has no updated date — cannot determine staleness.",
                    }
                )
                continue
            if isinstance(updated, date):
                # Cycle 15 AC4 — per-page cutoff unless caller overrides.
                per_page_days = max_days if max_days is not None else _effective_max_days(metadata)
                cutoff = today - timedelta(days=per_page_days)
                if updated < cutoff:
                    pid = page_id(page_path, wiki_dir)
                    issues.append(
                        {
                            "check": "stale_page",
                            "severity": "info",
                            "page": pid,
                            "last_updated": updated.isoformat(),
                            "message": f"Stale page (last updated {updated}): {pid}",
                        }
                    )
                # else: fresh page — no issue
            else:
                # YAML parsed the field as a non-date type (integer, list, etc.).
                # Unlikely in practice but treat as a warning for safety.
                pid = page_id(page_path, wiki_dir)
                issues.append(
                    {
                        "check": "staleness",
                        "severity": "warning",
                        "page": pid,
                        "message": (
                            f"Page {pid} has unrecognised updated type: {type(updated).__name__}"
                        ),
                    }
                )
        except (OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError) as e:
            logger.warning("Failed to load wiki page %s: %s", page_path, e)
            continue

    return issues
