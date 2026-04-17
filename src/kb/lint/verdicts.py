"""Persistent lint and review verdict storage."""

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

from kb.config import MAX_VERDICTS, VERDICTS_PATH
from kb.utils.io import file_lock

logger = logging.getLogger(__name__)

VALID_SEVERITIES = ("error", "warning", "info")
VALID_VERDICT_TYPES: tuple[str, ...] = (
    "fidelity",
    "consistency",
    "completeness",
    "review",
    "augment",
)
MAX_NOTES_LEN = 2000

# Cycle 4 item #12 — per-issue description size cap at library boundary.
# Previously `mcp/quality.py::kb_save_lint_verdict` capped issue COUNT (≤100)
# but not per-issue DESCRIPTION length, so a library caller passing
# ``issues=[{"severity":"error","description": 1_000_000*"x"}]`` × 100 could
# inflate one verdict entry to ~100 MB of disk writes. The mtime-keyed
# verdict cache would then thrash on every subsequent read.
MAX_ISSUE_DESCRIPTION_LEN = 4000


# M1 (Phase 4.5 MEDIUM): cache keyed on (path_str, mtime_ns, size). A 10k-
# entry verdict file is 3-5 MB (~50-150 ms per json.loads on Windows); this
# avoids re-parsing when the file hasn't changed. Invalidated on every save
# via _invalidate_verdicts_cache.
#
# PR review round 1 (Sonnet MAJOR M1 + Codex m-new-2):
#   - Threads acquire `_VERDICTS_CACHE_LOCK` around get/set so the module-
#     level dict is not corrupted under FastMCP's 40-thread pool.
#   - `load_verdicts` returns a SHALLOW COPY of the cached list so callers
#     that mutate (e.g. `add_verdict` → `verdicts.append(...)`) cannot
#     retroactively corrupt subsequent readers within the same (mtime,size)
#     window.
_VERDICTS_CACHE: dict[str, tuple[int, int, list[dict]]] = {}
_VERDICTS_CACHE_LOCK = threading.Lock()


def _invalidate_verdicts_cache(path: Path) -> None:
    """Drop the cache entry for `path` (called after every save)."""
    with _VERDICTS_CACHE_LOCK:
        _VERDICTS_CACHE.pop(str(path), None)


def load_verdicts(path: Path | None = None) -> list[dict]:
    """Load all stored verdicts from JSON file.

    M1 (Phase 4.5 MEDIUM): uses a (mtime_ns, size)-keyed cache so repeated
    callers (add_verdict, get_page_verdicts, get_verdict_summary, trends,
    runner.py) skip re-parsing when the file hasn't changed on disk. The
    cache is thread-safe and returns a shallow copy so callers mutating the
    result cannot poison subsequent reads.
    """
    path = path or VERDICTS_PATH
    if not path.exists():
        return []
    try:
        stat = path.stat()
    except OSError as e:
        logger.warning("Could not stat verdicts file %s: %s", path, e)
        return []
    key = str(path)
    with _VERDICTS_CACHE_LOCK:
        cached = _VERDICTS_CACHE.get(key)
        if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            return list(cached[2])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.warning("Corrupt verdicts file %s, returning empty: %s", path, e)
        return []
    if not isinstance(data, list):
        return []
    with _VERDICTS_CACHE_LOCK:
        _VERDICTS_CACHE[key] = (stat.st_mtime_ns, stat.st_size, data)
    return list(data)


def save_verdicts(verdicts: list[dict], path: Path | None = None) -> None:
    """Save verdicts to JSON file (atomic write via temp file)."""
    from kb.utils.io import atomic_json_write

    path = path or VERDICTS_PATH
    # PR review round 1 (Sonnet MAJOR M1): invalidate BEFORE the write. If
    # the write fails partway, the cache reflects "unknown" (forcing a
    # re-read) instead of the attempted-but-uncommitted state.
    _invalidate_verdicts_cache(path)
    atomic_json_write(verdicts, path)


