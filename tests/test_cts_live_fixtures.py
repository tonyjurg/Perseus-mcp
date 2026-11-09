"""Offline regressions using exact responses from the public Perseus service."""

import asyncio
import time
from functools import partial
from pathlib import Path

import httpx
import pytest

from perseus_mcp import server
from perseus_mcp.upstream import UpstreamFailure, validate_cts


FIXTURES = Path(__file__).parent / "fixtures" / "cts"
OPERATIONS = ["GetPassage", "GetPassagePlus", "GetValidReff", "GetCapabilities"]
URN = "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.1"


@pytest.fixture(params=OPERATIONS)
def response(request):
    operation = request.param
    return operation, (FIXTURES / f"{operation}.xml").read_text(encoding="utf-8")


def test_live_response_validates_and_parses(response):
    operation, body = response
    validate_cts(body, operation)
    if operation in {"GetPassage", "GetPassagePlus"}:
        assert "μῆνιν ἄειδε" in server._passage_plaintext_from_xml(body)
    elif operation == "GetValidReff":
        assert URN in server._reference_urns_from_xml(body)
    else:
        root = server._capabilities_root(body)
        assert any(e.tag.endswith("}textgroup") for e in root.iter())


def test_live_response_through_cts_request(monkeypatch, response):
    operation, body = response
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, text=body, headers={"Content-Type": "text/xml"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:

            async def shared():
                return client

            monkeypatch.setattr(server, "_shared_client", shared)
            assert await server._cts_request(operation, urn=URN) == body

    asyncio.run(run())
    assert len(requests) == 1
    assert requests[0].url.params["request"] == operation


@pytest.mark.parametrize("source", ["memory", "disk", "upstream"])
def test_valid_cts_cache_is_preserved(monkeypatch, tmp_path, response, source):
    operation, body = response
    monkeypatch.setenv("PERSEUS_MCP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("PERSEUS_MCP_CACHE_TTL_SECONDS", "0")
    monkeypatch.delenv("PERSEUS_MCP_DISABLE_CACHE", raising=False)
    monkeypatch.setattr(server, "_MEMORY_CACHE", {})
    parts = {"request": operation}
    key = server._cache_key(parts)
    path = server._cache_path("cts", key, "xml")
    if source != "upstream":
        path.parent.mkdir(parents=True)
        path.write_text(body, encoding="utf-8")
    if source == "memory":
        server._MEMORY_CACHE[f"cts:{key}"] = (time.time(), body)
    calls = []

    async def fetch():
        calls.append(True)
        assert source == "upstream", "Valid cached CTS must not be refetched"
        return body

    async def run():
        for _ in range(2):
            assert (
                await server._cached_text(
                    "cts",
                    parts,
                    fetch,
                    validator=partial(validate_cts, request=operation),
                )
                == body
            )

    asyncio.run(run())
    assert len(calls) == (1 if source == "upstream" else 0)
    assert path.read_text(encoding="utf-8") == body
    assert server._MEMORY_CACHE[f"cts:{key}"][1] == body


@pytest.mark.parametrize(
    "namespace",
    ["http://chs.harvard.edu/xmlns/cts3", "http://chs.harvard.edu/xmlns/cts3/ti"],
)
@pytest.mark.parametrize(
    "detail,code",
    [("InvalidURN", "INVALID_URN"), ("Unavailable", "UPSTREAM_CTS_ERROR")],
)
def test_cts3_protocol_errors_remain_typed(namespace, detail, code):
    with pytest.raises(UpstreamFailure) as caught:
        validate_cts(
            f'<cts:CTSError xmlns:cts="{namespace}"><cts:message>'
            f"{detail}</cts:message></cts:CTSError>",
            "GetPassage",
        )
    assert caught.value.code == code


def test_cts3_wrong_operation_is_still_rejected():
    body = (FIXTURES / "GetValidReff.xml").read_text(encoding="utf-8")
    with pytest.raises(UpstreamFailure, match="INVALID_PAYLOAD"):
        validate_cts(body, "GetPassage")
