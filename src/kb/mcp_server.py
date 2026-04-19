"""Back-compat shim — tools live in kb.mcp package."""

from kb.mcp import main, mcp  # noqa: F401 — re-exports for back-compat

if __name__ == "__main__":
    main()
