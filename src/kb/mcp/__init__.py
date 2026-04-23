"""MCP server package — tools split into focused modules.

Cycle 23 AC4 — tool-module registration is deferred from package init to
first attribute access of ``kb.mcp.mcp`` (or to ``main()`` at server
startup). A bare ``import kb.mcp`` no longer pulls the heavy transitive
deps (``anthropic``, ``networkx``, ``sentence-transformers``) into
``sys.modules``; they load only when a caller actually reaches for the
server object via ``from kb.mcp import mcp`` — that attribute access
triggers a PEP 562 ``__getattr__`` which imports the four tool
submodules (``browse``, ``core``, ``health``, ``quality``), letting each
``@mcp.tool()`` decorator register its handlers against the cached
FastMCP instance.

Explicit submodule imports (``from kb.mcp import core``) still work
unchanged — Python's import machinery loads the submodule normally and
the decorator side effects run. The lazy path exists for callers that
only need ``mcp`` or ``main`` (CLI entry, tests listing tools, the
``kb.mcp_server`` backward-compat shim).

``test_cycle23_mcp_boot_lean.py`` pins the boot-lean contract;
``test_v070.py::test_mcp_all_tools_registered`` +
``test_cycle9_mcp_app.py::test_instructions_tool_names_sorted_within_groups``
pin the tool-registration contract.
"""

__all__ = ["mcp", "main"]


def _register_all_tools() -> None:
    """Import tool modules to trigger ``@mcp.tool()`` registration side-effects.

    Idempotent — Python caches module imports, so calling this multiple
    times (once on first ``kb.mcp.mcp`` access, again at ``main()``
    startup) does no extra work.
    """
    # noqa: F401 — imports are for decorator side effects, no local use.
    from kb.mcp import browse, core, health, quality  # noqa: F401


def __getattr__(name: str):
    """PEP 562 lazy accessor for the server object.

    ``from kb.mcp import mcp`` lands here, registers the tool submodules,
    caches the resolved FastMCP instance in ``globals()`` so subsequent
    access is free. Names other than ``mcp`` raise ``AttributeError``
    (closed-allowlist discipline matching ``kb.mcp.core``).
    """
    if name == "mcp":
        _register_all_tools()
        from kb.mcp.app import mcp as _mcp

        globals()["mcp"] = _mcp
        return _mcp
    raise AttributeError(f"module 'kb.mcp' has no attribute {name!r}")


def main() -> None:
    """Run the MCP server (stdio transport)."""
    import logging

    _register_all_tools()
    from kb.mcp.app import mcp as _mcp

    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")

    # Cycle 26 AC2 — warm-load vector embedding model in background (best-effort).
    # Function-local imports preserve cycle-23 AC4 boot-lean contract (CONDITION 8):
    # bare `import kb.mcp` must not pull `kb.query.embeddings` or `kb.config` into
    # sys.modules. The `except RuntimeError` clause (CONDITION 11 / Q6) is intended
    # to swallow `Thread.start()` resource-exhaustion but also covers any
    # RuntimeError from the function-local imports — harmless since MCP would
    # fail to serve queries either way. Broader `except Exception` covers any
    # other setup-path failure; MCP always boots.
    try:
        from kb.config import WIKI_DIR
        from kb.query.embeddings import maybe_warm_load_vector_model

        maybe_warm_load_vector_model(WIKI_DIR)
    except RuntimeError as exc:
        logging.getLogger(__name__).warning("Warm-load thread failed to start: %s", exc)
    except Exception:
        logging.getLogger(__name__).exception("Warm-load setup failed")

    _mcp.run()
