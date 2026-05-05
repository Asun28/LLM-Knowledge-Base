"""MCP tool error boundary decorator for exception sanitization.

Cycle 65 AC21 — wraps MCP tool functions to catch exceptions,
sanitize sensitive error text, and return a safe error string.
"""

from __future__ import annotations

import functools
import logging

from kb.utils.sanitize import sanitize_error_text


def _mcp_error_boundary(fn):
    """Decorator to catch exceptions and sanitize error text for MCP tools.

    Applied BELOW @mcp.tool() in the decorator chain so exceptions from
    the function body are caught before FastMCP registration.

    Stacking order:
        @mcp.tool()
        @_mcp_error_boundary
        def my_tool(...): ...
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            logging.getLogger("kb.mcp").exception("MCP tool %s raised", fn.__name__)
            return f"Error: {sanitize_error_text(exc)}"

    return wrapper
