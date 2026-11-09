import asyncio

import httpx
import pytest

from perseus_mcp import server
from perseus_mcp.upstream import UpstreamFailure


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


def test_aclose_http_client_recovers_when_original_loop_is_closed(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, **kwargs):
            self.is_closed = False

        async def aclose(self):
            self.is_closed = True
            raise RuntimeError("Event loop is closed")

    monkeypatch.setattr(server.httpx, "AsyncClient", FakeClient)

    async def create_client():
        return await server._shared_client()

    client = asyncio.run(create_client())
    asyncio.run(server.aclose_http_client())

    assert client.is_closed is True
    assert server._HTTP_CLIENT is None
    assert server._HTTP_CLIENT_LOOP is None


def test_aclose_http_client_resets_state_after_unrelated_close_error() -> None:
    class FailingClient:
        is_closed = False

        async def aclose(self):
            raise RuntimeError("unexpected transport failure")

    async def scenario():
        server._HTTP_CLIENT = FailingClient()
        server._HTTP_CLIENT_LOOP = asyncio.get_running_loop()
        with pytest.raises(RuntimeError, match="unexpected transport failure"):
            await server.aclose_http_client()

    asyncio.run(scenario())

    assert server._HTTP_CLIENT is None
    assert server._HTTP_CLIENT_LOOP is None


def test_get_reuses_shared_client_across_calls(monkeypatch) -> None:
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, text="ok")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:

            async def shared():
                return client

            monkeypatch.setattr(server, "_shared_client", shared)
            assert await server._get("https://example.invalid/a") == "ok"
            assert await server._get("https://example.invalid/b") == "ok"

    asyncio.run(scenario())
    assert [request.url.path for request in requests] == ["/a", "/b"]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 500, 502, 503])
def test_get_maps_non_2xx_status(monkeypatch, status) -> None:
    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status, text="private error body")
            )
        ) as client:

            async def shared():
                return client

            monkeypatch.setattr(server, "_shared_client", shared)
            with pytest.raises(UpstreamFailure, match="UPSTREAM_HTTP_ERROR") as caught:
                await server._get("https://example.invalid/private-query")
            assert caught.value.status == status
            assert "private" not in caught.value.as_json()

    asyncio.run(scenario())


def test_get_warns_and_maps_429_error(monkeypatch) -> None:
    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429, headers={"Retry-After": "30"}, text="rate limited"
                )
            )
        ) as client:

            async def shared():
                return client

            monkeypatch.setattr(server, "_shared_client", shared)
            with (
                pytest.warns(
                    server.UpstreamRateLimitWarning,
                    match=r"HTTP 429.*Retry after 30 seconds.*not retried automatically",
                ),
                pytest.raises(UpstreamFailure, match="UPSTREAM_HTTP_ERROR") as caught,
            ):
                await server._get("https://example.invalid/rate-limited")
            assert caught.value.status == 429

    asyncio.run(scenario())
