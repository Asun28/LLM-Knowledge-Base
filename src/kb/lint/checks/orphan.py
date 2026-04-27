"""Orphan and stub page lint checks."""

import logging
from pathlib import Path

import networkx as nx
import yaml

from kb.config import AUTOGEN_PREFIXES, STUB_MIN_CONTENT_CHARS
from kb.graph.builder import build_graph, graph_stats
from kb.lint import checks
from kb.lint.checks.dead_links import _INDEX_FILES
from kb.utils.markdown import extract_wikilinks
from kb.utils.pages import load_page_frontmatter, page_id, scan_wiki_pages

logger = logging.getLogger(__name__)


def check_orphan_pages(wiki_dir: Path | None = None, graph: nx.DiGraph | None = None) -> list[dict]:
    """Find pages with no incoming links (except summaries, which are entry points).

    Returns:
        List of dicts: {page, message}.
    """
    wiki_dir = wiki_dir or checks.WIKI_DIR
    if graph is None:
        graph = build_graph(wiki_dir)
    else:
        graph = graph.copy()  # fix item 8: don't mutate the caller's shared graph

    # Augment graph with backlinks from index/log files — these are not wiki pages
    # (not in any subdir) so build_graph skips them, causing false orphan reports.
    existing_ids = set(graph.nodes())
    # Cycle 3 H13: track corrupt index files so we can surface them as
    # error-severity lint issues. The prior `errors="replace"` silently
    # substituted U+FFFD, letting `extract_wikilinks` drop corrupted targets
    # and report innocent pages as orphans.
    _corrupt_index_issues: list[dict] = []
    for name in _INDEX_FILES:
        idx_path = wiki_dir / name
        if not idx_path.exists():
            continue
        try:
            text = idx_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            # H13: the file is on disk but not UTF-8. Emit an explicit error so
            # the operator sees the corruption instead of guessing why the
            # orphan list grew. We do NOT abort the full check — other index
            # files are still processed.
            _corrupt_index_issues.append(
                {
                    "check": "corrupt_index_file",
                    "severity": "error",
                    "page": name,
                    "message": (
                        f"Index file {name} is not valid UTF-8 — please inspect "
                        f"and re-save; orphan detection may be inaccurate until fixed "
                        f"({exc.reason} at byte {exc.start})"
                    ),
                }
            )
            continue
        except OSError:
            continue
        for target in extract_wikilinks(text):
            if target in existing_ids:
                # Add a virtual edge from "_index:<name>" sentinel to the target.
                # The sentinel node is added on demand. It has in-degree 0 and
                # out-degree ≥ 1, so graph_stats() puts it in no_inbound; the
                # orphan/isolated loops below skip it via the "_index:" prefix guard.
                sentinel = f"_index:{name}"
                if not graph.has_node(sentinel):
                    graph.add_node(sentinel)
                graph.add_edge(sentinel, target)

    stats = graph_stats(graph)
    issues = list(_corrupt_index_issues)  # H13: surface corrupt indexes first

    # Orphans: have outgoing links but no incoming links
    for orphan in stats["no_inbound"]:
        # Summaries, comparisons, and synthesis are natural entry points, don't flag them
        if orphan.startswith(AUTOGEN_PREFIXES):
            continue
        if orphan.startswith("_index:"):  # virtual sentinel nodes from index augmentation
            continue
        issues.append(
            {
                "check": "orphan_page",
                "severity": "warning",
                "page": orphan,
                "message": f"Orphan page (no incoming links): {orphan}",
            }
        )

    # Isolated: no links at all (neither in nor out)
    for isolated in stats["isolated"]:
        # Summaries, comparisons, and synthesis are natural entry points, don't flag them
        if isolated.startswith(AUTOGEN_PREFIXES):
            continue
        if isolated.startswith("_index:"):  # virtual sentinel nodes from index augmentation
            continue
        issues.append(
            {
                "check": "isolated_page",
                "severity": "warning",
                "page": isolated,
                "message": f"Isolated page (no links at all): {isolated}",
            }
        )

    return issues


def check_stub_pages(
    wiki_dir: Path | None = None,
    min_content_chars: int = STUB_MIN_CONTENT_CHARS,
    pages: list[Path] | None = None,
) -> list[dict]:
    """Find wiki pages with minimal body content (stubs needing enrichment).

    A stub is a page where the body content (after frontmatter) is less than
    min_content_chars characters. Summaries are excluded since they're auto-generated.

    Args:
        wiki_dir: Path to wiki directory.
        min_content_chars: Minimum chars for non-stub content. Default 100.
        pages: Pre-scanned list of page paths. If None, scan_wiki_pages() is called.

    Returns:
        List of dicts: {page, content_length, message}.
    """
    wiki_dir = wiki_dir or checks.WIKI_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)
    issues = []

    for page_path in pages:
        pid = page_id(page_path, wiki_dir)
        # Skip autogen pages — they're natural entry points, not stubs to enrich
        if pid.startswith(AUTOGEN_PREFIXES):
            continue
        try:
            metadata, body = load_page_frontmatter(page_path)
            del metadata
            body = body.strip()
            if len(body) < min_content_chars:
                issues.append(
                    {
                        "check": "stub_page",
                        "severity": "info",
                        "page": pid,
                        "content_length": len(body),
                        "message": (
                            f"Stub page ({len(body)} chars): {pid} — "
                            "consider enriching with more content"
                        ),
                    }
                )
        except (OSError, ValueError, AttributeError, UnicodeDecodeError, yaml.YAMLError) as e:
            logger.warning("Failed to check stub status for %s: %s", page_path, e)
            continue

    return issues
