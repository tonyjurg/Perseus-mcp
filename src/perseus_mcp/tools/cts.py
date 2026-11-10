"""Expose CTS passage, reference, label, and navigation operations as MCP tools."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring as _safe_xml_fromstring

from .. import _app, _common
from .. import cts as _cts
from .. import upstream as _upstream

__all__ = [
    "count_valid_references",
    "get_capabilities",
    "get_first_urn",
    "get_label",
    "get_passage",
    "get_passage_plaintext",
    "get_passage_plus",
    "get_prev_next_urn",
    "get_valid_references",
    "get_valid_references_json",
]


@_app._upstream_tool
async def get_passage(urn: str) -> str:
    """Get the text of a specific passage using a CTS URN.

    Examples:
    - urn:cts:greekLit:tlg0012.tlg001:1.1-1.10
    - urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.1
    """
    return await _cts._cts_request("GetPassage", urn=urn)


@_app._upstream_tool
async def get_passage_plus(urn: str) -> str:
    """Get passage text plus surrounding metadata/context for a CTS URN."""
    return await _cts._cts_request("GetPassagePlus", urn=urn)


@_app._upstream_tool
async def get_passage_plaintext(urn: str) -> str:
    """Get a passage as plain readable text instead of raw CTS XML."""
    passage_xml = await _cts._cts_request("GetPassage", urn=urn)
    return _cts._passage_plaintext_from_xml(passage_xml)


@_app._upstream_tool
async def get_valid_references(urn: str, level: int | None = None) -> str:
    """Get valid citations/references for a work, useful for navigation.

    Optionally pass a citation `level` to constrain returned references.
    """
    return await _cts._get_valid_references_cached(urn, level)


@_app._upstream_tool
async def get_valid_references_json(
    urn: str, level: int | None = None, limit: int = 100, offset: int = 0
) -> str:
    """Get valid citation references as paged JSON instead of raw CTS XML.

    `limit` must be between 1 and 500.
    """
    references_xml = await _cts._get_valid_references_cached(urn, level)
    return _cts._valid_references_json(references_xml, urn, level, limit, offset)


@_app._upstream_tool
async def count_valid_references(urn: str, level: int | None = None) -> str:
    """Count valid citation references without returning the full reference list."""
    references_xml = await _cts._get_valid_references_cached(urn, level)
    references = _cts._reference_urns_from_xml(references_xml)
    return json.dumps(
        {"urn": urn, "level": level, "total_count": len(references)},
        ensure_ascii=False,
        indent=2,
    )


@_app._upstream_tool
async def get_capabilities() -> str:
    """Get the list of available texts and editions from Perseus CTS."""
    return await _cts._get_capabilities_cached()


@_app._upstream_tool
async def get_label(urn: str) -> str:
    """Get label XML, falling back to GetPassage request metadata when needed."""
    try:
        return await _cts._cts_request("GetLabel", urn=urn)
    except _upstream.UpstreamFailure as exc:
        if exc.code not in {"UPSTREAM_CTS_ERROR", "INVALID_PAYLOAD"}:
            raise

    passage_urn = urn
    if not urn.split(":", 4)[-1] or urn.count(":") < 4:
        # Resolve work/edition URNs to an advertised passage rather than fetching
        # an entire text or guessing its citation scheme.
        references = _cts._reference_urns_from_xml(
            await _cts._get_valid_references_cached(urn)
        )
        if not references:
            raise _upstream.UpstreamFailure(
                "INVALID_PAYLOAD",
                "No valid references are available for label metadata.",
            )
        passage_urn = references[0]

    passage = _safe_xml_fromstring(
        await _cts._cts_request("GetPassage", urn=passage_urn)
    )
    metadata = next(
        (child for child in passage if _common._local_name(child.tag) == "request"),
        None,
    )
    root = ET.Element("GetLabel")
    request = ET.SubElement(root, "request")
    ET.SubElement(request, "requestName").text = "GetLabel"
    ET.SubElement(request, "requestUrn").text = urn
    reply = ET.SubElement(root, "reply", source="GetPassage request metadata")
    fields = {"groupname", "title", "label", "description", "versionInfo"}
    if metadata is not None:
        for element in metadata:
            name = _common._local_name(element.tag)
            text = _common._element_text(element)
            if name in fields and text:
                ET.SubElement(reply, name, attrib=dict(element.attrib)).text = text
    if not len(reply):
        raise _upstream.UpstreamFailure(
            "INVALID_PAYLOAD", "The passage response contains no label metadata."
        )
    return ET.tostring(root, encoding="unicode")


@_app._upstream_tool
async def get_first_urn(urn: str) -> str:
    """Get the first available reference URN for a work/edition URN."""
    try:
        response = await _cts._cts_request("GetFirstUrn", urn=urn)
    except _upstream.UpstreamFailure as exc:
        if exc.code not in {"UPSTREAM_CTS_ERROR", "INVALID_PAYLOAD"}:
            raise
        response = ""
    if _cts._is_xml_response(response, "GetFirstUrn"):
        return response

    references_xml = await _cts._get_valid_references_cached(urn)
    return _cts._first_urn_xml(urn, _cts._reference_urns_from_xml(references_xml))


@_app._upstream_tool
async def get_prev_next_urn(urn: str) -> str:
    """Get previous and next URNs for a passage URN."""
    try:
        response = await _cts._cts_request("GetPrevNextUrn", urn=urn)
    except _upstream.UpstreamFailure as exc:
        if exc.code not in {"UPSTREAM_CTS_ERROR", "INVALID_PAYLOAD"}:
            raise
        response = ""
    if _cts._is_xml_response(response, "GetPrevNextUrn"):
        return response

    work_urn, separator, _ = urn.rpartition(":")
    if not separator:
        return response
    references_xml = await _cts._get_valid_references_cached(work_urn)
    return _cts._prev_next_xml(urn, _cts._reference_urns_from_xml(references_xml))
