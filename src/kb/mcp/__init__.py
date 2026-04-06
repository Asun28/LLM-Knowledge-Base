"""MCP server package — tools split into focused modules."""

# Import tool modules to trigger @mcp.tool() registration
from kb.mcp import browse, core, health, quality  # noqa: F401
from kb.mcp.app import mcp  # noqa: F401 — re-export for backward compatibility
