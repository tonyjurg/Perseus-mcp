"""Request CTS documents, cache inventories and references, and parse passage/navigation XML."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from functools import partial
from typing import Any

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring as _safe_xml_fromstring

from . import _common
from . import cache as _cache
from . import http as _http
from . import upstream as _upstream

__all__ = [
    "CTS_BASE",
    "_cts_request",
    "_first_urn_xml",
    "_get_capabilities_cached",
    "_get_valid_references_cached",
    "_is_xml_response",
    "_passage_plaintext_from_xml",
    "_prev_next_xml",
    "_reference_urns_from_xml",
    "_valid_references_json",
]


CTS_BASE = "https://www.perseus.tufts.edu/hopper/CTS"


async def _cts_request(
    request: str, urn: str | None = None, **extra_params: Any
) -> str:
    """Fetch a CTS operation with optional URN and parameters, validating its envelope."""
    params: dict[str, Any] = {"request": request, **extra_params}
    if urn:
        params["urn"] = urn
    return await _http._get(
        CTS_BASE,
        params=params,
        validator=partial(_upstream.validate_cts, request=request),
    )


async def _get_capabilities_cached(refresh: bool = False) -> str:
    """Return validated CTS inventory XML, optionally bypassing existing caches."""
    return await _cache._cached_text(
        "capabilities",
        {"request": "GetCapabilities", "base": CTS_BASE},
        lambda: _cts_request("GetCapabilities"),
        refresh=refresh,
        disk_validator=partial(_upstream.validate_cts, request="GetCapabilities"),
    )


async def _get_valid_references_cached(
    urn: str, level: int | None = None, refresh: bool = False
) -> str:
    """Return validated reference XML for a URN and optional citation level."""
    params: dict[str, Any] = {}
    if level is not None:
        params["level"] = str(level)
    return await _cache._cached_text(
        "valid_reff",
        {"request": "GetValidReff", "base": CTS_BASE, "urn": urn, **params},
        lambda: _cts_request("GetValidReff", urn=urn, **params),
        refresh=refresh,
        disk_validator=partial(_upstream.validate_cts, request="GetValidReff"),
    )


def _passage_plaintext_from_xml(passage_xml: str) -> str:
    """Extract readable text blocks from CTS/TEI XML without duplicating nested blocks."""
    root = _safe_xml_fromstring(passage_xml)

    def outermost_texts(names: set[str]) -> list[str]:
        """Collect text from matching outermost blocks in document order."""
        text_parts: list[str] = []

        def visit(element: ET.Element) -> None:
            """Walk descendants, stopping at a matching block to avoid duplicate text."""
            if _common._local_name(element.tag) in names:
                text = _common._element_text(element)
                if text:
                    text_parts.append(text)
                return
            for child in element:
                visit(child)

        visit(root)
        return text_parts

    text_parts = outermost_texts({"l", "p", "ab"})
    if not text_parts:
        text_parts = outermost_texts({"quote"})
    if not text_parts:
        text_parts = outermost_texts({"seg"})

    if not text_parts:
        for element in root.iter():
            if _common._local_name(element.tag) in {"text", "body", "div"}:
                text = _common._element_text(element)
                if text:
                    text_parts.append(text)
                    break

    if not text_parts:
        text_parts.append(_common._element_text(root))
    return "\n".join(part for part in text_parts if part)


def _is_xml_response(response_text: str, expected_root: str) -> bool:
    """Return whether safe XML parsing finds the expected local root name."""
    try:
        root = _safe_xml_fromstring(response_text)
    except (ET.ParseError, DefusedXmlException):
        return False
    return _common._local_name(root.tag).casefold() == expected_root.casefold()


def _reference_urns_from_xml(references_xml: str) -> list[str]:
    """Extract nonempty reference URNs in document order, ignoring namespaces."""
    root = _safe_xml_fromstring(references_xml)
    return [
        _common._element_text(element)
        for element in root.iter()
        if _common._local_name(element.tag).casefold() == "urn"
        and _common._element_text(element)
    ]


def _valid_references_json(
    references_xml: str,
    urn: str,
    level: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> str:
    """Serialize a validated page of reference URNs with counts and pagination metadata."""
    limit = _common._bounded_list_limit(limit)
    offset = _common._non_negative_int(offset, "offset")
    references = _reference_urns_from_xml(references_xml)
    page = references[offset : offset + limit]
    return json.dumps(
        {
            "urn": urn,
            "level": level,
            "total_count": len(references),
            "offset": offset,
            "limit": limit,
            "returned_count": len(page),
            "has_more": offset + len(page) < len(references),
            "references": page,
        },
        ensure_ascii=False,
        indent=2,
    )


def _prev_next_xml(urn: str, reference_urns: list[str]) -> str:
    """Build navigation XML from ordered references, reporting an absent URN as an error."""
    root = ET.Element("GetPrevNextUrn")
    request = ET.SubElement(root, "request")
    ET.SubElement(request, "requestName").text = "GetPrevNextUrn"
    ET.SubElement(request, "requestUrn").text = urn
    reply = ET.SubElement(root, "reply")

    try:
        index = reference_urns.index(urn)
    except ValueError:
        ET.SubElement(reply, "error").text = f"URN not found in valid references: {urn}"
        return ET.tostring(root, encoding="unicode")

    if index > 0:
        previous = ET.SubElement(reply, "previous")
        ET.SubElement(previous, "urn").text = reference_urns[index - 1]
    if index + 1 < len(reference_urns):
        following = ET.SubElement(reply, "next")
        ET.SubElement(following, "urn").text = reference_urns[index + 1]
    return ET.tostring(root, encoding="unicode")


def _first_urn_xml(urn: str, reference_urns: list[str]) -> str:
    """Build first-reference XML, reporting an empty reference list as an error."""
    root = ET.Element("GetFirstUrn")
    request = ET.SubElement(root, "request")
    ET.SubElement(request, "requestName").text = "GetFirstUrn"
    ET.SubElement(request, "requestUrn").text = urn
    reply = ET.SubElement(root, "reply")
    if reference_urns:
        ET.SubElement(reply, "urn").text = reference_urns[0]
    else:
        ET.SubElement(reply, "error").text = f"No valid references found for: {urn}"
    return ET.tostring(root, encoding="unicode")
