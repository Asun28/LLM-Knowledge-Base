"""Cycle 95 — MCP long-tool async offload (Phase 4.5 HIGH R3).

Six long-running MCP tools (kb_query / kb_lint / kb_compile / kb_ingest /
kb_ingest_content / kb_capture) register a signature-preserving ASYNC
wrapper that offloads the sync implementation to a dedicated per-event-loop
``anyio.CapacityLimiter`` (``kb.mcp._offload``), so concurrent long calls
cannot saturate FastMCP's shared default worker pool. The module attributes
stay plain sync callables — the direct-call contract every pre-cycle-95
test site relies on.
"""

import functools
import inspect
import threading
import time

import anyio
import anyio.to_thread
import pytest

# Importing the tool modules triggers @mcp.tool() registration side-effects
# (same mechanism as kb.mcp._register_all_tools).
import kb.mcp.browse as mcp_browse
import kb.mcp.compile as mcp_compile
import kb.mcp.core as mcp_core
import kb.mcp.health as mcp_health
import kb.mcp.ingest as mcp_ingest
import kb.mcp.quality as mcp_quality
from kb.config import MCP_LONG_TOOL_THREADS_DEFAULT
from kb.mcp._offload import (
    LONG_TOOL_NAMES,
    _get_limiter,
    _limiter_disabled,
    _long_tool_capacity,
    async_offload,
)
from kb.mcp.app import _LONG_TOOL_NOTE_NAMES, mcp

# Long = makes an LLM/network call OR does unbounded whole-corpus work.
# R1 P1 widened this from 6 to 14: "makes no LLM call" is not the same as
# "short", and kb_evolve (4.96-11.25s) / kb_stats (2.63-7.37s cold) were
# measured holding default-limiter tokens for seconds at a time.
EXPECTED_LONG_TOOLS = {
    # LLM / network
    "kb_query",
    "kb_lint",
    "kb_compile",
    "kb_ingest",
    "kb_ingest_content",
    "kb_capture",
    # whole-corpus work
    "kb_evolve",
    "kb_stats",
    "kb_graph_viz",
    "kb_detect_drift",
    "kb_compile_scan",
    "kb_lint_consistency",
    "kb_refine_page",
    "kb_affected_pages",
}

# Deliberately-sync: bounded to a single page, a capped listing, or one
# retention-capped JSON store. Pinned so a future sweep cannot quietly widen
# the long list until the dedicated budget is just a smaller shared one.
SHORT_TOOL_SAMPLE = (
    "kb_search",
    "kb_read_page",
    "kb_list_pages",
    "kb_list_sources",
    "kb_verdict_trends",
    "kb_save_source",
    "kb_lint_deep",
    "kb_review_page",
    "kb_reliability_map",
    "kb_create_page",
    "kb_refine_list_stale",
)


# ── Registration surface ──────────────────────────────────────────────


def test_long_tools_registered_as_async():
    async def check():
        for name in sorted(EXPECTED_LONG_TOOLS):
            tool = await mcp.get_tool(name)
            assert inspect.iscoroutinefunction(tool.fn), f"{name} should be async-offloaded"

    anyio.run(check)


def test_short_tools_stay_sync():
    async def check():
        for name in SHORT_TOOL_SAMPLE:
            tool = await mcp.get_tool(name)
            assert not inspect.iscoroutinefunction(tool.fn), f"{name} should remain sync"

    anyio.run(check)


@pytest.mark.parametrize("name", sorted(EXPECTED_LONG_TOOLS))
def test_module_attributes_remain_sync_callables(name):
    """Direct-call contract: every pre-cycle-95 test site calls these sync."""
    fn = _sync_impl(name)
    assert callable(fn), name
    assert not inspect.iscoroutinefunction(fn), f"{name} module attr must stay sync"


