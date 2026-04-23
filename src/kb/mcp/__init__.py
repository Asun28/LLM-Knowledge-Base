"""MCP server package — tools split into focused modules.

Cycle 23 AC4 — tool-module registration is deferred from package init to
``main()``. A bare ``import kb.mcp`` no longer pulls the heavy transitive
deps (``anthropic``, ``networkx``, ``sentence-transformers``) into
``sys.modules``; they load only when the MCP server actually starts up.
Consumers that want an individual tool group can still
``from kb.mcp import core`` / ``from kb.mcp import browse`` etc. — the
``@mcp.tool()`` decorators in each submodule register on first module
load, unchanged from prior cycles.

``test_cycle23_mcp_boot_lean.py`` pins the boot-lean contract.
"""

from kb.mcp.app import mcp  # noqa: F401 — re-export for backward compatibility


def _register_all_tools() -> None:
    """Import tool modules to trigger ``@mcp.tool()`` registration side-effects.

    Called by ``main()``. Direct callers that want a specific tool group
    should import that submodule explicitly rather than calling this helper.
    """
    # noqa: F401 — imports are for decorator side effects, no local use.
    from kb.mcp import browse, core, health, quality  # noqa: F401


def main() -> None:
    """Run the MCP server (stdio transport)."""
    import logging

    _register_all_tools()

    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    mcp.run()
