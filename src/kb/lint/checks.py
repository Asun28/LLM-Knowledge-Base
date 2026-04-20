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
    CALLOUT_MARKERS,
    DUPLICATE_SLUG_DISTANCE_THRESHOLD,
    RAW_DIR,
    SOURCE_DECAY_DEFAULT_DAYS,
    SOURCE_TYPE_DIRS,
    STUB_MIN_CONTENT_CHARS,
    SUPPORTED_SOURCE_EXTENSIONS,
    WIKI_DIR,
    decay_days_for,
)
from kb.graph.builder import build_graph, graph_stats
from kb.models.frontmatter import validate_frontmatter
from kb.utils.io import atomic_text_write
from kb.utils.markdown import extract_raw_refs, extract_wikilinks
from kb.utils.pages import load_page_frontmatter, normalize_sources, page_id, scan_wiki_pages
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


def _compose_page_topics(metadata: dict) -> str:
    """Compose tags + title into a single string for volatility lookup.

    Cycle 15 AC1/AC4 support — tags can be list-of-str or str; compose
    robustly so ``volatility_multiplier_for`` handles all shapes.
    """
    tags = metadata.get("tags", "")
    if isinstance(tags, list):
        tags_str = " ".join(str(t) for t in tags)
    else:
        tags_str = str(tags) if tags else ""
    title = str(metadata.get("title", ""))
    return f"{tags_str} {title}".strip()


def _effective_max_days(metadata: dict) -> int:
    """Cycle 15 AC4 — per-page decay window from source list.

    Uses the max of ``decay_days_for(source, topics=...)`` across every
    entry in the page's ``source`` frontmatter field (lenient — longest-decay
    platform wins for multi-source pages). Falls back to
    ``SOURCE_DECAY_DEFAULT_DAYS`` when the page has no sources.
    """
    sources = normalize_sources(metadata.get("source"))
    if not sources:
        return SOURCE_DECAY_DEFAULT_DAYS
    topics = _compose_page_topics(metadata)
    return max(
        (decay_days_for(str(s), topics=topics) for s in sources),
        default=SOURCE_DECAY_DEFAULT_DAYS,
    )


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
    wiki_dir = wiki_dir or WIKI_DIR
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
            metadata, body = load_page_frontmatter(page_path)
            del body
        except (OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError) as e:
            logger.warning("Failed to load wiki page %s: %s", page_path, e)
            continue

        updated = metadata.get("updated")
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


# Cycle 15 AC5 — status: mature staleness threshold (hardcoded 90 days per
# Step-5 gate; cycle-16 candidate to route through decay_days_for once the
# topic signal proves out).
_STATUS_MATURE_STALE_DAYS = 90


