"""Individual lint checks: orphans, dead links, staleness, circular refs, coverage gaps."""

from kb.compile.linker import resolve_wikilinks
from kb.config import RAW_DIR, SOURCE_TYPE_DIRS, WIKI_DIR
from kb.lint.checks.consistency import check_source_coverage
from kb.lint.checks.cycles import check_cycles
from kb.lint.checks.dead_links import _INDEX_FILES, check_dead_links, fix_dead_links
from kb.lint.checks.duplicate_slug import (
    _DUPLICATE_SLUGS_PAGE_CAP,
    _bounded_edit_distance,
    _slug_for_duplicate,
    check_duplicate_slugs,
)
from kb.lint.checks.frontmatter import (
    _ACTION_INGEST_RE,
    _EVIDENCE_TRAIL_ANCHOR,
    _STATUS_MATURE_STALE_DAYS,
    _compose_page_topics,
    _effective_max_days,
    check_authored_by_drift,
    check_frontmatter,
    check_frontmatter_staleness,
    check_status_mature_stale,
)
from kb.lint.checks.inline_callouts import (
    _CALLOUT_BODY_CHAR_CAP,
    _CALLOUT_MARKER_PATTERN,
    _CALLOUT_RE,
    _CALLOUTS_CROSS_PAGE_CAP,
    _CALLOUTS_PER_PAGE_CAP,
    check_inline_callouts,
    parse_inline_callouts,
)
from kb.lint.checks.orphan import check_orphan_pages, check_stub_pages
from kb.lint.checks.staleness import check_staleness
from kb.utils.io import atomic_text_write

__all__ = [
    "RAW_DIR",
    "SOURCE_TYPE_DIRS",
    "WIKI_DIR",
    "atomic_text_write",
    "resolve_wikilinks",
    "check_authored_by_drift",
    "check_cycles",
    "check_dead_links",
    "check_duplicate_slugs",
    "check_frontmatter",
    "check_frontmatter_staleness",
    "check_inline_callouts",
    "check_orphan_pages",
    "check_source_coverage",
    "check_staleness",
    "check_status_mature_stale",
    "check_stub_pages",
    "fix_dead_links",
    "parse_inline_callouts",
    "_ACTION_INGEST_RE",
    "_CALLOUT_BODY_CHAR_CAP",
    "_CALLOUT_MARKER_PATTERN",
    "_CALLOUT_RE",
    "_CALLOUTS_CROSS_PAGE_CAP",
    "_CALLOUTS_PER_PAGE_CAP",
    "_DUPLICATE_SLUGS_PAGE_CAP",
    "_EVIDENCE_TRAIL_ANCHOR",
    "_INDEX_FILES",
    "_STATUS_MATURE_STALE_DAYS",
    "_bounded_edit_distance",
    "_compose_page_topics",
    "_effective_max_days",
    "_slug_for_duplicate",
]
