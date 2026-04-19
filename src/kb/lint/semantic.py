"""Semantic lint checks — build contexts for LLM-powered quality evaluation."""

import logging
from pathlib import Path

import frontmatter
import networkx as nx
import yaml

from kb.config import (
    MAX_CONSISTENCY_GROUP_SIZE,
    MAX_CONSISTENCY_GROUPS,
    MAX_CONSISTENCY_PAGE_CONTENT_CHARS,
    MIN_SHARED_TERMS,
    QUERY_CONTEXT_MAX_CHARS,
    WIKI_DIR,
)
from kb.graph.builder import build_graph
from kb.review.context import pair_page_with_sources
from kb.utils.markdown import FRONTMATTER_RE as _FRONTMATTER_RE
from kb.utils.pages import normalize_sources, page_id, scan_wiki_pages

logger = logging.getLogger(__name__)


def _truncate_source(content: str, budget: int) -> str:
    """Truncate source content to fit within a character budget."""
    if len(content) <= budget:
        return content
    return content[:budget] + f"\n\n[... truncated from {len(content):,} to {budget:,} chars]\n"


_MIN_SOURCE_CHARS = 500  # Phase 4.5 HIGH L6: per-source minimum floor


def _render_sources(sources: list[dict], lines: list[str]) -> None:
    """Append source sections to lines with budget-aware truncation.

    Mutates `lines` in place. Tracks cumulative size so later sources
    get progressively less budget — prevents LLM context overflow.
    Phase 4.5 HIGH L6: enforces minimum floor per source so large wiki pages
    don't starve source context entirely (budget=0 previously passed through).
    """
    used = sum(len(line) for line in lines) + max(0, len(lines) - 1)
    for i, source in enumerate(sources, 1):
        if used >= QUERY_CONTEXT_MAX_CHARS:
            break  # PR review fix: prevent MIN_SOURCE_CHARS from overflowing total cap
        header = f"## Source {i}: {source['path']}\n"
        if source.get("content"):
            remaining = max(
                _MIN_SOURCE_CHARS,
                QUERY_CONTEXT_MAX_CHARS - used - len(header) - 20,
            )
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


def _group_by_shared_sources(wiki_dir: Path, *, pages: list[dict] | None = None) -> list[list[str]]:
    """Group pages that share raw sources (from frontmatter source: fields).

    Cycle 7 AC19: ``pages=`` kwarg lets callers pass a pre-loaded page bundle
    to skip the ``scan_wiki_pages`` + ``frontmatter.load`` pass.
    """
    source_to_pages: dict[str, list[str]] = {}

    if pages is not None:
        # Pre-loaded bundle: id, content (frontmatter parsed per call).
        for p in pages:
            try:
                content = p.get("content", "")
                post = frontmatter.loads(content)
                sources = normalize_sources(post.metadata.get("source"))
                for src in sources:
                    source_to_pages.setdefault(src, []).append(p["id"])
            except (ValueError, AttributeError, yaml.YAMLError) as e:
                logger.warning("Failed to parse frontmatter for %s: %s", p.get("id"), e)
                continue
    else:
        page_paths = scan_wiki_pages(wiki_dir)
        for page_path in page_paths:
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


def _group_by_wikilinks(wiki_dir: Path, *, pages: list[dict] | None = None) -> list[list[str]]:
    """Group pages connected by wikilinks (connected components in the undirected graph).

    Cycle 7 AC19: ``pages=`` threaded through to ``build_graph`` to skip scan.
    """
    graph = build_graph(wiki_dir, pages=pages)
    components = list(nx.connected_components(graph.to_undirected()))
    return [sorted(c) for c in components if len(c) >= 2]


