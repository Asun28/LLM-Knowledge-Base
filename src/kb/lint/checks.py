"""Individual lint checks: orphans, dead links, staleness, circular refs, coverage gaps."""

import logging
from datetime import date, timedelta
from pathlib import Path

import frontmatter

from kb.compile.linker import resolve_wikilinks
from kb.config import RAW_DIR, SOURCE_TYPE_DIRS, STALENESS_MAX_DAYS, WIKI_DIR
from kb.graph.builder import build_graph, graph_stats, page_id, scan_wiki_pages
from kb.models.frontmatter import validate_frontmatter
from kb.utils.markdown import extract_raw_refs

logger = logging.getLogger(__name__)


def check_dead_links(wiki_dir: Path | None = None) -> list[dict]:
    """Find wikilinks pointing to non-existent pages.

    Returns:
        List of dicts: {source, target, message}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    result = resolve_wikilinks(wiki_dir)
    issues = []
    for broken in result["broken"]:
        issues.append(
            {
                "check": "dead_link",
                "severity": "error",
                "source": broken["source"],
                "target": broken["target"],
                "message": f"Broken wikilink: [[{broken['target']}]] in {broken['source']}",
            }
        )
    return issues


def check_orphan_pages(wiki_dir: Path | None = None) -> list[dict]:
    """Find pages with no incoming links (except summaries, which are entry points).

    Returns:
        List of dicts: {page, message}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    graph = build_graph(wiki_dir)
    stats = graph_stats(graph)
    issues = []

    # Orphans: have outgoing links but no incoming links
    for orphan in stats["orphans"]:
        # Summaries are natural entry points, don't flag them
        if orphan.startswith("summaries/"):
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
        issues.append(
            {
                "check": "isolated_page",
                "severity": "warning",
                "page": isolated,
                "message": f"Isolated page (no links at all): {isolated}",
            }
        )

    return issues


def check_staleness(wiki_dir: Path | None = None, max_days: int = STALENESS_MAX_DAYS) -> list[dict]:
    """Find pages not updated within max_days.

    Returns:
        List of dicts: {page, last_updated, message}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    pages = scan_wiki_pages(wiki_dir)
    cutoff = date.today() - timedelta(days=max_days)
    issues = []

    for page_path in pages:
        try:
            post = frontmatter.load(str(page_path))
            updated = post.metadata.get("updated")
            if updated and isinstance(updated, date) and updated < cutoff:
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
        except Exception as e:
            logger.warning("Failed to load wiki page %s: %s", page_path, e)
            continue

    return issues


def check_frontmatter(wiki_dir: Path | None = None) -> list[dict]:
    """Validate frontmatter on all wiki pages.

    Returns:
        List of dicts: {page, errors, message}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    pages = scan_wiki_pages(wiki_dir)
    issues = []

    for page_path in pages:
        try:
            post = frontmatter.load(str(page_path))
            errors = validate_frontmatter(post)
            if errors:
                pid = page_id(page_path, wiki_dir)
                issues.append(
                    {
                        "check": "frontmatter",
                        "severity": "error",
                        "page": pid,
                        "errors": errors,
                        "message": f"Frontmatter issues in {pid}: {'; '.join(errors)}",
                    }
                )
        except Exception as e:
            pid = page_id(page_path, wiki_dir)
            issues.append(
                {
                    "check": "frontmatter",
                    "severity": "error",
                    "page": pid,
                    "errors": [str(e)],
                    "message": f"Failed to parse frontmatter in {pid}: {e}",
                }
            )

    return issues


def check_source_coverage(wiki_dir: Path | None = None, raw_dir: Path | None = None) -> list[dict]:
    """Find raw sources not referenced in any wiki page.

    Returns:
        List of dicts: {source, message}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    raw_dir = raw_dir or RAW_DIR
    pages = scan_wiki_pages(wiki_dir)

    # Collect all raw references across wiki pages
    all_raw_refs = set()
    for page_path in pages:
        content = page_path.read_text(encoding="utf-8")
        refs = extract_raw_refs(content)
        all_raw_refs.update(refs)

    # Also check frontmatter source fields
    for page_path in pages:
        try:
            post = frontmatter.load(str(page_path))
            sources = post.metadata.get("source", [])
            if isinstance(sources, list):
                all_raw_refs.update(sources)
            elif isinstance(sources, str):
                all_raw_refs.add(sources)
        except Exception as e:
            logger.warning("Failed to load frontmatter for %s: %s", page_path, e)
            continue

    # Find raw sources not referenced
    issues = []
    for _type_name, type_dir in SOURCE_TYPE_DIRS.items():
        actual_dir = raw_dir / type_dir.name
        if not actual_dir.exists():
            continue
        for f in actual_dir.iterdir():
            if f.is_file() and f.name != ".gitkeep":
                rel_path = f"raw/{type_dir.name}/{f.name}"
                # Check if this source is referenced (partial match)
                referenced = any(rel_path in ref or f.name in ref for ref in all_raw_refs)
                if not referenced:
                    issues.append(
                        {
                            "check": "source_coverage",
                            "severity": "warning",
                            "source": rel_path,
                            "message": f"Raw source not referenced in wiki: {rel_path}",
                        }
                    )

    return issues
