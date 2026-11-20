"""Create the shared MCP application and translate upstream failures at tool boundaries."""

from __future__ import annotations

from functools import wraps

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from . import upstream as _upstream

__all__ = ["_upstream_tool", "mcp"]


mcp = FastMCP("perseus")


def _upstream_tool(
    function=None, *, read_only=True, destructive=False, open_world=True
):
    """Register a tool with advisory MCP behavior hints and structured upstream errors."""

    def register(function):
        """Preserve the public Python signature and register the annotated wrapper."""

        @wraps(function)
        async def wrapped(*args, **kwargs):
            """Translate an expected upstream failure into a structured MCP ToolError."""
            try:
                return await function(*args, **kwargs)
            except _upstream.UpstreamFailure as exc:
                raise ToolError(exc.as_json()) from None

        mcp.tool(
            wrapped,
            annotations={
                "readOnlyHint": read_only,
                "destructiveHint": destructive,
                "idempotentHint": True,
                "openWorldHint": open_world,
            },
        )
        return wrapped

    return register(function) if function is not None else register
