import asyncio
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
import pytest
from fastmcp.exceptions import ToolError

from perseus_mcp import server

FIXTURES = Path(__file__).parent / "fixtures"
PASSAGE = (FIXTURES / "cts/GetPassage.xml").read_text(encoding="utf-8")
MALFORMED = (FIXTURES / "cts/navigation-malformed.html").read_text(encoding="utf-8")
CHALLENGE = (FIXTURES / "anubis.html").read_text(encoding="utf-8")
EDITION = "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1"
PASSAGE_URN = f"{EDITION}:1.1"
REFERENCES = f"<GetValidReff><reply><urn>{PASSAGE_URN}</urn></reply></GetValidReff>"


def call_label(monkeypatch, urn, responses, calls):
    monkeypatch.setenv("PERSEUS_MCP_DISABLE_CACHE", "1")

    def respond(request):
        operation = request.url.params["request"]
        calls.append((operation, request.url.params["urn"]))
        return httpx.Response(200, text=responses[operation])

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:

            async def shared():
                return client

            monkeypatch.setattr(server, "_shared_client", shared)
            return await server.get_label(urn)

    return asyncio.run(run())


@pytest.mark.parametrize("urn", [EDITION.rsplit(".", 1)[0], EDITION, PASSAGE_URN])
@pytest.mark.parametrize(
    "failure",
    [MALFORMED, "<CTSError><message>Unsupported request</message></CTSError>"],
)
def test_label_fallback_uses_live_passage_request_metadata(monkeypatch, urn, failure):
    calls = []
    result = call_label(
        monkeypatch,
        urn,
        {"GetLabel": failure, "GetValidReff": REFERENCES, "GetPassage": PASSAGE},
        calls,
    )
    root = ET.fromstring(result)
    assert root.tag == "GetLabel"
    assert root.findtext("request/requestUrn") == urn
    reply = root.find("reply")
    assert reply.attrib == {"source": "GetPassage request metadata"}
    assert {child.tag: child.text for child in reply} == {
        "groupname": "Homer",
        "title": "Iliad",
        "label": "Iliad",
        "versionInfo": "Perseus 4.0",
    }
    expected = [("GetLabel", urn)]
    if urn != PASSAGE_URN:
        expected.append(("GetValidReff", urn))
    assert calls == expected + [("GetPassage", PASSAGE_URN)]


def test_valid_label_is_returned_unchanged(monkeypatch):
    body = '<GetLabel><reply><label xml:lang="eng">Iliad</label></reply></GetLabel>'
    calls = []
    assert call_label(monkeypatch, EDITION, {"GetLabel": body}, calls) == body
    assert calls == [("GetLabel", EDITION)]


@pytest.mark.parametrize(
    "body,code",
    [(CHALLENGE, "UPSTREAM_CHALLENGE"), ("Invalid URN: example", "INVALID_URN")],
)
@pytest.mark.parametrize("stage", ["GetLabel", "GetValidReff", "GetPassage"])
def test_label_fallback_stops_on_challenges_and_invalid_urns(
    monkeypatch, stage, body, code
):
    responses = {
        "GetLabel": MALFORMED,
        "GetValidReff": REFERENCES,
        "GetPassage": PASSAGE,
    }
    responses[stage] = body
    calls = []
    with pytest.raises(ToolError, match=code):
        call_label(monkeypatch, EDITION, responses, calls)
    stages = ["GetLabel", "GetValidReff", "GetPassage"]
    assert [op for op, _ in calls] == stages[: stages.index(stage) + 1]


@pytest.mark.parametrize(
    "body",
    [
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><title>Not request metadata</title></TEI>',
        "<GetPassage><request><label> </label></request><reply><title>Not metadata</title></reply></GetPassage>",
    ],
)
def test_label_fallback_does_not_invent_missing_metadata(monkeypatch, body):
    with pytest.raises(ToolError, match="no label metadata"):
        call_label(
            monkeypatch, PASSAGE_URN, {"GetLabel": MALFORMED, "GetPassage": body}, []
        )


def test_label_fallback_does_not_fetch_passage_without_references(monkeypatch):
    calls = []
    with pytest.raises(ToolError, match="No valid references"):
        call_label(
            monkeypatch,
            EDITION,
            {
                "GetLabel": MALFORMED,
                "GetValidReff": "<GetValidReff><reply/></GetValidReff>",
            },
            calls,
        )
    assert calls == [("GetLabel", EDITION), ("GetValidReff", EDITION)]


def test_label_metadata_preserves_language_and_escapes_text(monkeypatch):
    body = '<GetPassage><request><label xml:lang="eng">A &amp; B</label>'
    body += "<description>One &lt; two</description></request></GetPassage>"
    result = call_label(
        monkeypatch, PASSAGE_URN, {"GetLabel": MALFORMED, "GetPassage": body}, []
    )
    root = ET.fromstring(result)
    assert root.find("reply/label").attrib == {
        "{http://www.w3.org/XML/1998/namespace}lang": "eng"
    }
    assert root.findtext("reply/label") == "A & B"
    assert root.findtext("reply/description") == "One < two"
