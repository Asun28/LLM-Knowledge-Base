"""Semantic lint checks — build contexts for LLM-powered quality evaluation."""

import logging
import re
from pathlib import Path

import frontmatter
import networkx as nx
import yaml

from kb.config import (
    MAX_CONSISTENCY_GROUP_SIZE,
    MIN_SHARED_TERMS,
    QUERY_CONTEXT_MAX_CHARS,
    WIKI_DIR,
)
from kb.graph.builder import build_graph, page_id, scan_wiki_pages
from kb.review.context import pair_page_with_sources
from kb.utils.pages import normalize_sources

logger = logging.getLogger(__name__)


def _truncate_source(content: str, budget: int) -> str:
    """Truncate source content to fit within a character budget."""
    if len(content) <= budget:
        return content
    return content[:budget] + f"\n\n[... truncated from {len(content):,} to {budget:,} chars]\n"


def _render_sources(sources: list[dict], lines: list[str]) -> None:
    """Append source sections to lines with budget-aware truncation.

    Mutates `lines` in place. Tracks cumulative size so later sources
    get progressively less budget — prevents LLM context overflow.
    """
    used = sum(len(line) for line in lines) + max(0, len(lines) - 1)
    for i, source in enumerate(sources, 1):
        header = f"## Source {i}: {source['path']}\n"
        if source.get("content"):
            remaining = max(0, QUERY_CONTEXT_MAX_CHARS - used - len(header) - 20)
            body = _truncate_source(source["content"], remaining)
        else:
            body = f"*Not available: {source.get('error', 'unknown')}*"
        lines.append(header)
        lines.append(body)
        lines.append("\n---\n")
        used += len(header) + len(body) + 6


def build_fidelity_context(
    page_id_str: str, wiki_dir: Path | None = None, raw_dir: Path | None = None
) -> str:
    """Build source fidelity check context: page content paired with source content.

    Returns formatted text for Claude Code to evaluate whether each claim
    in the wiki page traces to a specific passage in the raw source(s).
    """
    paired = pair_page_with_sources(page_id_str, wiki_dir, raw_dir)

    if "error" in paired and "page_content" not in paired:
        return f"Error: {paired['error']}"

    lines = [
        f"# Source Fidelity Check: {page_id_str}\n",
        "Evaluate whether each factual claim in the wiki page can be traced "
        "to a specific passage in the raw source(s).\n",
        "---\n",
        "## Wiki Page\n",
        paired["page_content"],
        "\n---\n",
    ]

    _render_sources(paired["source_contents"], lines)

    lines.append(
        "For each factual claim in the wiki page, identify whether it is:\n"
        "- **Traced**: directly supported by a passage in the source\n"
        "- **Inferred**: reasonably deduced from the source but not stated\n"
        "- **Unsourced**: not found in the source material\n"
    )

    return "\n".join(lines)


def _group_by_shared_sources(wiki_dir: Path) -> list[list[str]]:
    """Group pages that share raw sources (from frontmatter source: fields)."""
    pages = scan_wiki_pages(wiki_dir)
    source_to_pages: dict[str, list[str]] = {}

    for page_path in pages:
        try:
            post = frontmatter.load(str(page_path))
            pid = page_id(page_path, wiki_dir)
            sources = normalize_sources(post.metadata.get("source"))
            for src in sources:
                source_to_pages.setdefault(src, []).append(pid)
        except (OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError) as e:
            logger.warning("Failed to load frontmatter for %s: %s", page_path, e)
            continue

    return [pids for pids in source_to_pages.values() if len(pids) >= 2]


def _group_by_wikilinks(wiki_dir: Path) -> list[list[str]]:
    """Group pages connected by wikilinks (connected components in the undirected graph)."""
    graph = build_graph(wiki_dir)
    components = list(nx.connected_components(graph.to_undirected()))
    return [sorted(c) for c in components if len(c) >= 2]


