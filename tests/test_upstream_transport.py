import asyncio
import gzip
import json

import httpx
import pytest
from fastmcp import Client

from perseus_mcp import server
from perseus_mcp.upstream import DEFAULT_RETRY_POLICY, UpstreamFailure


class Stream(httpx.AsyncByteStream):
    def __init__(self, chunks, error=None):
        self.chunks = chunks
        self.error = error
        self.reads = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            self.reads += 1
            yield chunk
        if self.error:
            raise self.error

    async def aclose(self):
        self.closed = True


def get(monkeypatch, response):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: response)
        ) as client:

            async def shared():
                return client

            monkeypatch.setattr(server, "_shared_client", shared)
            return await server._get("https://example.invalid/private")

    return asyncio.run(run())


@pytest.mark.parametrize(
    "exception,code",
    [
        (httpx.ConnectTimeout, "UPSTREAM_TIMEOUT"),
        (httpx.ReadTimeout, "UPSTREAM_TIMEOUT"),
        (httpx.WriteTimeout, "UPSTREAM_TIMEOUT"),
        (httpx.PoolTimeout, "UPSTREAM_TIMEOUT"),
        (httpx.ConnectError, "UPSTREAM_CONNECTION_ERROR"),
        (httpx.ReadError, "UPSTREAM_CONNECTION_ERROR"),
        (httpx.RemoteProtocolError, "UPSTREAM_TRANSPORT_ERROR"),
        (httpx.ProxyError, "UPSTREAM_TRANSPORT_ERROR"),
        (httpx.TooManyRedirects, "UPSTREAM_TRANSPORT_ERROR"),
    ],
)
@pytest.mark.parametrize("after_headers", [False, True])
def test_transport_errors_are_safe_mcp_errors(
    monkeypatch, exception, code, after_headers
):
    calls = []
    stream = Stream([b"partial"], exception("private connection details"))

    def respond(request):
        calls.append(request)
        if not after_headers:
            raise exception("private connection details")
        return httpx.Response(200, stream=stream)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond)
        ) as http_client:

            async def shared():
                return http_client

            monkeypatch.setattr(server, "_shared_client", shared)
            async with Client(server.mcp) as client:
                result = await client.call_tool_mcp(
                    "get_passage", {"urn": "urn:cts:private"}
                )
                assert result.isError
                data = json.loads(result.content[0].text)
                assert data["code"] == code
                assert data["upstream_http_status"] == (200 if after_headers else None)
                assert "private" not in result.content[0].text

    asyncio.run(run())
    assert len(calls) == 1
    if after_headers:
        assert stream.closed


@pytest.mark.parametrize("length", [None, "1", "invalid"])
def test_size_limit_stops_chunked_or_understated_response(monkeypatch, length):
    monkeypatch.setenv("PERSEUS_MCP_MAX_RESPONSE_BYTES", "8")
    stream = Stream([b"1234", b"5678", b"9", b"unread"])
    headers = {} if length is None else {"Content-Length": length}
    with pytest.raises(UpstreamFailure, match="UPSTREAM_RESPONSE_TOO_LARGE") as caught:
        get(monkeypatch, httpx.Response(200, headers=headers, stream=stream))
    assert caught.value.status == 200
    assert stream.reads == 3
    assert stream.closed


def test_large_content_length_rejected_before_reading(monkeypatch):
    monkeypatch.setenv("PERSEUS_MCP_MAX_RESPONSE_BYTES", "8")
    stream = Stream([b"unread"])
    with pytest.raises(UpstreamFailure, match="UPSTREAM_RESPONSE_TOO_LARGE"):
        get(
            monkeypatch,
            httpx.Response(200, headers={"Content-Length": "9"}, stream=stream),
        )
    assert stream.reads == 0
    assert stream.closed


def test_compressed_response_is_limited_by_decoded_size(monkeypatch):
    monkeypatch.setenv("PERSEUS_MCP_MAX_RESPONSE_BYTES", "128")
    compressed = gzip.compress(b"a" * 1024)
    assert len(compressed) < 128
    stream = Stream([compressed])
    with pytest.raises(UpstreamFailure, match="UPSTREAM_RESPONSE_TOO_LARGE"):
        get(
            monkeypatch,
            httpx.Response(
                200,
                headers={
                    "Content-Encoding": "gzip",
                    "Content-Length": str(len(compressed)),
                },
                stream=stream,
            ),
        )
    assert stream.closed


def test_exact_limit_and_split_utf8_are_supported(monkeypatch):
    monkeypatch.setenv("PERSEUS_MCP_MAX_RESPONSE_BYTES", "4")
    stream = Stream([b"\xce", b"\xbc\xce", b"\xb7"])
    assert get(monkeypatch, httpx.Response(200, stream=stream)) == "μη"
    assert stream.closed


