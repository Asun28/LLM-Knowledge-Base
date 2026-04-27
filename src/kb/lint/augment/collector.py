"""Stub collection and augment admission gates."""

from __future__ import annotations

import logging
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from kb import config
from kb.graph.builder import build_graph
from kb.lint.checks import check_stub_pages
from kb.utils.pages import load_page_frontmatter

logger = logging.getLogger(__name__)

_ORIGINAL_LOAD_PAGE_FRONTMATTER = load_page_frontmatter

_PLACEHOLDER_TITLE_RE = re.compile(
    r"^(entity-\d+|concept-\d+|placeholder|untitled|tbd|todo)\b",
    re.IGNORECASE,
)


def _package_attr(name: str, fallback: Any) -> Any:
    package = sys.modules.get("kb.lint.augment")
    return getattr(package, name, fallback) if package is not None else fallback


def _load_page_frontmatter(page_path: Path) -> Any:
    package_helper = _package_attr("load_page_frontmatter", _ORIGINAL_LOAD_PAGE_FRONTMATTER)
    if package_helper is not _ORIGINAL_LOAD_PAGE_FRONTMATTER:
        return package_helper(page_path)
    return load_page_frontmatter(page_path)


def _collect_eligible_stubs(*, wiki_dir: Path | None = None) -> list[dict[str, Any]]:
    """Apply admission gates G1-G7 to stub_pages results."""
    wiki_dir = wiki_dir or _package_attr("WIKI_DIR", config.WIKI_DIR)

    stub_issues = check_stub_pages(wiki_dir=wiki_dir)
    if not stub_issues:
        return []

    graph = build_graph(wiki_dir)
    eligible: list[dict[str, Any]] = []

    for issue in stub_issues:
        page_id = issue["page"]

        if page_id.startswith(config.AUTOGEN_PREFIXES):
            continue

        page_path = wiki_dir / f"{page_id}.md"
        if not page_path.exists():
            continue

        try:
            metadata, body = _load_page_frontmatter(page_path)
        except (OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError) as e:
            logger.warning("Skipping unparseable stub %s: %s", page_id, e)
            continue

        title = str(metadata.get("title", "") or "")
        if not title or _PLACEHOLDER_TITLE_RE.match(title.strip()):
            continue
        if metadata.get("confidence") == "speculative":
            continue
        if metadata.get("augment") is False:
            continue

        last_attempt = metadata.get("last_augment_attempted")
        if last_attempt:
            try:
                if isinstance(last_attempt, datetime):
                    last_dt = last_attempt
                else:
                    last_dt = datetime.fromisoformat(str(last_attempt).replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=UTC)
                if datetime.now(UTC) - last_dt < timedelta(hours=config.AUGMENT_COOLDOWN_HOURS):
                    continue
            except (ValueError, TypeError) as e:
                logger.debug("Could not parse last_augment_attempted for %s: %s", page_id, e)

        if not graph.has_node(page_id):
            continue
        non_summary_inbound = [
            src
            for src in graph.predecessors(page_id)
            if not src.startswith(config.AUTOGEN_PREFIXES)
        ]
        if not non_summary_inbound:
            continue

        eligible.append(
            {
                "page_id": page_id,
                "title": title,
                "page_type": metadata.get("type", page_id.split("/")[0].rstrip("s")),
                "frontmatter": dict(metadata),
                "body": body,
                "inbound_count": len(non_summary_inbound),
                "inbound_pages": non_summary_inbound,
            }
        )

    return eligible
