import asyncio
import json
import time
import xml.etree.ElementTree as ET
from functools import partial
from pathlib import Path

import httpx
import pytest
from fastmcp import Client

from perseus_mcp import server
from perseus_mcp.upstream import (
    UpstreamFailure,
    reject_challenge,
    validate_catalogue,
    validate_cts,
    validate_metadata,
    validate_passage_json,
    validate_search,
    validate_text,
)

CHALLENGE = (Path(__file__).parent / "fixtures/anubis.html").read_text(encoding="utf-8")
MALFORMED_NAVIGATION = (
    Path(__file__).parent / "fixtures/cts/navigation-malformed.html"
).read_text(encoding="utf-8")
URN = "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1"
CAPABILITIES = '<GetCapabilities xmlns="http://chs.harvard.edu/xmlns/cts"><TextInventory/></GetCapabilities>'


def mock_upstream(monkeypatch, body, status=200, content_type="text/html"):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status, text=body, headers={"Content-Type": content_type})

    async def scenario():
        return httpx.AsyncClient(transport=httpx.MockTransport(respond))

    client = asyncio.run(scenario())

    async def shared():
        return client

    monkeypatch.setattr(server, "_shared_client", shared)
    return client, requests


@pytest.mark.parametrize("status", [200, 403, 429, 503])
@pytest.mark.parametrize("content_type", ["text/html", "application/json"])
def test_challenge_precedes_http_status_and_format_checks(
    monkeypatch, status, content_type
):
    client, requests = mock_upstream(monkeypatch, CHALLENGE, status, content_type)

    async def run():
        async with client:
            with pytest.raises(UpstreamFailure) as caught:
                await server._get(server.SCAIFE_SEARCH, validator=validate_search)
            assert caught.value.code == "UPSTREAM_CHALLENGE"
            assert caught.value.status == status
            message = caught.value.as_json()
            assert "DO_NOT_EXPOSE" not in message and "PRIVATE_CLIENT" not in message
            assert json.loads(message)["automatic_retry_allowed"] is False

    asyncio.run(run())
    assert len(requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        "<html><script id='anubis_challenge'>{}</script></html>",
        '<html><head><script src="/.within.website/x/cmd/anubis/main.js"></script></head></html>',
        '\ufeff <html><title>Überprüfung</title><script id="anubis_challenge">',
    ],
)
def test_challenge_detection_does_not_depend_on_title_or_complete_page(body):
    with pytest.raises(UpstreamFailure, match="UPSTREAM_CHALLENGE"):
        reject_challenge(body)


@pytest.mark.parametrize(
    "body",
    [
        "Anubis is mentioned in this text.",
        "The literal marker anubis_challenge is not a page.",
        '{"results": [{"snippet": "<script id=\\"anubis_challenge\\">fiction</script>"}]}',
    ],
)
def test_plain_mentions_and_json_excerpts_are_not_challenges(body):
    reject_challenge(body)


@pytest.mark.parametrize(
    "validator,body",
    [
        (validate_search, "{}"),
        (validate_search, '{"results": null}'),
        (validate_search, '{"results": [42]}'),
        (validate_search, '{"results": [], "total_count": "0"}'),
        (validate_search, '{"results": [], "error": "unavailable"}'),
        (validate_search, "not json"),
        (validate_search, "<html>Unavailable</html>"),
        (validate_catalogue, '{"text_groups": null}'),
        (validate_catalogue, '{"detail": "unavailable"}'),
        (validate_metadata, '{"urn": null}'),
        (validate_passage_json, '{"urn": "urn:cts:greekLit:example"}'),
        (validate_text, "<!doctype html><h1>Service unavailable</h1>"),
    ],
)
def test_invalid_payloads_are_never_empty_results(validator, body):
    with pytest.raises(UpstreamFailure, match="INVALID_PAYLOAD"):
        validator(body)


@pytest.mark.parametrize(
    "validator,body",
    [
        (validate_search, '{"results": [], "total_count": 0}'),
        (validate_search, "[]"),
        (validate_search, '{"results": [{"passage": {}, "highlights": []}]}'),
        (validate_catalogue, '{"text_groups": []}'),
        (validate_metadata, json.dumps({"urn": URN, "kind": "edition"})),
        (validate_passage_json, json.dumps({"urn": URN, "text_html": "<p>μῆνιν</p>"})),
        (validate_text, "μῆνιν ἄειδε θεά"),
    ],
)
def test_supported_success_shapes(validator, body):
    validator(body)


