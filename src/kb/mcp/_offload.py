"""Async offload for long-running MCP tools.

Cycle 95 — Phase 4.5 HIGH R3: FastMCP executes sync tools via
``anyio.to_thread.run_sync``, which draws from the DEFAULT thread limiter
(capacity 40, stored per event loop in an anyio ``RunVar``). A tool holds
its token for its entire runtime, so concurrent long calls exhaust that
budget and queue every other tool — including sub-second browse reads —
behind them.

``register_long_tool(fn)`` registers a signature-preserving ASYNC wrapper
with FastMCP under ``fn``'s own name. The wrapper offloads the sync
implementation to a DEDICATED per-event-loop ``anyio.CapacityLimiter`` so
long tools contend only with each other and the default budget stays free
for the short tools. The module attribute (``kb.mcp.health.kb_lint``
etc.) remains the plain sync function, so direct-call test sites and CLI
parity paths are unchanged.

**Terminology (R1 P2).** A custom ``CapacityLimiter`` is an ADMISSION
BUDGET, not a separate pool of reserved OS threads: anyio keeps ONE
``workers``/``idle_workers`` collection per event loop and applies the
limiter as an ``async with`` gate around it. Total live workers can
therefore reach roughly default capacity + long-tool capacity. Do not
describe this as "a dedicated pool of N threads".

**Classification rule (R1 P1).** A tool belongs here if it makes an
LLM/network call OR does unbounded whole-corpus work. "Makes no LLM call"
is NOT sufficient to call a tool short — the starvation this module fixes
is about WALL TIME. Measured on a 174-page corpus: ``kb_evolve`` 4.96-11.25s
(loads the wiki, scores up to 50,000 connection pairs), ``kb_stats``
2.63-7.37s cold (fingerprints every page, rebuilds the graph under
``graph.cache._CACHE_LOCK``, runs PageRank). The 14 registered tools are
the 6 LLM/network ones plus 8 whole-corpus ones; each call site carries a
comment naming the specific unbounded work.

Deliberately NOT registered (bounded to one page or one capped store, so
they belong on the default budget): ``kb_search``, ``kb_read_page``,
``kb_list_pages``, ``kb_list_sources``, ``kb_verdict_trends``,
``kb_review_page``, ``kb_lint_deep``, ``kb_query_feedback``,
``kb_reliability_map``, ``kb_save_source``, ``kb_save_lint_verdict``,
``kb_create_page``, ``kb_refine_sweep``, ``kb_refine_list_stale``.
``kb_review_page`` / ``kb_lint_deep`` read every source referenced by
their ONE page with no byte cap — bounded by that page's source list, not
the corpus; the missing read bound is filed in BACKLOG as its own item.

Env vars (truthy variants ``{1, true, yes}`` case-insensitive):

- ``KB_MCP_LONG_TOOL_THREADS`` — dedicated pool capacity (default
  ``kb.config.MCP_LONG_TOOL_THREADS_DEFAULT``, floor 1). Read when an
  event loop's limiter is first created — one read per loop, which is the
  closest a loop-scoped resource can get to the cycle-19 L2 call-time rule.
- ``KB_DISABLE_MCP_LONG_TOOL_LIMITER`` — kill-switch, read at CALL time:
  offload through anyio's default limiter instead (pre-cycle-95
  behaviour, behaviourally identical to a plain sync FastMCP tool).

FW-1 (snapshot-binding, cycle-18 L1): the async wrapper binds ``fn`` at
decoration time. Tests must call the sync module attribute directly or
patch the OWNER-module callables underneath (``ingest_source``,
``query_wiki``, ...) — rebinding ``kb.mcp.health.kb_lint`` itself is not
seen by the MCP-registered wrapper.
"""

from __future__ import annotations

import functools
import logging
import os
from weakref import WeakKeyDictionary

import anyio
import anyio.to_thread

from kb.config import MCP_LONG_TOOL_THREADS_DEFAULT
from kb.mcp.app import mcp

logger = logging.getLogger(__name__)

# Registration-order names of every tool routed through register_long_tool.
# Pinned by tests against the app.py "## Concurrency" instructions note so
# the two surfaces cannot drift.
LONG_TOOL_NAMES: list[str] = []

# Per-event-loop limiter cache. ``anyio.CapacityLimiter()`` must be
# constructed inside a running async context (the backend is sniffed at
# creation), and a limiter is only meaningful while its loop is alive —
# keying on the loop keeps each ``anyio.run()`` in tests isolated and
# re-reads the capacity env once per loop.
_limiters: WeakKeyDictionary = WeakKeyDictionary()


def _limiter_disabled() -> bool:
    """Kill-switch, read at CALL time (cycle-19 L2)."""
    return os.environ.get("KB_DISABLE_MCP_LONG_TOOL_LIMITER", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _long_tool_capacity() -> int:
    """Dedicated-pool capacity from env, defaulting to the config constant."""
    raw = os.environ.get("KB_MCP_LONG_TOOL_THREADS", "").strip()
    if not raw:
        return MCP_LONG_TOOL_THREADS_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "KB_MCP_LONG_TOOL_THREADS=%r is not an integer; using default %d",
            raw,
            MCP_LONG_TOOL_THREADS_DEFAULT,
        )
        return MCP_LONG_TOOL_THREADS_DEFAULT
    return max(1, value)


def _get_limiter() -> anyio.CapacityLimiter | None:
    """Return this loop's dedicated limiter, or ``None`` for the default pool.

    Must be called from async context. ``None`` (kill-switch set, or no
    asyncio loop detectable) makes ``anyio.to_thread.run_sync`` fall back
    to its default limiter — never hand out a fresh uncached limiter per
    call, which would enforce nothing.
    """
    if _limiter_disabled():
        return None
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Non-asyncio backend. FastMCP runs asyncio; if we get here anyway,
        # degrade to the shared pool rather than a non-limiting limiter.
        logger.warning(
            "no running asyncio loop; long-tool offload falling back to the default pool"
        )
        return None
    limiter = _limiters.get(loop)
    if limiter is None:
        limiter = anyio.CapacityLimiter(_long_tool_capacity())
        _limiters[loop] = limiter
    return limiter


def async_offload(fn):
    """Wrap sync ``fn`` in a signature-preserving coroutine on the long-tool pool.

    ``functools.wraps`` carries ``__name__`` / ``__doc__`` / ``__wrapped__``
    so FastMCP derives the tool name, description, and full parameter
    schema from ``fn`` (verified by the cycle-95 schema-preservation tests).
    """

    @functools.wraps(fn)
    async def _offloaded(*args, **kwargs):
        return await anyio.to_thread.run_sync(
            functools.partial(fn, *args, **kwargs), limiter=_get_limiter()
        )

    return _offloaded


def register_long_tool(fn):
    """Register ``fn`` with FastMCP as an async-offloaded tool; return ``fn`` unchanged.

    Drop-in replacement for ``@mcp.tool()`` on long-running tools::

        @register_long_tool
        @_mcp_error_boundary        # optional, stays below as before
        def kb_query(...): ...

    The module attribute stays the sync callable (tests / CLI parity);
    only the FastMCP-registered surface becomes async.
    """
    mcp.tool(async_offload(fn))
    LONG_TOOL_NAMES.append(fn.__name__)
    return fn