def test_registration_list_matches_instructions_note():
    """kb.mcp._offload.LONG_TOOL_NAMES and app._LONG_TOOL_NOTE_NAMES cannot drift."""
    assert set(LONG_TOOL_NAMES) == set(_LONG_TOOL_NOTE_NAMES) == EXPECTED_LONG_TOOLS
    # No double registration (module import is cached, so each name once).
    assert len(LONG_TOOL_NAMES) == len(set(LONG_TOOL_NAMES))


def _sync_impl(name):
    """Resolve a long tool's SYNC implementation from its owner module."""
    for mod in (mcp_core, mcp_health, mcp_compile, mcp_ingest, mcp_browse, mcp_quality):
        fn = getattr(mod, name, None)
        if fn is not None and callable(fn):
            return fn
    raise AssertionError(f"no sync implementation found for {name}")


@pytest.mark.parametrize("name", sorted(EXPECTED_LONG_TOOLS))
def test_wrapper_schema_matches_plain_registration(name):
    """R1 P2 — full schema equality for ALL long tools, not a subset of two.

    Registers the same sync function on a THROWAWAY FastMCP with plain
    `.tool()` and compares the complete parameter schema + description
    against the offloaded registration on the real app. Catches any
    property, required-list, default, or nullability drift the async
    wrapper might introduce (e.g. `kb_capture.provenance`'s `str | None`).
    """
    from fastmcp import FastMCP

    reference_app = FastMCP("cycle95-schema-reference")
    reference_app.tool(_sync_impl(name))

    async def check():
        offloaded = await mcp.get_tool(name)
        plain = await reference_app.get_tool(name)
        assert offloaded.parameters == plain.parameters
        assert offloaded.description == plain.description
        assert offloaded.name == plain.name

    anyio.run(check)


@pytest.mark.parametrize("name", sorted(EXPECTED_LONG_TOOLS))
def test_wrapper_signature_follows_sync_impl(name):
    async def check():
        tool = await mcp.get_tool(name)
        assert inspect.signature(tool.fn) == inspect.signature(_sync_impl(name))

    anyio.run(check)


# ── End-to-end async execution ───────────────────────────────────────


def test_async_path_executes_sync_body_end_to_end():
    """In-memory MCP client → async wrapper → thread → sync validation body."""
    from fastmcp import Client

    async def run():
        async with Client(mcp) as client:
            res = await client.call_tool("kb_query", {"question": ""})
            return res.content[0].text

    assert anyio.run(run) == "Error: Question cannot be empty."


def test_error_boundary_sanitizes_through_async_path(monkeypatch):
    """_mcp_error_boundary (below the offload wrapper) still catches + sanitizes."""
    from fastmcp import Client

    def boom(ctx):
        raise RuntimeError("boom-internal")

    monkeypatch.setattr("kb.mcp.core._sanitize_conversation_context", boom)

    async def run():
        async with Client(mcp) as client:
            res = await client.call_tool("kb_query", {"question": "q", "conversation_context": "x"})
            return res.content[0].text

    text = anyio.run(run)
    assert text.startswith("Error:")
    assert "boom-internal" in text


# ── Limiter capacity + kill-switch env contract ──────────────────────


def test_capacity_default(monkeypatch):
    monkeypatch.delenv("KB_MCP_LONG_TOOL_THREADS", raising=False)
    assert _long_tool_capacity() == MCP_LONG_TOOL_THREADS_DEFAULT


def test_capacity_env_override(monkeypatch):
    monkeypatch.setenv("KB_MCP_LONG_TOOL_THREADS", "3")
    assert _long_tool_capacity() == 3


def test_capacity_env_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("KB_MCP_LONG_TOOL_THREADS", "abc")
    assert _long_tool_capacity() == MCP_LONG_TOOL_THREADS_DEFAULT


@pytest.mark.parametrize("raw", ["0", "-5"])
def test_capacity_env_floor_is_one(monkeypatch, raw):
    monkeypatch.setenv("KB_MCP_LONG_TOOL_THREADS", raw)
    assert _long_tool_capacity() == 1


