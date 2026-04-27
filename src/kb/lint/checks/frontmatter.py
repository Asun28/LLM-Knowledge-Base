"""Frontmatter lint checks."""

import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import frontmatter
import yaml

from kb.config import SOURCE_DECAY_DEFAULT_DAYS, decay_days_for
from kb.lint import checks
from kb.models.frontmatter import validate_frontmatter
from kb.utils.pages import load_page_frontmatter, normalize_sources, page_id, scan_wiki_pages

logger = logging.getLogger(__name__)


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
    wiki_dir = wiki_dir or checks.WIKI_DIR
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
    wiki_dir = wiki_dir or checks.WIKI_DIR
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
    wiki_dir = wiki_dir or checks.WIKI_DIR
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
    wiki_dir = wiki_dir or checks.WIKI_DIR
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
