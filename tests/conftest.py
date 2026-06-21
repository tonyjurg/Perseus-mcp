import asyncio

import pytest

from perseus_mcp import server


@pytest.fixture(autouse=True)
def _close_shared_http_client_after_test():
    """Close perseus_mcp's shared httpx.AsyncClient after every test.

    Each test that drives the server through ``asyncio.run(...)`` runs in
    its own event loop. The shared client in ``server._shared_client()``
    detects a loop change and recreates itself automatically, but closing it
    explicitly here keeps tests from leaking unclosed clients/connections
    into the next loop and avoids ResourceWarning noise in test output.
    """
    yield
    if server._HTTP_CLIENT is not None:
        asyncio.run(server.aclose_http_client())