@pytest.mark.parametrize(
    "body,code",
    [
        ("Invalid URN: private-request", "INVALID_URN"),
        (
            "<CTSError><message>Invalid URN: private-request</message></CTSError>",
            "INVALID_URN",
        ),
        (
            '<GetPassage><reply><error code="InvalidURN"/></reply></GetPassage>',
            "INVALID_URN",
        ),
        (
            "<CTSError><message>private error details</message></CTSError>",
            "UPSTREAM_CTS_ERROR",
        ),
        ("<unexpected/>", "INVALID_PAYLOAD"),
        ('<GetPassage xmlns="https://example.invalid/"/>', "INVALID_PAYLOAD"),
        (
            '<!DOCTYPE x [<!ENTITY e "expanded">]><GetPassage>&e;</GetPassage>',
            "INVALID_PAYLOAD",
        ),
    ],
)
def test_cts_errors_are_safe_and_typed(body, code):
    with pytest.raises(UpstreamFailure) as caught:
        validate_cts(body, "GetPassage")
    assert caught.value.code == code
    assert "private" not in caught.value.as_json()


def test_supported_cts_and_tei_representations():
    validate_cts(CAPABILITIES, "GetCapabilities")
    validate_cts("<TextInventory/>", "GetCapabilities")
    validate_cts(
        '<GetPassage xmlns="http://chs.harvard.edu/xmlns/cts"><reply/></GetPassage>',
        "GetPassage",
    )
    validate_cts(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text>Anubis</text></TEI>',
        "GetPassage",
    )


