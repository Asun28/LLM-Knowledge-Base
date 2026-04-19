"""Individual lint checks: orphans, dead links, staleness, circular refs, coverage gaps."""

import itertools
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import frontmatter
import networkx as nx
import yaml

from kb.compile.linker import _mask_code_blocks, _unmask_code_blocks, resolve_wikilinks
from kb.config import (
    AUTOGEN_PREFIXES,
    RAW_DIR,
    SOURCE_TYPE_DIRS,
    STALENESS_MAX_DAYS,
    STUB_MIN_CONTENT_CHARS,
    SUPPORTED_SOURCE_EXTENSIONS,
    WIKI_DIR,
)
from kb.graph.builder import build_graph, graph_stats
from kb.models.frontmatter import validate_frontmatter
from kb.utils.io import atomic_text_write
from kb.utils.markdown import extract_raw_refs, extract_wikilinks
from kb.utils.pages import normalize_sources, page_id, scan_wiki_pages
from kb.utils.paths import make_source_ref

logger = logging.getLogger(__name__)


def check_dead_links(wiki_dir: Path | None = None) -> list[dict]:
    """Find wikilinks pointing to non-existent pages.

    Cycle 7 AC18: ``[[index]]`` / ``[[_sources]]`` / ``[[log]]`` wikilinks are
    not dead when the corresponding root-level file exists. ``scan_wiki_pages``
    only walks ``WIKI_SUBDIRS`` and thus never includes root index files in
    ``existing_ids`` — without this filter every page linking ``[[index]]``
    generates a false-positive dead-link issue.

    Returns:
        List of dicts: {source, target, message}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    result = resolve_wikilinks(wiki_dir)

    # Stem → filename map for root files that count as valid link targets.
    _ROOT_TARGETS = {name.removesuffix(".md"): name for name in _INDEX_FILES}

    issues = []
    for broken in result["broken"]:
        target = broken["target"]
        # AC18: honour root-level index files if present on disk.
        if target in _ROOT_TARGETS and (wiki_dir / _ROOT_TARGETS[target]).is_file():
            continue
        issues.append(
            {
                "check": "dead_link",
                "severity": "error",
                "page": broken["source"],
                "target": target,
                "message": f"Broken wikilink: [[{target}]] in {broken['source']}",
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
        # Mask code blocks to prevent modifying wikilinks inside code examples
        content, masked_code, mask_prefix = _mask_code_blocks(content)
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

        # Unmask code blocks before writing
        content = _unmask_code_blocks(content, masked_code, mask_prefix)
        if modified:
            atomic_text_write(content, page_path)

    # Log fixes to audit trail
    if fixes:
        from kb.config import WIKI_DIR as _WIKI_DIR
        from kb.utils.wiki_log import append_wiki_log

        fixed_count = len(fixes)
        pages_fixed = len({f["page"] for f in fixes})
        effective_log_dir = wiki_dir if wiki_dir is not None else _WIKI_DIR
        append_wiki_log(
            "lint-fix",
            f"Auto-fixed {fixed_count} broken wikilink(s) across {pages_fixed} page(s)",
            effective_log_dir / "log.md",
        )

    return fixes


# _categories.md was designed but never written by the system — dropped to
# avoid a dead lookup on every lint invocation. Re-add if/when the categories
# index is actually materialized by the compile pipeline.
_INDEX_FILES = ("index.md", "_sources.md", "log.md")


def check_orphan_pages(wiki_dir: Path | None = None, graph: nx.DiGraph | None = None) -> list[dict]:
    """Find pages with no incoming links (except summaries, which are entry points).

    Returns:
        List of dicts: {page, message}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
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


