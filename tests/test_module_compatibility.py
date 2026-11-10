"""Protect notebook imports and the MCP contract during implementation refactors."""

import ast
import asyncio
import importlib
import inspect
import json
from pathlib import Path

from fastmcp import Client

from perseus_mcp import cache, greek, http, server

ROOT = Path(__file__).resolve().parents[1]


def test_tool_contract_matches_monolithic_server():
    """Compare all 23 tool schemas and signatures with main before extraction."""
    # Captured from 709555e before moving definitions. Only protocol fields
    # relevant to callers are retained, excluding FastMCP's incidental metadata.
    expected = json.loads(
        (ROOT / "tests/fixtures/server_api.json").read_text(encoding="utf-8")
    )

    async def contract():
        """Use the same in-process client connection as the existing notebooks."""
        async with Client(server.mcp) as client:
            tools = await client.list_tools()
        assert len(tools) == len(expected) == 23
        return {
            tool.name: {
                "schema": {
                    key: tool.model_dump(mode="json")[key]
                    for key in ("description", "inputSchema", "outputSchema")
                },
                "signature": str(inspect.signature(getattr(server, tool.name))),
            }
            for tool in tools
        }

    assert asyncio.run(contract()) == expected


def test_legacy_imports_share_functions_and_state(monkeypatch):
    """Facade writes and owner writes both remain visible to old notebook code."""
    from perseus_mcp.server import _normalize_query_for_search, get_passage
    from perseus_mcp.tools.cts import get_passage as implementation

    assert get_passage is implementation
    assert _normalize_query_for_search is greek._normalize_query_for_search
    assert _normalize_query_for_search("lo/gos") == "Î»ÏŒÎ³Î¿Ï‚"
    assert server._MEMORY_CACHE is cache._MEMORY_CACHE
    client_marker = object()
    monkeypatch.setattr(server, "_HTTP_CLIENT", client_marker)
    assert http._HTTP_CLIENT is client_marker
    monkeypatch.setattr(http, "_HTTP_CLIENT_LOOP", client_marker)
    assert server._HTTP_CLIENT_LOOP is client_marker
    # Restore before the shared-client cleanup fixture tries to close the marker.
    monkeypatch.undo()


def test_reimport_facade_preserves_application_and_registered_tools():
    """Reloading the facade must not create another application or tool set."""
    application = server.mcp
    passage = server.get_passage
    importlib.reload(server)
    assert server.mcp is application
    assert server.get_passage is passage


def test_all_package_modules_classes_and_functions_have_docstrings():
    """Keep the Sphinx source documentation complete as modules evolve."""
    missing = []
    for path in (ROOT / "src/perseus_mcp").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not ast.get_docstring(tree):
            missing.append(str(path.relative_to(ROOT)))
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ) and not ast.get_docstring(node):
                missing.append(f"{path.name}:{node.lineno}:{node.name}")
    assert missing == []
