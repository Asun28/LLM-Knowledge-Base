"""Cycle 64 AC9 — process-shared graph cache.

Closes the BACKLOG.md HIGH item "graph/builder.py no shared caching policy".
Pre-cycle-64 state: ``lint/runner.py`` builds a ``shared_graph`` per-call and
threads it down, but the 5 fallback ``build_graph(wiki_dir)`` call sites in
``lint/checks/cycles.py``, ``lint/checks/orphan.py``, ``lint/semantic.py``,
``lint/augment/collector.py``, and ``lint/runner.py:96`` rebuild from scratch
when ``shared_graph`` is None — and a future Phase 5 feature could add another
caller without a documented invalidation contract. Cycle 64 formalises a
process-shared cache keyed on ``(wiki_dir, max_mtime_of_wiki_subdirs)`` with
explicit invalidation hooks at ``ingest_source`` and ``refine_page``.

Design decisions (per ``2026-05-03-cycle-64-design-decision.md``):

- **Bespoke dict over ``functools.lru_cache``** (R2-F4 REJECT): per-key
  ``invalidate(wiki_dir)`` is required by AC11; ``functools.lru_cache``
  exposes only ``cache_clear()`` (drops all). AC12's
  ``test_invalidate_drops_entries_for_wiki_dir`` requires per-key precision.
- **RLock over Lock** (R2-F5 REJECT): test fixtures may invoke
  ``invalidate()`` from inside an autouse fixture that's already inside
  another lock context (cycle-19 L2 reload-leak pattern). RLock prevents
  false-positive deadlocks during test reloads.
- **Bypass cache when ``pages=`` supplied** (R1-F5): the in-memory pages
  list can diverge from disk-scanned pages; sharing a cache slot between
  the two caller shapes would let a stale ``pages=`` snapshot poison the
  fresh-disk caller's view (or vice versa). Pages-supplying callers
  already have data in memory — caching adds no win. Cache is for the
  disk-scan fallback only.
- **FIFO insertion-order eviction** (R1-F13): matches cycle-7's
  ``_index_cache`` precedent (embeddings.py:362–381). One eviction policy
  across two module-level caches reduces cognitive load.
- **`from kb.graph.builder import build_graph`** import shape (R1-F12):
  AC12 spies on ``kb.graph.cache.build_graph`` succeed. Callers that need
  to spy MUST patch the owner module attribute per cycle-18 L1 +
  CLAUDE.md path-safety convention.
- **`_MAX_CACHE_SIZE = 4`**: 1 wiki_dir for users + 2-4 for test fixtures
  / dev local / CI multi-fixture; bounded memory at ≤4 graphs without
  imposing a per-call hot-path cost. Adversarial cache-thrash workloads
  (1M+ wiki_dirs) degrade to the pre-cycle-64 baseline (build_graph
  per-call); correctness unaffected.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

from kb.graph.builder import build_graph

if TYPE_CHECKING:
    import networkx as nx

# ── Cache state ──

# Insertion-ordered dict (CPython 3.7+) keyed on
# (wiki_dir.resolve().as_posix(), max_mtime_of_wiki_subdirs). FIFO eviction
# by oldest insertion when size exceeds _MAX_CACHE_SIZE.
_GLOBAL_CACHE: dict[tuple[str, float], nx.DiGraph] = {}

# Re-entrant lock so test fixtures can invoke invalidate() from inside an
# autouse fixture that's already inside another lock context (cycle-19 L2
# reload-leak hazard). RLock is the ONLY correct choice here.
_CACHE_LOCK: threading.RLock = threading.RLock()

_MAX_CACHE_SIZE: int = 4

# Diagnostic counters; lock-free per cycle-25 Q8 — approximate, not
# billing-grade. Tests observe monotonic deltas via get_cache_stats().
_cache_hits: int = 0
_cache_misses: int = 0
_cache_invalidations: int = 0

# Canonical wiki subdirectories scanned for mtime. Mirrors the WIKI_SUBDIRS
# constant in tests/conftest.py + the `_vec_db_path` derivation pattern.
# Each subdir's *.md files are stat'd for max(st_mtime). On Windows NTFS
# this gives 100ns resolution; FAT32 (2s granularity) is not a documented
# project surface so coarse-grained cache misses are not a concern there.
_WIKI_SUBDIRS_FOR_MTIME: tuple[str, ...] = (
    "entities",
    "concepts",
    "comparisons",
    "summaries",
    "synthesis",
)


def _max_mtime_of_wiki_subdirs(wiki_dir: Path) -> float:
    """Return the most recent st_mtime across all *.md files in WIKI_SUBDIRS.

    Returns ``0.0`` for an empty wiki (consistent with cycle-25's empty-DB
    handling). Caller-supplied wiki_dir is trusted (callers are kb.* internals);
    no path validation here.
    """
    mtimes: list[float] = []
    for subdir_name in _WIKI_SUBDIRS_FOR_MTIME:
        subdir = wiki_dir / subdir_name
        if not subdir.exists():
            continue
        for md_file in subdir.rglob("*.md"):
            try:
                mtimes.append(md_file.stat().st_mtime)
            except OSError:
                # File disappeared between rglob and stat (rare; tolerate).
                continue
    return max(mtimes, default=0.0)


def get_graph(wiki_dir: Path, *, pages: list[dict] | None = None) -> nx.DiGraph:
    """Return a graph for ``wiki_dir``, using the process-shared cache when
    no ``pages=`` snapshot is supplied.

    Cycle 64 AC9. When ``pages is not None``, BYPASS the cache and call
    ``build_graph`` directly (per R1-F5: pages-supplying callers already
    have an in-memory snapshot; caching their result risks poisoning a
    fresh-disk caller). When ``pages is None``, look up by
    ``(wiki_dir.resolve().as_posix(), max_mtime_of_wiki_subdirs)`` — return
    the cached graph if hit; build, store, evict-if-over-bound, return.

    Cycle-18 L1 import shape: this function uses the module-top
    ``from kb.graph.builder import build_graph`` import so tests that
    spy on ``kb.graph.cache.build_graph`` (the OWNER module attribute)
    intercept correctly. Callers patching ``kb.graph.cache.get_graph``
    similarly succeed.
    """
    if pages is not None:
        # Bypass cache; pages-supplying callers already have data in memory.
        return build_graph(wiki_dir, pages=pages)

    cache_key = (wiki_dir.resolve().as_posix(), _max_mtime_of_wiki_subdirs(wiki_dir))
    with _CACHE_LOCK:
        if cache_key in _GLOBAL_CACHE:
            global _cache_hits
            _cache_hits += 1
            return _GLOBAL_CACHE[cache_key]
        # Miss — build, store, evict.
        global _cache_misses
        _cache_misses += 1
        graph = build_graph(wiki_dir)
        _GLOBAL_CACHE[cache_key] = graph
        # FIFO eviction by insertion order. Drops the oldest key first.
        while len(_GLOBAL_CACHE) > _MAX_CACHE_SIZE:
            oldest_key = next(iter(_GLOBAL_CACHE))
            _GLOBAL_CACHE.pop(oldest_key, None)
        return graph


def invalidate(wiki_dir: Path | None = None) -> int:
    """Drop cache entries for ``wiki_dir``; if ``None``, drop all.

    Cycle 64 AC11. Callers MUST invalidate after mutating wiki content
    (``ingest_source``, ``refine_page``, ``compile_wiki``) so subsequent
    ``get_graph`` calls see the post-mutation state instead of stale.

    Returns the number of entries dropped. Idempotent: no-op when no
    matching key exists.
    """
    with _CACHE_LOCK:
        global _cache_invalidations
        if wiki_dir is None:
            count = len(_GLOBAL_CACHE)
            _GLOBAL_CACHE.clear()
            _cache_invalidations += 1
            return count
        target_prefix = wiki_dir.resolve().as_posix()
        keys_to_drop = [k for k in _GLOBAL_CACHE if k[0] == target_prefix]
        for key in keys_to_drop:
            _GLOBAL_CACHE.pop(key, None)
        if keys_to_drop:
            _cache_invalidations += 1
        return len(keys_to_drop)


def get_cache_stats() -> dict:
    """Return diagnostic counters and current cache size.

    Cycle 64 AC9. Lock-free read of the size field (acceptable per cycle-25
    Q8 — counts are approximate); the size is a snapshot at call time.

    Returned dict:
        {
            "hits": int,            # cache-hit count since module load
            "misses": int,          # cache-miss count since module load
            "invalidations": int,   # number of invalidate() calls that dropped ≥1 entry
            "size": int,            # current cache size (≤ _MAX_CACHE_SIZE)
        }

    Threat T7 mitigation: keys are NOT exposed (would leak resolved paths).
    Counters are integer-only.
    """
    with _CACHE_LOCK:
        return {
            "hits": _cache_hits,
            "misses": _cache_misses,
            "invalidations": _cache_invalidations,
            "size": len(_GLOBAL_CACHE),
        }


def _reset_for_tests() -> None:
    """Test-only helper: reset all cache state between tests.

    Used by tests/test_cycle64_graph_cache.py's autouse fixture to ensure
    cross-test independence (the cache is module-level and process-shared).
    NOT exported via __all__; callers outside tests/ should use ``invalidate()``.
    """
    with _CACHE_LOCK:
        global _cache_hits, _cache_misses, _cache_invalidations
        _GLOBAL_CACHE.clear()
        _cache_hits = 0
        _cache_misses = 0
        _cache_invalidations = 0
