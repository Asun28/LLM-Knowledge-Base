"""MCP server package — tools split into focused modules."""

# Import tool modules to trigger @mcp.tool() registration
from kb.mcp import browse, core, health, quality  # noqa: F401
from kb.mcp.app import mcp  # noqa: F401 — re-export for backward compatibility


def main() -> None:
    """Run the MCP server (stdio transport)."""
    import logging

    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    mcp.run()
