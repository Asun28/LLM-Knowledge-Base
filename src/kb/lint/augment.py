"""Augment orchestrator for kb_lint --augment.

Three-gate execution model (see docs/superpowers/specs/2026-04-15-kb-lint-augment-design.md):
  1. propose       — analyze stubs, write proposals to wiki/_augment_proposals.md
  2. --execute     — fetch URLs, save raw files (no ingest)
  3. --auto-ingest — pre-extract at scan tier, ingest, write quality verdict
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import frontmatter

from kb.config import (
    AUGMENT_COOLDOWN_HOURS,
    AUTOGEN_PREFIXES,
    WIKI_DIR,
)
from kb.graph.builder import build_graph
from kb.lint.checks import check_stub_pages

logger = logging.getLogger(__name__)

Mode = Literal["propose", "execute", "auto_ingest"]

# Placeholder-title regex: rejects entity-N, placeholder-foo, etc.
_PLACEHOLDER_TITLE_RE = re.compile(
    r"^(entity-\d+|concept-\d+|placeholder|untitled|tbd|todo)\b",
    re.IGNORECASE,
)


def _collect_eligible_stubs(*, wiki_dir: Path | None = None) -> list[dict[str, Any]]:
    """Apply admission gates G1-G7 to stub_pages results.

    Returns list of {page_id, title, page_type, frontmatter, body, inbound_count,
    inbound_pages} for eligible stubs.
    """
    wiki_dir = wiki_dir or WIKI_DIR

    stub_issues = check_stub_pages(wiki_dir=wiki_dir)
    if not stub_issues:
        return []

    graph = build_graph(wiki_dir)
    eligible: list[dict[str, Any]] = []

    for issue in stub_issues:
        page_id = issue["page"]

        # G7 autogen prefix
        if page_id.startswith(AUTOGEN_PREFIXES):
            continue

        page_path = wiki_dir / f"{page_id}.md"
        if not page_path.exists():
            continue

        try:
            post = frontmatter.load(str(page_path))
        except (OSError, ValueError, UnicodeDecodeError) as e:
            logger.warning("Skipping unparseable stub %s: %s", page_id, e)
            continue

        title = str(post.metadata.get("title", "") or "")

        # G1 placeholder title
        if not title or _PLACEHOLDER_TITLE_RE.match(title.strip()):
            continue

        # G3 confidence ≠ speculative
        if post.metadata.get("confidence") == "speculative":
            continue

        # G4 per-page opt-out
        if post.metadata.get("augment") is False:
            continue

        # G6 cooldown
        last_attempt = post.metadata.get("last_augment_attempted")
        if last_attempt:
            try:
                if isinstance(last_attempt, datetime):
                    last_dt = last_attempt
                else:
                    last_dt = datetime.fromisoformat(str(last_attempt).replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=UTC)
                if datetime.now(UTC) - last_dt < timedelta(hours=AUGMENT_COOLDOWN_HOURS):
                    continue
            except (ValueError, TypeError) as e:
                logger.debug("Could not parse last_augment_attempted for %s: %s", page_id, e)

        # G2 inbound link from non-summary/non-autogen page
        # graph predecessors are page IDs of pages that link TO this page
        if not graph.has_node(page_id):
            continue
        non_summary_inbound = [
            src for src in graph.predecessors(page_id)
            if not src.startswith(AUTOGEN_PREFIXES)
        ]
        if not non_summary_inbound:
            continue

        eligible.append({
            "page_id": page_id,
            "title": title,
            "page_type": post.metadata.get("type", page_id.split("/")[0].rstrip("s")),
            "frontmatter": dict(post.metadata),
            "body": post.content,
            "inbound_count": len(non_summary_inbound),
            "inbound_pages": non_summary_inbound,
        })

    return eligible
