"""Cycle 95 — MCP long-tool async offload (Phase 4.5 HIGH R3).

Six long-running MCP tools (kb_query / kb_lint / kb_compile / kb_ingest /
kb_ingest_content / kb_capture) register a signature-preserving ASYNC
wrapper that offloads the sync implementation to a dedicated per-event-loop
``anyio.CapacityLimiter`` (``kb.mcp._offload``), so concurrent long calls
cannot saturate FastMCP's shared default worker pool. The module attributes
stay plain sync callables — the direct-call contract every pre-cycle-95
test site relies on.
"""

import inspect
import threading
import time

import anyio
import anyio.to_thread
import pytest

# Importing the tool modules triggers @mcp.tool() registration side-effects
# (same mechanism as kb.mcp._register_all_tools).
import kb.mcp.browse  # noqa: F401
import kb.mcp.compile as mcp_compile
import kb.mcp.core as mcp_core
import kb.mcp.health as mcp_health
import kb.mcp.ingest as mcp_ingest
import kb.mcp.quality  # noqa: F401
from kb.config import MCP_LONG_TOOL_THREADS_DEFAULT
from kb.mcp._offload import (
    LONG_TOOL_NAMES,
    _get_limiter,
    _limiter_disabled,
    _long_tool_capacity,
    async_offload,
)
from kb.mcp.app import _LONG_TOOL_NOTE_NAMES, mcp

EXPECTED_LONG_TOOLS = {
    "kb_query",
    "kb_lint",
    "kb_compile",
    "kb_ingest",
    "kb_ingest_content",
    "kb_capture",
}

# Deliberately-sync sample: short/scan tools plus the context-returning
# quality tools that must NOT have been swept into the long-tool pool.
SHORT_TOOL_SAMPLE = (
    "kb_search",
    "kb_compile_scan",
    "kb_evolve",
    "kb_save_source",
    "kb_lint_deep",
    "kb_lint_consistency",
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


def test_module_attributes_remain_sync_callables():
    """Direct-call contract: every pre-cycle-95 test site calls these sync."""
    for mod, name in (
        (mcp_core, "kb_query"),
        (mcp_health, "kb_lint"),
        (mcp_compile, "kb_compile"),
        (mcp_ingest, "kb_ingest"),
        (mcp_ingest, "kb_ingest_content"),
        (mcp_ingest, "kb_capture"),
    ):
        fn = getattr(mod, name)
        assert callable(fn), name
        assert not inspect.iscoroutinefunction(fn), f"{name} module attr must stay sync"


def test_registration_list_matches_instructions_note():
    """kb.mcp._offload.LONG_TOOL_NAMES and app._LONG_TOOL_NOTE_NAMES cannot drift."""
    assert set(LONG_TOOL_NAMES) == set(_LONG_TOOL_NOTE_NAMES) == EXPECTED_LONG_TOOLS
    # No double registration (module import is cached, so each name once).
    assert len(LONG_TOOL_NAMES) == len(set(LONG_TOOL_NAMES))


def test_wrapper_schema_preserved_kb_query():
    async def check():
        tool = await mcp.get_tool("kb_query")
        props = set(tool.parameters.get("properties", {}))
        assert props == {
            "question",
            "max_results",
            "use_api",
            "conversation_context",
            "output_format",
            "save_as",
        }
        assert tool.parameters.get("required") == ["question"]
        assert (tool.description or "").startswith("Query the knowledge base.")

    anyio.run(check)


def test_wrapper_schema_preserved_kb_lint():
    async def check():
        tool = await mcp.get_tool("kb_lint")
        props = set(tool.parameters.get("properties", {}))
        assert {
            "fix",
            "augment",
            "dry_run",
            "execute",
            "auto_ingest",
            "max_gaps",
            "wiki_dir",
            "resume",
        } <= props

    anyio.run(check)


def test_wrapper_signature_follows_sync_impl():
    async def check():
        tool = await mcp.get_tool("kb_lint")
        assert inspect.signature(tool.fn) == inspect.signature(mcp_health.kb_lint)

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


def test_get_limiter_dedicated_capacity_and_per_loop_cache(monkeypatch):
    monkeypatch.setenv("KB_MCP_LONG_TOOL_THREADS", "5")
    monkeypatch.delenv("KB_DISABLE_MCP_LONG_TOOL_LIMITER", raising=False)

    async def run():
        lim = _get_limiter()
        assert isinstance(lim, anyio.CapacityLimiter)
        assert lim.total_tokens == 5
        # Same loop → cached instance.
        assert _get_limiter() is lim
        return lim

    lim1 = anyio.run(run)

    async def run2():
        return _get_limiter()

    lim2 = anyio.run(run2)
    # New event loop → new limiter (env re-read per loop).
    assert lim2 is not lim1


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
        return await real_run_sync(func, *args, **kwargs)

    monkeypatch.setattr(anyio.to_thread, "run_sync", spy)

    def impl(x: int = 1) -> str:
        return f"ok{x}"

    wrapped = async_offload(impl)
    assert anyio.run(wrapped) == "ok1"
    assert isinstance(captured["limiter"], anyio.CapacityLimiter)


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


def test_limiter_enforces_max_concurrency(monkeypatch):
    monkeypatch.setenv("KB_MCP_LONG_TOOL_THREADS", "2")
    monkeypatch.delenv("KB_DISABLE_MCP_LONG_TOOL_LIMITER", raising=False)
    lock = threading.Lock()
    state = {"active": 0, "peak": 0}

    def work() -> str:
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.05)
        with lock:
            state["active"] -= 1
        return "ok"

    wrapped = async_offload(work)

    async def main():
        async with anyio.create_task_group() as tg:
            for _ in range(6):
                tg.start_soon(wrapped)

    anyio.run(main)
    assert 1 <= state["peak"] <= 2, f"peak concurrency {state['peak']} exceeded limiter capacity"


# ── Instructions surface (backlog: "surface the concurrency model") ──


def test_instructions_surface_concurrency_model():
    text = mcp.instructions or ""
    assert "## Concurrency" in text
    assert "KB_MCP_LONG_TOOL_THREADS" in text
    assert "KB_DISABLE_MCP_LONG_TOOL_LIMITER" in text
    assert str(MCP_LONG_TOOL_THREADS_DEFAULT) in text
    for name in EXPECTED_LONG_TOOLS:
        assert f"`{name}`" in text, f"{name} missing from Concurrency note"