def _group_by_term_overlap(wiki_dir: Path, *, pages: list[dict] | None = None) -> list[list[str]]:
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
    page_terms: dict[str, set[str]] = {}

    def _terms_from_body(body: str) -> set[str]:
        return {
            stripped
            for w in body.lower().split()
            if len(stripped := w.strip(".,!?()[]{}\"':-/")) > 4
        } - common_words

    if pages is not None:
        # Cycle 7 AC19: reuse pre-loaded bundle.
        for p in pages:
            raw = p.get("content", "")
            fm_match = _FRONTMATTER_RE.match(raw)
            body = fm_match.group(2) if fm_match else raw
            page_terms[p["id"]] = _terms_from_body(body)
    else:
        page_paths = scan_wiki_pages(wiki_dir)
        for page_path in page_paths:
            try:
                raw = page_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Skipping unreadable page %s in term overlap: %s", page_path, e)
                continue
            pid = page_id(page_path, wiki_dir)
            # Phase 4.5 HIGH L7: use shared FRONTMATTER_RE and group(2) for body text.
            # Previous code used group(1) which captured the frontmatter fence, causing
            # consistency grouping to tokenize YAML keys instead of body content.
            fm_match = _FRONTMATTER_RE.match(raw)
            body = fm_match.group(2) if fm_match else raw
            page_terms[pid] = _terms_from_body(body)

    # Phase 4.5 HIGH L2: inverted postings index replaces O(n^2) pairwise loop.
    # No 500-page wall — this is O(T * avg_pages_per_term) which scales linearly.
    term_to_pages: dict[str, list[str]] = {}
    for pid, terms in page_terms.items():
        for term in terms:
            if term not in term_to_pages:
                term_to_pages[term] = []
            term_to_pages[term].append(pid)

    # Count shared terms per page pair via the inverted index
    from collections import Counter

    pair_counts: Counter[tuple[str, str]] = Counter()
    for term, pids in term_to_pages.items():
        if len(pids) > 200:
            continue  # Skip extremely common terms (noise)
        for i, a in enumerate(pids):
            for b in pids[i + 1 :]:
                pair = (a, b) if a < b else (b, a)
                pair_counts[pair] += 1

    groups = [
        sorted(list(pair)) for pair, count in pair_counts.items() if count >= MIN_SHARED_TERMS
    ]
    return groups


def build_consistency_context(
    page_ids: list[str] | None = None,
    wiki_dir: Path | None = None,
    raw_dir: Path | None = None,
    *,
    pages: list[dict] | None = None,
) -> str:
    """Build cross-page consistency check context.

    If page_ids is provided, uses them as a single group.
    Otherwise, auto-selects groups using shared sources and wikilinks, chunks
    large groups, caps total emitted groups, strips frontmatter from page
    bodies, and truncates each inlined body to the configured auto-mode limit.

    Returns formatted text for Claude Code to check for contradictions.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    auto_mode = page_ids is None

    if page_ids:
        all_chunks = [
            page_ids[i : i + MAX_CONSISTENCY_GROUP_SIZE]
            for i in range(0, len(page_ids), MAX_CONSISTENCY_GROUP_SIZE)
        ]
        groups = [chunk for chunk in all_chunks if len(chunk) >= 2]
    else:
        # Auto-select using three strategies (priority order per spec).
        # Cycle 7 AC19: thread `pages=` into each grouper so they skip the
        # scan_wiki_pages walk when the caller provided a pre-loaded bundle.
        all_groups: list[list[str]] = []
        all_groups.extend(_group_by_shared_sources(wiki_dir, pages=pages))
        all_groups.extend(_group_by_wikilinks(wiki_dir, pages=pages))
        all_groups.extend(_group_by_term_overlap(wiki_dir, pages=pages))

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
        if len(groups) > MAX_CONSISTENCY_GROUPS:
            dropped = len(groups) - MAX_CONSISTENCY_GROUPS
            logger.info(
                "Dropping %d consistency group(s) above cap=%d",
                dropped,
                MAX_CONSISTENCY_GROUPS,
            )
            groups = groups[:MAX_CONSISTENCY_GROUPS]

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
                if auto_mode:
                    fm_match = _FRONTMATTER_RE.match(content)
                    content = fm_match.group(2) if fm_match else content
                    if len(content) > MAX_CONSISTENCY_PAGE_CONTENT_CHARS:
                        content = (
                            content[:MAX_CONSISTENCY_PAGE_CONTENT_CHARS]
                            + f"\n\n[Truncated at {MAX_CONSISTENCY_PAGE_CONTENT_CHARS} "
                            "chars — run kb_lint_deep for full body]"
                        )
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