def test_response_charset_is_respected(monkeypatch):
    assert (
        get(
            monkeypatch,
            httpx.Response(
                200,
                headers={"Content-Type": "text/plain; charset=iso-8859-1"},
                stream=Stream([b"caf\xe9"]),
            ),
        )
        == "café"
    )


def test_redirect_bodies_are_closed_without_buffering(monkeypatch):
    monkeypatch.setenv("PERSEUS_MCP_MAX_RESPONSE_BYTES", "4")
    redirects = [Stream([b"huge unread body"]), Stream([b"also unread"])]
    final = Stream([b"done"])
    paths = []

    def respond(request):
        paths.append(request.url.path)
        if len(paths) < 3:
            return httpx.Response(
                302,
                headers={"Location": f"/hop{len(paths)}"},
                stream=redirects[len(paths) - 1],
            )
        return httpx.Response(200, stream=final)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:

            async def shared():
                return client

            monkeypatch.setattr(server, "_shared_client", shared)
            assert await server._get("https://example.invalid/start") == "done"

    asyncio.run(run())
    assert paths == ["/start", "/hop1", "/hop2"]
    assert all(stream.closed and stream.reads == 0 for stream in redirects)
    assert final.closed


def test_redirect_loop_is_bounded_and_typed(monkeypatch):
    streams = []

    def respond(request):
        stream = Stream([b"unread"])
        streams.append(stream)
        return httpx.Response(302, headers={"Location": "/again"}, stream=stream)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond), max_redirects=2
        ) as client:

            async def shared():
                return client

            monkeypatch.setattr(server, "_shared_client", shared)
            with pytest.raises(UpstreamFailure, match="UPSTREAM_TRANSPORT_ERROR"):
                await server._get("https://example.invalid/start")

    asyncio.run(run())
    assert len(streams) == 3
    assert all(stream.closed and stream.reads == 0 for stream in streams)


@pytest.mark.parametrize("value", ["0", "-1", "unlimited"])
def test_invalid_size_setting_fails_before_network(monkeypatch, value):
    monkeypatch.setenv("PERSEUS_MCP_MAX_RESPONSE_BYTES", value)
    with pytest.raises(ValueError, match="positive integer"):
        asyncio.run(server._get("https://example.invalid"))


@pytest.mark.parametrize("code,allowed", list(DEFAULT_RETRY_POLICY.items()))
def test_retry_policy_defaults_and_overrides(monkeypatch, code, allowed):
    monkeypatch.delenv("PERSEUS_MCP_RETRY_POLICY", raising=False)
    error = UpstreamFailure(code, "safe")
    assert json.loads(error.as_json())["automatic_retry_allowed"] is allowed
    monkeypatch.setenv("PERSEUS_MCP_RETRY_POLICY", json.dumps({code: not allowed}))
    assert json.loads(error.as_json())["automatic_retry_allowed"] is not allowed


@pytest.mark.parametrize(
    "policy", ["bad", "[]", '{"UNKNOWN": true}', '{"UPSTREAM_TIMEOUT": 1}']
)
def test_invalid_retry_policy_is_rejected(monkeypatch, policy):
    monkeypatch.setenv("PERSEUS_MCP_RETRY_POLICY", policy)
    with pytest.raises(ValueError, match="PERSEUS_MCP_RETRY_POLICY"):
        UpstreamFailure("UPSTREAM_TIMEOUT", "safe").as_json()


@pytest.mark.parametrize("failure", ["timeout", "size", "http"])
def test_failed_stream_is_never_cached(monkeypatch, tmp_path, failure):
    monkeypatch.setenv("PERSEUS_MCP_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("PERSEUS_MCP_DISABLE_CACHE", raising=False)
    monkeypatch.setenv("PERSEUS_MCP_MAX_RESPONSE_BYTES", "8")
    monkeypatch.setattr(server, "_MEMORY_CACHE", {})
    stream = Stream(
        [b"123456789"] if failure == "size" else [b"bad"],
        httpx.ReadTimeout("private") if failure == "timeout" else None,
    )

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    503 if failure == "http" else 200, stream=stream
                )
            )
        ) as client:

            async def shared():
                return client

            monkeypatch.setattr(server, "_shared_client", shared)
            with pytest.raises(UpstreamFailure):
                await server._get_capabilities_cached()

    asyncio.run(run())
    assert not server._MEMORY_CACHE
    assert not list(tmp_path.rglob("*.xml"))
    assert stream.closed