def _group_by_term_overlap(wiki_dir: Path) -> list[list[str]]:
    """Group pages with high term overlap (>= 3 shared significant terms)."""
    # Common English words that pass the length filter but carry no semantic signal
    common_words = {
        "about",
        "after",
        "again",
        "along",
        "based",
        "because",
        "before",
        "being",
        "between",
        "called",
        "could",
        "different",
        "during",
        "early",
        "every",
        "example",
        "first",
        "found",
        "great",
        "https",
        "index",
        "known",
        "large",
        "later",
        "level",
        "likely",
        "model",
        "never",
        "often",
        "other",
        "point",
        "right",
        "since",
        "small",
        "state",
        "still",
        "their",
        "there",
        "these",
        "thing",
        "those",
        "through",
        "title",
        "under",
        "until",
        "using",
        "value",
        "where",
        "which",
        "while",
        "would",
        "should",
        "above",
        "below",
        "might",
        "source",
        "content",
        "created",
        "updated",
        "stated",
    }
    pages = scan_wiki_pages(wiki_dir)
    page_terms: dict[str, set[str]] = {}

    for page_path in pages:
        try:
            raw = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Skipping unreadable page %s in term overlap: %s", page_path, e)
            continue
        pid = page_id(page_path, wiki_dir)
        # Strip YAML frontmatter before tokenizing (handle both LF and CRLF line endings)
        fm_match = re.match(r"\A\s*---\r?\n.*?\r?\n---\r?\n?(.*)", raw, re.DOTALL)
        body = fm_match.group(1) if fm_match else raw
        words = {
            stripped
            for w in body.lower().split()
            if len(stripped := w.strip(".,!?()[]{}\"':-/")) > 4
        } - common_words
        page_terms[pid] = words

    groups = []
    page_ids_list = list(page_terms.keys())

    _MAX_OVERLAP_PAGES = 500
    if len(page_ids_list) > _MAX_OVERLAP_PAGES:
        logger.info(
            "Skipping O(n^2) term-overlap grouping for %d pages (limit=%d)",
            len(page_ids_list),
            _MAX_OVERLAP_PAGES,
        )
        return []

    # j > i loop structure already prevents duplicates — no seen_pairs set needed
    for i, pid_a in enumerate(page_ids_list):
        for pid_b in page_ids_list[i + 1 :]:
            shared = page_terms[pid_a] & page_terms[pid_b]
            if len(shared) >= MIN_SHARED_TERMS:
                groups.append(sorted([pid_a, pid_b]))

    return groups


def build_consistency_context(
    page_ids: list[str] | None = None,
    wiki_dir: Path | None = None,
    raw_dir: Path | None = None,
) -> str:
    """Build cross-page consistency check context.

    If page_ids is provided, uses them as a single group.
    Otherwise, auto-selects groups using shared sources and wikilinks.

    Returns formatted text for Claude Code to check for contradictions.
    """
    wiki_dir = wiki_dir or WIKI_DIR

    if page_ids:
        all_chunks = [
            page_ids[i : i + MAX_CONSISTENCY_GROUP_SIZE]
            for i in range(0, len(page_ids), MAX_CONSISTENCY_GROUP_SIZE)
        ]
        groups = [chunk for chunk in all_chunks if len(chunk) >= 2]
    else:
        # Auto-select using three strategies (priority order per spec)
        all_groups: list[list[str]] = []
        all_groups.extend(_group_by_shared_sources(wiki_dir))
        all_groups.extend(_group_by_wikilinks(wiki_dir))
        all_groups.extend(_group_by_term_overlap(wiki_dir))

        # Deduplicate by sorted tuple
        seen: set[tuple[str, ...]] = set()
        deduped = []
        for group in all_groups:
            key = tuple(sorted(group))
            if key not in seen:
                seen.add(key)
                deduped.append(list(key))

        # Apply size cap — chunk large groups so no group exceeds MAX_CONSISTENCY_GROUP_SIZE
        groups = []
        for g in deduped:
            for i in range(0, len(g), MAX_CONSISTENCY_GROUP_SIZE):
                chunk = g[i : i + MAX_CONSISTENCY_GROUP_SIZE]
                if len(chunk) >= 2:
                    groups.append(chunk)

    if not groups:
        return "No page groups found for consistency checking."

    lines = [
        "# Cross-Page Consistency Check\n",
        f"Found {len(groups)} group(s) of related pages to check for contradictions.\n",
        "For each group, identify any claims that contradict each other.\n",
    ]

    for gi, group in enumerate(groups, 1):
        lines.append(f"## Group {gi} ({len(group)} pages)\n")
        for pid in group:
            page_path = wiki_dir / f"{pid}.md"
            if page_path.exists():
                try:
                    content = page_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as e:
                    lines.append(f"### {pid}\n*Unreadable: {e}*\n---\n")
                    continue
                lines.append(f"### {pid}\n")
                lines.append(content)
                lines.append("\n---\n")
            else:
                lines.append(f"### {pid}\n*Page not found*\n---\n")

    return "\n".join(lines)


def build_completeness_context(
    page_id_str: str, wiki_dir: Path | None = None, raw_dir: Path | None = None
) -> str:
    """Build completeness check context: source alongside page for gap detection.

    Returns formatted text for Claude Code to identify key claims from the
    source that are NOT represented in the wiki page.
    """
    paired = pair_page_with_sources(page_id_str, wiki_dir, raw_dir)

    if "error" in paired and "page_content" not in paired:
        return f"Error: {paired['error']}"

    lines = [
        f"# Completeness Check: {page_id_str}\n",
        "Evaluate whether key claims from the raw source(s) are represented "
        "in the wiki page. Identify important omissions.\n",
        "---\n",
        "## Wiki Page\n",
        paired["page_content"],
        "\n---\n",
    ]

    _render_sources(paired["source_contents"], lines)

    lines.append(
        "List any key claims, facts, or arguments from the source(s) that are "
        "NOT represented in the wiki page.\n"
    )

    return "\n".join(lines)
