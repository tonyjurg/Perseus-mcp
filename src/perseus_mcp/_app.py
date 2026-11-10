"""Create the shared MCP application and translate upstream failures at tool boundaries."""

from __future__ import annotations

from functools import wraps

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from . import upstream as _upstream

__all__ = ["_upstream_tool", "mcp"]


mcp = FastMCP("perseus")


def _upstream_tool(function):
    """Register an async MCP tool while preserving its Python signature and docstring."""

    @wraps(function)
    async def wrapped(*args, **kwargs):
        """Translate an expected upstream failure into a structured MCP ToolError."""
        try:
            return await function(*args, **kwargs)
        except _upstream.UpstreamFailure as exc:
            raise ToolError(exc.as_json()) from None

    mcp.tool(wrapped)
    return wrapped