@pytest.mark.parametrize("raw", ["1", "true", "YES", " True "])
def test_kill_switch_truthy_variants(monkeypatch, raw):
    monkeypatch.setenv("KB_DISABLE_MCP_LONG_TOOL_LIMITER", raw)
    assert _limiter_disabled() is True


@pytest.mark.parametrize("raw", ["", "0", "no", "off"])
def test_kill_switch_falsy_variants(monkeypatch, raw):
    monkeypatch.setenv("KB_DISABLE_MCP_LONG_TOOL_LIMITER", raw)
    assert _limiter_disabled() is False


def test_get_limiter_is_not_the_default_limiter(monkeypatch):
    """R1 P2 — the whole point is ISOLATION from the default limiter.

    Every other limiter assertion (isinstance / capacity / per-loop / peak
    concurrency) still passes if `_get_limiter()` returns the DEFAULT
    limiter with its capacity mutated, which preserves starvation exactly.
    This is the test that rejects that implementation.
    """
    monkeypatch.setenv("KB_MCP_LONG_TOOL_THREADS", "5")
    monkeypatch.delenv("KB_DISABLE_MCP_LONG_TOOL_LIMITER", raising=False)

    async def run():
        lim = _get_limiter()
        default = anyio.to_thread.current_default_thread_limiter()
        assert lim is not default
        # And the dedicated budget must not have been achieved by mutating
        # the shared one — the default keeps anyio's own capacity.
        assert lim.total_tokens == 5
        assert default.total_tokens == 40

    anyio.run(run)


def test_get_limiter_same_loop_returns_cached_instance(monkeypatch):
    monkeypatch.setenv("KB_MCP_LONG_TOOL_THREADS", "5")
    monkeypatch.delenv("KB_DISABLE_MCP_LONG_TOOL_LIMITER", raising=False)

    async def run():
        lim = _get_limiter()
        assert isinstance(lim, anyio.CapacityLimiter)
        assert lim.total_tokens == 5
        assert _get_limiter() is lim
        assert _get_limiter() is lim

    anyio.run(run)


def test_get_limiter_distinct_per_concurrently_live_loop(monkeypatch):
    """R1 P2 — two SIMULTANEOUSLY LIVE loops get distinct limiters.

    The original version ran two sequential `anyio.run()` calls and asserted
    the limiters differed. That proves only that the first loop was garbage
    collected and its WeakKeyDictionary entry evicted — it never exercises
    two live keys, which is the case per-loop keying exists for.
    """
    monkeypatch.setenv("KB_MCP_LONG_TOOL_THREADS", "5")
    monkeypatch.delenv("KB_DISABLE_MCP_LONG_TOOL_LIMITER", raising=False)

    both_started = threading.Barrier(2, timeout=10)
    results: dict[int, object] = {}
    lock = threading.Lock()

    def worker(idx: int) -> None:
        async def run():
            lim = _get_limiter()
            # Hold this loop alive until the other loop has its limiter too,
            # so both keys are live in the cache simultaneously.
            both_started.wait()
            await anyio.sleep(0.05)
            assert _get_limiter() is lim, "same-loop lookup must stay stable"
            with lock:
                results[idx] = lim

        anyio.run(run)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert set(results) == {0, 1}, "both loops must have produced a limiter"
    assert results[0] is not results[1], "concurrently-live loops must not share a limiter"


def test_get_limiter_kill_switch_returns_none(monkeypatch):
    monkeypatch.setenv("KB_DISABLE_MCP_LONG_TOOL_LIMITER", "1")

    async def run():
        return _get_limiter()

    assert anyio.run(run) is None


# ── Offload wrapper behaviour ────────────────────────────────────────