def add_verdict(
    page_id: str,
    verdict_type: str,
    verdict: str,
    issues: list[dict] | None = None,
    notes: str = "",
    path: Path | None = None,
) -> dict:
    """Record a lint or review verdict for a page.

    Args:
        page_id: Wiki page ID (e.g., 'concepts/rag').
        verdict_type: Type of check ('fidelity', 'consistency', 'completeness', 'review').
        verdict: Result ('pass', 'fail', 'warning').
        issues: List of issue dicts with severity/description.
        notes: Free-text notes.
        path: Path to verdicts JSON file.

    Returns:
        The created verdict dict.

    Raises:
        ValueError: If verdict is not valid.
    """
    if verdict not in ("pass", "fail", "warning"):
        raise ValueError(f"Invalid verdict: {verdict}. Must be 'pass', 'fail', or 'warning'")
    if verdict_type not in VALID_VERDICT_TYPES:
        raise ValueError(
            f"Invalid verdict_type: {verdict_type}. "
            f"Must be one of: {', '.join(repr(t) for t in VALID_VERDICT_TYPES)}"
        )

    # Validate page_id against path traversal and null bytes
    if ".." in page_id or page_id.startswith("/") or page_id.startswith("\\") or "\x00" in page_id:
        raise ValueError(f"Invalid page_id: {page_id!r}. Must not contain '..' or start with '/'.")

    # Cap notes length (consistent with feedback store MAX_NOTES_LEN)
    if len(notes) > MAX_NOTES_LEN:
        logger.warning(
            "Notes truncated from %d to %d chars for %s", len(notes), MAX_NOTES_LEN, page_id
        )
        notes = notes[:MAX_NOTES_LEN]

    if issues:
        for issue in issues:
            if not isinstance(issue, dict):
                raise ValueError(f"Each issue must be a dict, got {type(issue).__name__}")
            severity = issue.get("severity", "")
            if severity and severity not in VALID_SEVERITIES:
                raise ValueError(
                    f"Invalid issue severity '{severity}'. "
                    f"Must be one of: {', '.join(VALID_SEVERITIES)}"
                )
            # Cycle 4 item #12 — cap per-issue description at library boundary
            # so direct library callers (not just MCP) cannot inflate the
            # verdict store. Truncate in place with a tag so operators can
            # spot oversized entries in the audit log.
            desc = issue.get("description", "")
            if isinstance(desc, str) and len(desc) > MAX_ISSUE_DESCRIPTION_LEN:
                logger.warning(
                    "Issue description truncated from %d → %d chars for %s",
                    len(desc),
                    MAX_ISSUE_DESCRIPTION_LEN,
                    page_id,
                )
                issue["description"] = (
                    desc[:MAX_ISSUE_DESCRIPTION_LEN] + "... [truncated]"
                )

    path = path or VERDICTS_PATH
    with file_lock(path):
        verdicts = load_verdicts(path)
        entry = {
            # Phase 4.5 HIGH L4: write UTC-aware timestamps so trend bucketing
            # is consistent across machines (completes the read-side fix in trends.py).
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "page_id": page_id,
            "verdict_type": verdict_type,
            "verdict": verdict,
            "issues": issues or [],
            "notes": notes,
        }
        verdicts.append(entry)
        # Retain only the most recent verdicts to prevent unbounded growth
        if len(verdicts) > MAX_VERDICTS:
            verdicts = verdicts[-MAX_VERDICTS:]
        save_verdicts(verdicts, path)
    return entry


def get_page_verdicts(page_id: str, path: Path | None = None) -> list[dict]:
    """Get all verdicts for a specific page, most recent first."""
    verdicts = load_verdicts(path)
    return sorted(
        [v for v in verdicts if v.get("page_id") == page_id],
        key=lambda v: v.get("timestamp", ""),
        reverse=True,
    )


def get_verdict_summary(path: Path | None = None) -> dict:
    """Get summary statistics of all verdicts.

    Returns:
        Dict with total, by_verdict (pass/fail/warning counts),
        by_type (fidelity/consistency/completeness/review counts),
        pages_with_failures (list of page IDs that have at least one 'fail').
    """
    verdicts = load_verdicts(path)
    summary = {
        "total": len(verdicts),
        "by_verdict": {"pass": 0, "fail": 0, "warning": 0},
        "by_type": {t: 0 for t in VALID_VERDICT_TYPES},
        "pages_with_failures": [],
    }
    failed_pages = set()
    for v in verdicts:
        vrd = v.get("verdict", "")
        vtype = v.get("verdict_type", "")
        if vrd in summary["by_verdict"]:
            summary["by_verdict"][vrd] += 1
        if vtype in summary["by_type"]:
            summary["by_type"][vtype] += 1
        if vrd == "fail":
            pid = v.get("page_id", "")
            if pid:
                failed_pages.add(pid)
    summary["pages_with_failures"] = sorted(failed_pages)
    return summary
