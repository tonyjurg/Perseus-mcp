import asyncio

import httpx
import pytest

from perseus_mcp import server


def test_shared_client_is_reused_within_one_event_loop() -> None:
    async def scenario() -> tuple[int, int]:
        first = id(await server._shared_client())
        second = id(await server._shared_client())
        return first, second

    first, second = asyncio.run(scenario())
    assert first == second


def test_shared_client_is_recreated_and_closed_across_event_loops() -> None:
    clients: list[httpx.AsyncClient] = []

    async def get_client() -> httpx.AsyncClient:
        client = await server._shared_client()
        clients.append(client)
        return client

    first = asyncio.run(get_client())
    second = asyncio.run(get_client())
    # Each asyncio.run() call uses a fresh event loop; the client must be
    # recreated rather than reused across loops, or requests would fail. The
    # replaced client must also be closed so its resources are not leaked.
    assert first is not second
    assert first.is_closed is True


def test_shared_client_recovers_when_previous_loop_is_already_closed(
    monkeypatch,
) -> None:
    clients = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.is_closed = False
            clients.append(self)

        async def aclose(self):
            self.is_closed = True
            raise RuntimeError("Event loop is closed")

    monkeypatch.setattr(server.httpx, "AsyncClient", FakeClient)

    async def get_client():
        return await server._shared_client()

    first = asyncio.run(get_client())
    second = asyncio.run(get_client())

    assert first is not second
    assert first.is_closed is True
    server._HTTP_CLIENT = None
    server._HTTP_CLIENT_LOOP = None


def test_aclose_http_client_closes_and_resets_client() -> None:
    async def scenario() -> bool:
        client = await server._shared_client()
        await server.aclose_http_client()
        return client.is_closed

    is_closed = asyncio.run(scenario())
    assert is_closed is True
    assert server._HTTP_CLIENT is None


def test_get_reuses_shared_client_across_calls(monkeypatch) -> None:
    seen_client_ids: list[int] = []

    class FakeResponse:
        text = "ok"

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        is_closed = False

        async def get(self, url, params=None, timeout=20.0):
            seen_client_ids.append(id(self))
            return FakeResponse()

    fake_client = FakeClient()

    async def get_fake_client():
        return fake_client

    monkeypatch.setattr(server, "_shared_client", get_fake_client)

    async def scenario() -> None:
        await server._get("https://example.invalid/a")
        await server._get("https://example.invalid/b")

    asyncio.run(scenario())

    assert seen_client_ids == [id(fake_client), id(fake_client)]


def test_get_raises_for_non_2xx_status(monkeypatch) -> None:
    class FakeResponse:
        text = "error body"

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError(
                "boom", request=httpx.Request("GET", "https://example.invalid"), response=None
            )

    class FakeClient:
        is_closed = False

        async def get(self, url, params=None, timeout=20.0):
            return FakeResponse()

    async def get_fake_client():
        return FakeClient()

    monkeypatch.setattr(server, "_shared_client", get_fake_client)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(server._get("https://example.invalid/a"))
