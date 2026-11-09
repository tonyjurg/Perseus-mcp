import asyncio
import json

import httpx
import pytest

from perseus_mcp import server
from perseus_mcp.upstream import UpstreamFailure


class TrickleStream(httpx.AsyncByteStream):
    def __init__(self):
        self.reads = 0
        self.closed = False
        self.started = asyncio.Event()

    async def __aiter__(self):
        self.started.set()
        while True:
            self.reads += 1
            yield b" "
            await asyncio.sleep(0.01)

    async def aclose(self):
        self.closed = True


def test_total_deadline_stops_trickle_and_never_caches_partial_body(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("PERSEUS_MCP_BODY_TIMEOUT_SECONDS", "0.05")
    monkeypatch.setenv("PERSEUS_MCP_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("PERSEUS_MCP_DISABLE_CACHE", raising=False)
    monkeypatch.setattr(server, "_MEMORY_CACHE", {})
    calls = []

    async def run():
        stream = TrickleStream()

        def respond(request):
            calls.append(request)
            return httpx.Response(200, stream=stream)

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:

            async def shared():
                return client

            monkeypatch.setattr(server, "_shared_client", shared)
            with pytest.raises(UpstreamFailure) as caught:
                # A watchdog makes a missing body deadline fail instead of hanging.
                await asyncio.wait_for(server._get_capabilities_cached(), timeout=2)
            error = json.loads(caught.value.as_json())
            assert error["code"] == "UPSTREAM_TIMEOUT"
            assert error["upstream_http_status"] == 200
        assert stream.closed
        assert stream.reads >= 1

    asyncio.run(run())
    assert len(calls) == 1
    assert not server._MEMORY_CACHE
    assert not list(tmp_path.rglob("*.xml"))


def test_external_cancellation_is_not_converted_to_upstream_timeout(monkeypatch):
    monkeypatch.setenv("PERSEUS_MCP_BODY_TIMEOUT_SECONDS", "10")

    async def run():
        stream = TrickleStream()
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, stream=stream)
            )
        ) as client:

            async def shared():
                return client

            monkeypatch.setattr(server, "_shared_client", shared)
            task = asyncio.create_task(server._get("https://example.invalid"))
            await asyncio.wait_for(stream.started.wait(), timeout=2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert stream.closed

    asyncio.run(run())


def test_finite_body_can_complete_with_configured_deadline(monkeypatch):
    monkeypatch.setenv("PERSEUS_MCP_BODY_TIMEOUT_SECONDS", "1.5")

    class FiniteStream(TrickleStream):
        async def __aiter__(self):
            yield b"first "
            await asyncio.sleep(0.01)
            yield b"second"

    async def run():
        stream = FiniteStream()
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, stream=stream)
            )
        ) as client:

            async def shared():
                return client

            monkeypatch.setattr(server, "_shared_client", shared)
            assert await server._get("https://example.invalid") == "first second"
        assert stream.closed

    asyncio.run(run())


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf", "unlimited", ""])
def test_invalid_deadline_configuration_fails_before_io(monkeypatch, value):
    monkeypatch.setenv("PERSEUS_MCP_BODY_TIMEOUT_SECONDS", value)

    async def unexpected_client():
        pytest.fail("Invalid deadline must fail before obtaining an HTTP client")

    monkeypatch.setattr(server, "_shared_client", unexpected_client)
    with pytest.raises(ValueError, match="positive finite number"):
        asyncio.run(server._get("https://example.invalid"))
