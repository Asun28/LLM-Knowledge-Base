"""Individual lint checks: orphans, dead links, staleness, circular refs, coverage gaps."""

import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import frontmatter
import networkx as nx
import yaml

from kb.compile.linker import resolve_wikilinks
from kb.config import RAW_DIR, SOURCE_TYPE_DIRS, STALENESS_MAX_DAYS, WIKI_DIR
from kb.graph.builder import build_graph, graph_stats, page_id, scan_wiki_pages
from kb.models.frontmatter import validate_frontmatter
from kb.utils.markdown import extract_raw_refs
from kb.utils.pages import normalize_sources
from kb.utils.paths import make_source_ref

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
                "page": broken["source"],
                "target": broken["target"],
                "message": f"Broken wikilink: [[{broken['target']}]] in {broken['source']}",
            }
        )
    return issues


def fix_dead_links(
    wiki_dir: Path | None = None,
    broken_links: list[dict] | None = None,
) -> list[dict]:
    """Fix broken wikilinks by replacing them with plain text.

    ``[[broken/link]]`` becomes ``broken/link`` (basename if path contains ``/``).
    ``[[broken/link|Display Text]]`` becomes ``Display Text``.

    Args:
        wiki_dir: Path to wiki directory.
        broken_links: Pre-computed list of broken link dicts (with 'source' and 'target' keys).
            If None, resolve_wikilinks() is called to compute them (avoids duplicate call
            when run_all_checks already computed the broken links).

    Returns:
        List of dicts: {check, severity, page, target, message} for each fix applied.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    if broken_links is None:
        result = resolve_wikilinks(wiki_dir)
        broken_links = result["broken"]
    fixes: list[dict] = []

    # Group broken links by source page
    broken_by_page: dict[str, list[str]] = {}
    for broken in broken_links:
        broken_by_page.setdefault(broken["source"], []).append(broken["target"])

    for source_pid, targets in broken_by_page.items():
        page_path = wiki_dir / f"{source_pid}.md"
        if not page_path.exists():
            continue

        content = page_path.read_text(encoding="utf-8")
        modified = False

        for target in targets:
            old_content = content

            # Match [[target|display]] or [[target]]
            # Use re.IGNORECASE since extract_wikilinks lowercases targets
            pattern = re.compile(r"\[\[" + re.escape(target) + r"\|([^\]]+)\]\]", re.IGNORECASE)
            if pattern.search(content):
                content = pattern.sub(r"\1", content)
            else:
                # No display text — replace [[target]] with target basename
                pattern_plain = re.compile(r"\[\[" + re.escape(target) + r"\]\]", re.IGNORECASE)
                display = target.split("/")[-1] if "/" in target else target
                content = pattern_plain.sub(display, content)

            # Only record a fix if the content actually changed
            if content != old_content:
                modified = True
                fixes.append(
                    {
                        "check": "dead_link_fixed",
                        "severity": "info",
                        "page": source_pid,
                        "target": target,
                        "message": f"Fixed broken wikilink [[{target}]] in {source_pid}",
                    }
                )

        if modified:
            page_path.write_text(content, encoding="utf-8")

    # Log fixes to audit trail
    if fixes:
        from kb.utils.wiki_log import append_wiki_log

        fixed_count = len(fixes)
        pages_fixed = len({f["page"] for f in fixes})
        append_wiki_log(
            "lint-fix",
            f"Auto-fixed {fixed_count} broken wikilink(s) across {pages_fixed} page(s)",
        )

    return fixes


def check_orphan_pages(wiki_dir: Path | None = None, graph: nx.DiGraph | None = None) -> list[dict]:
    """Find pages with no incoming links (except summaries, which are entry points).

    Returns:
        List of dicts: {page, message}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    if graph is None:
        graph = build_graph(wiki_dir)
    stats = graph_stats(graph)
    issues = []

    # Orphans: have outgoing links but no incoming links
    for orphan in stats["no_inbound"]:
        # Summaries, comparisons, and synthesis are natural entry points, don't flag them
        if orphan.startswith(("summaries/", "comparisons/", "synthesis/")):
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
        if isolated.startswith(("summaries/", "comparisons/", "synthesis/")):
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


def check_cycles(wiki_dir: Path | None = None, graph: nx.DiGraph | None = None) -> list[dict]:
    """Find circular wikilink chains (A → B → C → A).

    Returns:
        List of dicts: {cycle, message}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    if graph is None:
        graph = build_graph(wiki_dir)
    issues = []

    for cycle in nx.simple_cycles(graph):
        if len(cycle) >= 2:
            cycle_str = " → ".join(cycle + [cycle[0]])
            issues.append(
                {
                    "check": "wikilink_cycle",
                    "severity": "info",
                    "cycle": cycle,
                    "message": f"Wikilink cycle detected: {cycle_str}",
                }
            )

    return issues


def check_staleness(
    wiki_dir: Path | None = None,
    max_days: int = STALENESS_MAX_DAYS,
    pages: list[Path] | None = None,
) -> list[dict]:
    """Find pages not updated within max_days.

    Returns:
        List of dicts: {page, last_updated, message}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)
    cutoff = date.today() - timedelta(days=max_days)
    issues = []

    for page_path in pages:
        try:
            post = frontmatter.load(str(page_path))
            updated = post.metadata.get("updated")
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
            if isinstance(updated, date) and updated < cutoff:
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
            elif updated is not None and not isinstance(updated, date):
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


def check_frontmatter(
    wiki_dir: Path | None = None,
    pages: list[Path] | None = None,
) -> list[dict]:
    """Validate frontmatter on all wiki pages.

    Returns:
        List of dicts: {page, errors, message}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    if pages is None:
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
        except (OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError) as e:
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


def check_source_coverage(
    wiki_dir: Path | None = None,
    raw_dir: Path | None = None,
    pages: list[Path] | None = None,
) -> list[dict]:
    """Find raw sources not referenced in any wiki page.

    Returns:
        List of dicts: {source, message}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    raw_dir = raw_dir or RAW_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)

    # Collect all raw references across wiki pages (single pass per file)
    all_raw_refs = set()
    for page_path in pages:
        try:
            content = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read page %s: %s", page_path, e)
            continue
        refs = extract_raw_refs(content)
        all_raw_refs.update(refs)
        try:
            post = frontmatter.loads(content)
            all_raw_refs.update(normalize_sources(post.metadata.get("source")))
        except (ValueError, AttributeError, yaml.YAMLError) as e:
            logger.warning("Failed to parse frontmatter for %s: %s", page_path, e)

    # Find raw sources not referenced
    issues = []
    for _type_name, type_dir in SOURCE_TYPE_DIRS.items():
        actual_dir = raw_dir / type_dir.name
        if not actual_dir.exists():
            continue
        for f in actual_dir.iterdir():
            if f.is_file() and f.name != ".gitkeep":
                rel_path = make_source_ref(f, raw_dir)
                # Check if this source is referenced (exact path only — no suffix match to avoid
                # false-positives when two subdirs contain same-named files)
                referenced = rel_path in all_raw_refs
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


def check_stub_pages(
    wiki_dir: Path | None = None,
    min_content_chars: int = 100,
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
    wiki_dir = wiki_dir or WIKI_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)
    issues = []

    for page_path in pages:
        pid = page_id(page_path, wiki_dir)
        # Skip summaries — they're auto-generated entry points
        if pid.startswith("summaries/"):
            continue
        try:
            post = frontmatter.load(str(page_path))
            body = post.content.strip()
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
