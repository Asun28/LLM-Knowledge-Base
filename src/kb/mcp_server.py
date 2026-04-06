"""MCP server entry point — backward compatible wrapper.

The actual tools are defined in kb.mcp submodules:
  - kb.mcp.core: query, ingest, compile
  - kb.mcp.browse: search, read, list, stats
  - kb.mcp.health: lint, evolve
  - kb.mcp.quality: review, refine, lint_deep, consistency, feedback, verdicts, create_page
"""

from kb.mcp import mcp  # noqa: F401 — triggers tool registration


def main():
    """Run the MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