def check_status_mature_stale(
    wiki_dir: Path | None = None,
    pages: list[Path] | None = None,
    today: date | None = None,
) -> list[dict]:
    """Cycle 15 AC5 — flag ``status: mature`` pages unchanged >90 days.

    Surfaces a ``warning``-level issue per page: the author marked the page
    as mature (a load-bearing lifecycle signal) but hasn't touched it in
    a quarter. Operator remediation is to either re-review (bump ``updated``)
    or downgrade ``status`` to ``developing``.

    Args:
        wiki_dir: Defaults to ``WIKI_DIR``.
        pages: Optional pre-scanned page list (shared with other checks).
        today: Override current date for deterministic testing.

    Returns:
        List of dicts: ``{check, severity, page, last_updated, message}``.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)
    today = today or date.today()
    cutoff = today - timedelta(days=_STATUS_MATURE_STALE_DAYS)
    issues: list[dict] = []

    for page_path in pages:
        try:
            metadata, body = load_page_frontmatter(page_path)
            del body
        except (OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError) as e:
            logger.warning("Failed to load wiki page %s: %s", page_path, e)
            continue
        if str(metadata.get("status", "")).strip() != "mature":
            continue
        updated = metadata.get("updated")
        if isinstance(updated, str):
            try:
                updated = date.fromisoformat(updated)
            except ValueError:
                continue
        if isinstance(updated, datetime):
            updated = updated.date()
        if not isinstance(updated, date):
            continue
        if updated < cutoff:
            pid = page_id(page_path, wiki_dir)
            delta = (today - updated).days
            issues.append(
                {
                    "check": "status_mature_stale",
                    "severity": "warning",
                    "page": pid,
                    "last_updated": updated.isoformat(),
                    "message": (f"mature page {pid} unchanged {delta} days — consider re-review"),
                }
            )
    return issues


# Cycle 15 AC6 — Evidence Trail span anchor. Mirrors the machine-maintained
# sentinel convention from src/kb/ingest/evidence.py:96 so the `action:
# ingest` regex scan fires only within the trail block (threat T5).
#
# R1 MINOR 1 — tolerate trailing horizontal whitespace on the header line so
# hand-edited pages with ``## Evidence Trail  \n`` still match. Machine-
# written sentinels never include trailing whitespace, but lint targets
# human-authored pages too.
_EVIDENCE_TRAIL_ANCHOR = re.compile(r"^## Evidence Trail[ \t]*\r?\n", re.MULTILINE)
_NEXT_H2_HEADER = re.compile(r"^## ", re.MULTILINE)
_ACTION_INGEST_RE = re.compile(r"action:\s*ingest", re.IGNORECASE)


def check_authored_by_drift(
    wiki_dir: Path | None = None,
    pages: list[Path] | None = None,
) -> list[dict]:
    """Cycle 15 AC6 — flag ``authored_by: human`` pages auto-edited by ingest.

    Scans the Evidence Trail section body (between ``^## Evidence Trail``
    and the next ``^## `` header or EOF) for any ``action: ingest`` entry.
    Pages lacking an Evidence Trail section emit no warning (absence of
    signal is not a drift event — threat T5 mitigation).

    Args:
        wiki_dir: Defaults to ``WIKI_DIR``.
        pages: Optional pre-scanned page list.

    Returns:
        List of dicts: ``{check, severity, page, message}``.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)
    issues: list[dict] = []

    for page_path in pages:
        try:
            metadata, body = load_page_frontmatter(page_path)
        except (OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError) as e:
            logger.warning("Failed to load wiki page %s: %s", page_path, e)
            continue
        if str(metadata.get("authored_by", "")).strip() != "human":
            continue
        # Threat T5 — scope regex to the Evidence Trail span only.
        anchor = _EVIDENCE_TRAIL_ANCHOR.search(body)
        if anchor is None:
            continue  # no trail → no drift signal
        span_start = anchor.end()
        next_h2 = _NEXT_H2_HEADER.search(body, pos=span_start)
        span_end = next_h2.start() if next_h2 else len(body)
        trail_span = body[span_start:span_end]
        if _ACTION_INGEST_RE.search(trail_span) is None:
            continue
        pid = page_id(page_path, wiki_dir)
        issues.append(
            {
                "check": "authored_by_drift",
                "severity": "warning",
                "page": pid,
                "message": (
                    f"human-authored {pid} auto-edited by ingest — "
                    "drop authored_by or change to hybrid"
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
            metadata, body = load_page_frontmatter(page_path)
            post = frontmatter.Post(body, **metadata)
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


# ── Cycle 16 AC10-AC13 — duplicate-slug + inline-callouts ────────────────
_DUPLICATE_SLUGS_PAGE_CAP: int = 10_000
_CALLOUTS_PER_PAGE_CAP: int = 500
_CALLOUTS_CROSS_PAGE_CAP: int = 10_000
_CALLOUT_BODY_BYTE_CAP: int = 1_048_576  # 1 MiB — T5 DoS bound

_CALLOUT_MARKER_PATTERN = "|".join(re.escape(m) for m in CALLOUT_MARKERS)
_CALLOUT_RE = re.compile(
    r"^> \[!(" + _CALLOUT_MARKER_PATTERN + r")\][^\n]*$",
    re.MULTILINE | re.IGNORECASE,
)


def _bounded_edit_distance(a: str, b: str, threshold: int) -> int:
    """Return Levenshtein distance between ``a`` and ``b`` capped at ``threshold + 1``.

    Pure-stdlib two-row dynamic programming with an early exit when the running
    row-minimum exceeds ``threshold`` — returns ``threshold + 1`` in that case
    so callers know the true distance is strictly greater. Used for
    :func:`check_duplicate_slugs` (T6 DoS containment).
    """
    la, lb = len(a), len(b)
    if la == 0:
        return min(lb, threshold + 1)
    if lb == 0:
        return min(la, threshold + 1)
    if abs(la - lb) > threshold:
        return threshold + 1

    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        curr = [i] + [0] * lb
        row_min = curr[0]
        ai = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ai == b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,  # deletion
                curr[j - 1] + 1,  # insertion
                prev[j - 1] + cost,  # substitution
            )
            if curr[j] < row_min:
                row_min = curr[j]
        if row_min > threshold:
            return threshold + 1
        prev = curr
    return prev[lb]


def _slug_for_duplicate(page: Path, wiki_dir: Path) -> str:
    """Return the canonical slug form for duplicate-slug comparison.

    Per AC10 and T14: full lowered ``page_id`` (subdir retained), with
    underscores normalised to hyphens so ``foo_bar`` and ``foo-bar`` are
    comparable at distance 1.
    """
    pid = page_id(page, wiki_dir)
    return pid.lower().replace("_", "-")


def check_duplicate_slugs(
    wiki_dir: Path | None = None, pages: list[Path] | None = None
) -> list[dict]:
    """Detect near-duplicate page slugs via bounded edit-distance.

    Cycle 16 AC10 / AC13 / T6 / T14.

    For wikis above :data:`_DUPLICATE_SLUGS_PAGE_CAP` pages, returns a single
    skip record rather than running the O(N²) comparison — protects
    ``kb_lint`` from CPU exhaustion on large wikis.

    Length-bucket iteration (Q10/C6): for each slug of length L, compare
    against slugs in buckets ``[L, L+1, ..., L+DUPLICATE_SLUG_DISTANCE_THRESHOLD]``.
    Levenshtein lower bound ``distance >= abs(len(a) - len(b))`` means
    radius 1 would miss distance-2/3 pairs; use full-threshold radius.

    Returns dicts: ``{"slug_a", "slug_b", "distance", "page_a", "page_b"}``.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)

    if len(pages) > _DUPLICATE_SLUGS_PAGE_CAP:
        return [
            {
                "slug_a": "<skipped>",
                "slug_b": "<skipped>",
                "distance": -1,
                "page_a": "",
                "page_b": "",
                "skipped_reason": (
                    f"wiki too large ({len(pages)} pages > cap {_DUPLICATE_SLUGS_PAGE_CAP})"
                ),
            }
        ]

    slug_entries: list[tuple[str, str]] = []  # (slug, page_id)
    for p in pages:
        try:
            pid = page_id(p, wiki_dir)
        except (OSError, ValueError):
            continue
        slug_entries.append((_slug_for_duplicate(p, wiki_dir), pid))

    # Bucket by slug length.
    buckets: dict[int, list[tuple[str, str]]] = {}
    for entry in slug_entries:
        buckets.setdefault(len(entry[0]), []).append(entry)

    seen_pairs: set[tuple[str, str]] = set()
    issues: list[dict] = []
    for length, bucket in buckets.items():
        # Iterate same-bucket pairs plus above-length buckets up to +threshold.
        candidate_buckets: list[list[tuple[str, str]]] = [bucket]
        for delta in range(1, DUPLICATE_SLUG_DISTANCE_THRESHOLD + 1):
            other = buckets.get(length + delta)
            if other:
                candidate_buckets.append(other)

        for i, (slug_a, pid_a) in enumerate(bucket):
            for cb_idx, cb in enumerate(candidate_buckets):
                start = i + 1 if cb_idx == 0 else 0
                for slug_b, pid_b in cb[start:]:
                    if slug_a == slug_b:
                        continue  # AC10 — distance 0 excluded
                    key = (min(pid_a, pid_b), max(pid_a, pid_b))
                    if key in seen_pairs:
                        continue
                    distance = _bounded_edit_distance(
                        slug_a, slug_b, DUPLICATE_SLUG_DISTANCE_THRESHOLD
                    )
                    if 0 < distance <= DUPLICATE_SLUG_DISTANCE_THRESHOLD:
                        seen_pairs.add(key)
                        issues.append(
                            {
                                "slug_a": slug_a,
                                "slug_b": slug_b,
                                "distance": distance,
                                "page_a": pid_a,
                                "page_b": pid_b,
                            }
                        )
    return issues


def parse_inline_callouts(content: str) -> list[dict]:
    """Return Obsidian-style callouts `> [!marker] text` from ``content``.

    Cycle 16 AC11 / T5 / T12.

    Returns list of ``{"marker": str, "line": int, "text": str}``.
    - ``marker`` is lowercased (regex is case-insensitive per AC11).
    - ``line`` is 1-based.
    - ``text`` is the full matched line (``> [!…] …``).

    Bounded: input > ``_CALLOUT_BODY_BYTE_CAP`` returns ``[]`` (T5 page-body
    DoS mitigation). Per-page cap: ``_CALLOUTS_PER_PAGE_CAP`` matches,
    then appends a ``{"marker": "__truncated__", ...}`` sentinel and stops.
    """
    if len(content) > _CALLOUT_BODY_BYTE_CAP:
        return []

    out: list[dict] = []
    for m in _CALLOUT_RE.finditer(content):
        if len(out) >= _CALLOUTS_PER_PAGE_CAP:
            out.append(
                {
                    "marker": "__truncated__",
                    "line": 0,
                    "text": f"truncated at {_CALLOUTS_PER_PAGE_CAP} matches",
                }
            )
            break
        line_number = content.count("\n", 0, m.start()) + 1
        out.append(
            {
                "marker": m.group(1).lower(),
                "line": line_number,
                "text": m.group(0),
            }
        )
    return out


def check_inline_callouts(
    wiki_dir: Path | None = None, pages: list[Path] | None = None
) -> list[dict]:
    """Aggregate inline callouts across the wiki for lint reporting.

    Cycle 16 AC12 / T5 / T12.

    Returns dicts: ``{"page_id", "marker", "line", "text"}``. Unreadable
    pages are logged and skipped (consistent with other checks). Cross-page
    cap: ``_CALLOUTS_CROSS_PAGE_CAP`` — adds a truncation record and breaks
    when exceeded.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)

    out: list[dict] = []
    for p in pages:
        try:
            content = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Skipping unreadable page %s in callout scan: %s", p, e)
            continue
        try:
            pid = page_id(p, wiki_dir)
        except (OSError, ValueError) as e:
            logger.warning("Skipping unresolvable page_id for %s: %s", p, e)
            continue

        for entry in parse_inline_callouts(content):
            if len(out) >= _CALLOUTS_CROSS_PAGE_CAP:
                out.append(
                    {
                        "page_id": "__truncated__",
                        "marker": "__truncated__",
                        "line": 0,
                        "text": f"truncated at {_CALLOUTS_CROSS_PAGE_CAP} matches",
                    }
                )
                return out
            out.append(
                {
                    "page_id": pid,
                    "marker": entry["marker"],
                    "line": entry["line"],
                    "text": entry["text"],
                }
            )
    return out