def test_async_offload_routes_through_dedicated_limiter(monkeypatch):
    monkeypatch.delenv("KB_DISABLE_MCP_LONG_TOOL_LIMITER", raising=False)
    captured = {}
    real_run_sync = anyio.to_thread.run_sync

    async def spy(func, *args, **kwargs):
        captured["limiter"] = kwargs.get("limiter")
        captured["default"] = anyio.to_thread.current_default_thread_limiter()
        return await real_run_sync(func, *args, **kwargs)

    monkeypatch.setattr(anyio.to_thread, "run_sync", spy)

    def impl(x: int = 1) -> str:
        return f"ok{x}"

    wrapped = async_offload(impl)
    assert anyio.run(wrapped) == "ok1"
    assert isinstance(captured["limiter"], anyio.CapacityLimiter)
    # R1 P2 — isinstance alone passes for the DEFAULT limiter.
    assert captured["limiter"] is not captured["default"]


def test_registered_tool_offloads_through_dedicated_limiter(monkeypatch):
    """R1 P2 — spy through an ACTUALLY REGISTERED tool, not just async_offload().

    The isolated `async_offload()` tests stay green even if
    `register_long_tool` registered some other wrapper that passed
    `limiter=None`. This drives the real FastMCP-registered coroutine.
    """
    monkeypatch.delenv("KB_DISABLE_MCP_LONG_TOOL_LIMITER", raising=False)
    captured = {}
    real_run_sync = anyio.to_thread.run_sync

    async def spy(func, *args, **kwargs):
        captured.setdefault("limiter", kwargs.get("limiter"))
        captured.setdefault("default", anyio.to_thread.current_default_thread_limiter())
        return await real_run_sync(func, *args, **kwargs)

    monkeypatch.setattr(anyio.to_thread, "run_sync", spy)

    async def run():
        tool = await mcp.get_tool("kb_query")
        return await tool.fn(question="")

    assert anyio.run(run) == "Error: Question cannot be empty."
    assert isinstance(captured["limiter"], anyio.CapacityLimiter), (
        "registered tool did not offload through a CapacityLimiter"
    )
    assert captured["limiter"] is not captured["default"]


def test_async_offload_kill_switch_uses_default_pool(monkeypatch):
    monkeypatch.setenv("KB_DISABLE_MCP_LONG_TOOL_LIMITER", "1")
    captured = {"limiter": "unset"}
    real_run_sync = anyio.to_thread.run_sync

    async def spy(func, *args, **kwargs):
        captured["limiter"] = kwargs.get("limiter")
        return await real_run_sync(func, *args, **kwargs)

    monkeypatch.setattr(anyio.to_thread, "run_sync", spy)

    wrapped = async_offload(lambda: "ok")
    assert anyio.run(wrapped) == "ok"
    assert captured["limiter"] is None


def test_async_offload_forwards_kwargs():
    def impl(a: str, b: int = 0) -> str:
        return f"{a}:{b}"

    wrapped = async_offload(impl)

    async def run():
        return await wrapped("x", b=7)

    assert anyio.run(run) == "x:7"