@pytest.mark.parametrize("source", ["memory", "disk"])
@pytest.mark.parametrize("replacement", [CAPABILITIES, CHALLENGE])
def test_invalid_cached_payload_is_evicted_and_never_recached(
    monkeypatch, tmp_path, source, replacement
):
    monkeypatch.setenv("PERSEUS_MCP_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("PERSEUS_MCP_DISABLE_CACHE", raising=False)
    monkeypatch.setattr(server, "_MEMORY_CACHE", {})
    key = server._cache_key({"request": "GetCapabilities"})
    path = server._cache_path("capabilities", key, "xml")
    path.parent.mkdir(parents=True)
    path.write_text(CHALLENGE, encoding="utf-8")
    if source == "memory":
        server._MEMORY_CACHE[f"capabilities:{key}"] = (time.time(), CHALLENGE)
    calls = []

    async def fetch():
        calls.append(True)
        return replacement

    async def run():
        return await server._cached_text(
            "capabilities",
            {"request": "GetCapabilities"},
            fetch,
            validator=partial(validate_cts, request="GetCapabilities"),
        )

    if replacement == CHALLENGE:
        with (
            pytest.warns(
                server.MetadataCacheWarning, match="Ignoring invalid capabilities"
            ),
            pytest.raises(UpstreamFailure, match="UPSTREAM_CHALLENGE"),
        ):
            asyncio.run(run())
        assert not path.exists()
        assert not server._MEMORY_CACHE
    else:
        with pytest.warns(
            server.MetadataCacheWarning, match="Ignoring invalid capabilities"
        ):
            value = asyncio.run(run())
        assert value == CAPABILITIES
        assert path.read_text(encoding="utf-8") == CAPABILITIES
    assert len(calls) == 1


def test_invalid_author_filter_shape_is_not_reported_as_zero_results():
    with pytest.raises(UpstreamFailure, match="INVALID_PAYLOAD"):
        server._filter_scaife_search_response_by_author(
            '{"error": "unavailable"}', "Homer", []
        )


@pytest.mark.parametrize(
    "name,args",
    [
        ("search_perseus", {"query": "λόγος"}),
        ("search_within_text", {"query": "λόγος", "text_urn": URN}),
        ("get_passage_highlights", {"query": "λόγος", "passage_urn": URN}),
        ("get_scaife_library_metadata", {"urn": URN}),
        ("get_scaife_passage_json", {"urn": URN}),
        ("get_scaife_passage_text", {"urn": URN}),
        ("get_passage", {"urn": URN}),
        ("get_passage_plus", {"urn": URN}),
        ("get_passage_plaintext", {"urn": URN}),
        ("get_label", {"urn": URN}),
        ("get_first_urn", {"urn": URN}),
        ("get_prev_next_urn", {"urn": URN}),
        ("get_capabilities", {}),
        ("get_valid_references", {"urn": URN}),
    ],
)
def test_mcp_wire_result_reports_challenge_as_error(monkeypatch, name, args):
    monkeypatch.setenv("PERSEUS_MCP_DISABLE_CACHE", "1")
    http_client, requests = mock_upstream(monkeypatch, CHALLENGE)

    async def run():
        async with http_client, Client(server.mcp) as client:
            result = await client.call_tool_mcp(name, args)
            assert result.model_dump(by_alias=True)["isError"] is True
            text = " ".join(
                block.text for block in result.content if block.type == "text"
            )
            assert "UPSTREAM_CHALLENGE" in text
            assert "DO_NOT_EXPOSE" not in text and "PRIVATE_CLIENT" not in text

    asyncio.run(run())
    assert len(requests) == 1


def test_mcp_wire_result_preserves_a_valid_empty_search(monkeypatch):
    http_client, _ = mock_upstream(
        monkeypatch,
        '{"results": [], "total_count": 0}',
        content_type="application/json",
    )

    async def run():
        async with http_client, Client(server.mcp) as client:
            result = await client.call_tool_mcp("search_perseus", {"query": "λόγος"})
            assert not result.model_dump(by_alias=True).get("isError", False)
            assert json.loads(result.content[0].text) == {
                "results": [],
                "total_count": 0,
            }

    asyncio.run(run())


@pytest.mark.parametrize("tool", ["get_first_urn", "get_prev_next_urn"])
@pytest.mark.parametrize("body", [
    MALFORMED_NAVIGATION,
    "<CTSError><message>Unsupported request</message></CTSError>",
], ids=["live-malformed-html", "cts-error"])
def test_cts_navigation_keeps_valid_reference_fallback(monkeypatch, tool, body):
    monkeypatch.setenv("PERSEUS_MCP_DISABLE_CACHE", "1")
    calls = []
    work_urn = URN.rsplit(":", 1)[0]
    references = [f"{work_urn}:1.{line}" for line in (1, 2, 3)]
    requested_urn = work_urn if tool == "get_first_urn" else references[1]
    operation_name = "GetFirstUrn" if tool == "get_first_urn" else "GetPrevNextUrn"

    def respond(request):
        operation = request.url.params["request"]
        calls.append((operation, request.url.params["urn"]))
        if operation == "GetValidReff":
            return httpx.Response(
                200,
                text='<GetValidReff xmlns="http://chs.harvard.edu/xmlns/cts3/ti">'
                "<reply><reff>" + "".join(f"<urn>{urn}</urn>" for urn in references)
                + "</reff></reply></GetValidReff>",
            )
        return httpx.Response(200, text=body)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond)
        ) as http_client:

            async def shared():
                return http_client

            monkeypatch.setattr(server, "_shared_client", shared)
            result = await getattr(server, tool)(requested_urn)
            root = ET.fromstring(result)
            assert root.tag == operation_name
            assert root.findtext("request/requestUrn") == requested_urn
            assert root.find("reply/error") is None
            if tool == "get_first_urn":
                assert root.findtext("reply/urn") == references[0]
            else:
                assert root.findtext("reply/previous/urn") == references[0]
                assert root.findtext("reply/next/urn") == references[2]

    asyncio.run(run())
    assert calls == [(operation_name, requested_urn), ("GetValidReff", work_urn)]


def test_live_navigation_fixture_reproduces_notebook_parse_error():
    with pytest.raises(ET.ParseError, match="unbound prefix: line 2, column 2"):
        ET.fromstring(MALFORMED_NAVIGATION)
    with pytest.raises(UpstreamFailure, match="INVALID_PAYLOAD"):
        validate_cts(MALFORMED_NAVIGATION, "GetFirstUrn")