def check_cycles(wiki_dir: Path | None = None, graph: nx.DiGraph | None = None) -> list[dict]:
    """Find circular wikilink chains (A → B → C → A).

    Returns:
        List of dicts: {cycle, message}.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    if graph is None:
        graph = build_graph(wiki_dir)
    issues = []

    # Phase 4.5 HIGH L1: bound cycle detection to 100 to prevent super-exponential
    # runtime on dense link graphs. nx.simple_cycles is unbounded; islice caps output.
    _MAX_CYCLES = 100
    for cycle in itertools.islice(nx.simple_cycles(graph), _MAX_CYCLES):
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

    if len(issues) >= _MAX_CYCLES:
        issues.append(
            {
                "check": "wikilink_cycle",
                "severity": "warning",
                "cycle": [],
                "message": (
                    f"Cycle detection aborted after {_MAX_CYCLES} cycles — graph may contain more"
                ),
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
            if isinstance(updated, date):
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


def check_frontmatter_staleness(
    wiki_dir: Path | None = None,
    pages: list[Path] | None = None,
) -> list[dict]:
    """Surface pages whose filesystem mtime is newer than their frontmatter `updated` date.

    Cycle 3 M10: ingest/refine is responsible for bumping `updated:`; when a
    page is hand-edited without the bump the page silently drifts from its
    declared freshness. This check compares the MD5-granularity of
    ``post.metadata['updated']`` (a date) against
    ``page_path.stat().st_mtime`` (a timestamp) and surfaces an info-severity
    issue when the mtime's date is strictly newer.

    Known limitation (acknowledged in scope doc, R2 review): same-day edits
    are NOT detected because frontmatter `updated` is date-granular.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)
    issues: list[dict] = []

    for page_path in pages:
        try:
            post = frontmatter.load(str(page_path))
        except (OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError) as e:
            logger.warning("Failed to load wiki page %s: %s", page_path, e)
            continue

        updated = post.metadata.get("updated")
        if isinstance(updated, str):
            try:
                updated = date.fromisoformat(updated)
            except ValueError:
                continue
        if isinstance(updated, datetime):
            updated = updated.date()
        if not isinstance(updated, date):
            continue  # check_staleness handles missing/malformed dates

        try:
            mtime_date = datetime.fromtimestamp(page_path.stat().st_mtime).date()
        except OSError:
            continue

        if mtime_date > updated:
            pid = page_id(page_path, wiki_dir)
            issues.append(
                {
                    "check": "frontmatter_updated_stale",
                    "severity": "info",
                    "page": pid,
                    "last_updated": updated.isoformat(),
                    "mtime_date": mtime_date.isoformat(),
                    "message": (
                        f"Frontmatter updated ({updated}) predates file mtime "
                        f"({mtime_date}) for {pid} — run kb refine to bump the date"
                    ),
                }
            )

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

    # Collect all raw references across wiki pages (single pass per file).
    # O1 (Phase 4.5 R4 HIGH): short-circuit pages missing the opening
    # frontmatter fence. `frontmatter.loads` returns empty metadata on these,
    # silently dropping any already-written `source:` YAML — producing
    # false-positive "Raw source not referenced" warnings. Flag the page as
    # malformed so the operator sees the actual problem.
    issues: list[dict] = []
    all_raw_refs = set()
    for page_path in pages:
        try:
            content = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read page %s: %s", page_path, e)
            continue
        # Short-circuit: if the page has body-level raw refs but no frontmatter
        # fence, emit a frontmatter issue and skip the YAML parse (which would
        # silently return empty metadata).
        if not content.lstrip().startswith("---"):
            # PR review round 1: use "check" key so `runner.py` and downstream
            # consumers filtering by `i["check"]` surface this class (was "type").
            issues.append(
                {
                    "check": "frontmatter_missing_fence",
                    "severity": "warning",
                    "page": str(page_path.relative_to(wiki_dir))
                    if page_path.is_relative_to(wiki_dir)
                    else str(page_path),
                    "message": f"Missing opening frontmatter fence in {page_path.name}",
                }
            )
            # Still collect body-level refs so a malformed page's mentions
            # don't falsely flag their raw sources as orphans.
            refs = extract_raw_refs(content)
            all_raw_refs.update(refs)
            continue
        try:
            post = frontmatter.loads(content)
            all_raw_refs.update(normalize_sources(post.metadata.get("source")))
            all_raw_refs.update(extract_raw_refs(post.content))
        except (ValueError, AttributeError, yaml.YAMLError) as e:
            logger.warning("Failed to parse frontmatter for %s: %s", page_path, e)
            all_raw_refs.update(extract_raw_refs(content))

    # Find raw sources not referenced (append to issues collected above).
    for _type_name, type_dir in SOURCE_TYPE_DIRS.items():
        actual_dir = raw_dir / type_dir.name
        if not actual_dir.exists():
            continue
        for f in actual_dir.rglob("*"):
            if (
                f.is_file()
                and f.name != ".gitkeep"
                and f.suffix.lower() in SUPPORTED_SOURCE_EXTENSIONS
            ):
                try:
                    rel_path = make_source_ref(f, raw_dir)
                except ValueError:
                    logger.warning("Skipping source outside raw_dir: %s", f)
                    continue
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
    wiki_dir = wiki_dir or WIKI_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)
    issues = []

    for page_path in pages:
        pid = page_id(page_path, wiki_dir)
        # Skip autogen pages — they're natural entry points, not stubs to enrich
        if pid.startswith(AUTOGEN_PREFIXES):
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