def test_limiter_admits_exactly_capacity_concurrently(monkeypatch):
    """R1 P2 — assert EXACTLY the configured capacity, both directions.

    The original `1 <= peak <= 2` passed when capacity 2 behaved as capacity
    1 (a too-tight limiter is also a bug), and a slow machine could let an
    UNBOUNDED implementation report a peak of 1-2 by chance. This version
    uses a barrier that only releases once exactly `capacity` workers are
    inside the critical section, so it cannot pass with fewer; a follow-up
    assertion proves the remaining workers were genuinely held out.
    """
    capacity = 3
    total = 8
    assert total > capacity, "vacuous unless more workers than capacity are queued"
    monkeypatch.setenv("KB_MCP_LONG_TOOL_THREADS", str(capacity))
    monkeypatch.delenv("KB_DISABLE_MCP_LONG_TOOL_LIMITER", raising=False)

    # NOTE: deliberately NOT threading.Barrier — a Barrier is reusable, so a
    # trailing wave smaller than `parties` blocks forever when total is not a
    # multiple of capacity. Counter + Event is wave-count independent.
    filled = threading.Event()  # set once `capacity` workers are inside at once
    release = threading.Event()  # first wave holds the budget until we assert
    lock = threading.Lock()
    state = {"active": 0, "peak": 0, "admitted": 0, "admitted_at_fill": None}

    def work() -> str:
        with lock:
            state["active"] += 1
            state["admitted"] += 1
            state["peak"] = max(state["peak"], state["active"])
            first_wave = state["admitted"] <= capacity
            if state["active"] == capacity and not filled.is_set():
                state["admitted_at_fill"] = state["admitted"]
                filled.set()
        if first_wave:
            release.wait(timeout=10)
        time.sleep(0.02)
        with lock:
            state["active"] -= 1
        return "ok"

    wrapped = async_offload(work)

    async def main():
        async with anyio.create_task_group() as tg:
            for _ in range(total):
                tg.start_soon(wrapped)
            # Runs on the DEFAULT limiter, so it is not competing for the
            # long budget it is waiting on.
            reached = await anyio.to_thread.run_sync(functools.partial(filled.wait, 10.0))
            # Too TIGHT is a bug too: capacity 3 behaving as 1 never fills.
            assert reached, f"limiter never admitted {capacity} workers concurrently"
            with lock:
                # While the first wave is held, no further worker may enter.
                assert state["active"] == capacity, (
                    f"{state['active']} active while budget should be exactly {capacity}"
                )
                assert state["admitted_at_fill"] == capacity, (
                    f"{state['admitted_at_fill']} admitted at fill; the remaining "
                    f"{total - capacity} workers were not held out"
                )
            release.set()

    anyio.run(main)
    # Too loose → peak exceeds capacity.
    assert state["peak"] == capacity, (
        f"peak concurrency {state['peak']} != configured capacity {capacity}"
    )
    assert state["admitted"] == total, "every queued worker should eventually run"


def test_long_pool_saturation_does_not_block_default_pool(monkeypatch):
    """R1 P2 — the behavioural claim: a short call proceeds while long calls saturate.

    This is the assertion that actually encodes the bug being fixed. With
    the long budget fully occupied and MORE long calls queued behind it, a
    call submitted to the DEFAULT limiter must still complete promptly.
    A `_get_limiter()` that returned the default limiter would deadlock or
    time out here.
    """
    capacity = 2
    monkeypatch.setenv("KB_MCP_LONG_TOOL_THREADS", str(capacity))
    monkeypatch.delenv("KB_DISABLE_MCP_LONG_TOOL_LIMITER", raising=False)

    filled = threading.Event()
    release = threading.Event()
    short_done = threading.Event()
    lock = threading.Lock()
    state = {"active": 0}

    def long_work() -> str:
        with lock:
            state["active"] += 1
            if state["active"] == capacity:
                filled.set()
        release.wait(timeout=10)
        with lock:
            state["active"] -= 1
        return "long"

    def short_work() -> str:
        short_done.set()
        return "short"

    wrapped_long = async_offload(long_work)

    async def main():
        async with anyio.create_task_group() as tg:
            for _ in range(6):  # `capacity` admitted, the rest queued behind
                tg.start_soon(wrapped_long)
            reached = await anyio.to_thread.run_sync(functools.partial(filled.wait, 10.0))
            assert reached, "long budget never filled"
            # Long budget is saturated AND has 4 calls queued. A DEFAULT-limiter
            # call must still complete promptly — this is the starvation claim.
            with anyio.fail_after(5):
                assert await anyio.to_thread.run_sync(short_work) == "short"
            release.set()

    anyio.run(main)
    assert short_done.is_set()


# ── Instructions surface (backlog: "surface the concurrency model") ──


def test_instructions_surface_concurrency_model():
    text = mcp.instructions or ""
    assert "## Concurrency" in text
    assert "KB_MCP_LONG_TOOL_THREADS" in text
    assert "KB_DISABLE_MCP_LONG_TOOL_LIMITER" in text
    assert str(MCP_LONG_TOOL_THREADS_DEFAULT) in text
    for name in EXPECTED_LONG_TOOLS:
        assert f"`{name}`" in text, f"{name} missing from Concurrency note"
