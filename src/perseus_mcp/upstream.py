"""Validate upstream representations without exposing response bodies in errors."""

import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring


class UpstreamFailure(Exception):
    """An expected upstream failure with a safe, stable public description."""

    def __init__(self, code: str, message: str, status: int | None = None):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(f"{code}: {message}")

    def as_json(self) -> str:
        return json.dumps(
            {
                "code": self.code,
                "message": self.message,
                "upstream_http_status": self.status,
                "automatic_retry_allowed": False,
            }
        )


class _PageMarkers(HTMLParser):
    def __init__(self):
        super().__init__()
        self.challenge = False
        self.html = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in {"html", "head", "body"}:
            self.html = True
        if tag == "script" and values.get("id") == "anubis_challenge":
            self.challenge = True
        if tag in {"script", "link"} and any(
            "/.within.website/x/cmd/anubis/" in (values.get(key) or "")
            for key in ("src", "href")
        ):
            self.challenge = True


def reject_challenge(text: str, status: int | None = None) -> None:
    # JSON may legitimately contain HTML excerpts: do not parse those as pages.
    prefix = text.lstrip("\ufeff \t\r\n")[:65536]
    if not prefix.startswith("<"):
        return
    page = _PageMarkers()
    page.feed(prefix)
    if page.challenge:
        raise UpstreamFailure(
            "UPSTREAM_CHALLENGE",
            "The upstream service returned an access challenge; no results were "
            "obtained. Automatic retry is disabled.",
            status,
        )


def _invalid() -> None:
    raise UpstreamFailure(
        "INVALID_PAYLOAD", "The upstream response has an unexpected format."
    )


def validate_text(text: str) -> None:
    reject_challenge(text)
    prefix = text.lstrip("\ufeff \t\r\n")[:65536]
    page = _PageMarkers()
    if prefix.startswith("<"):
        page.feed(prefix)
    if page.html or re.match(r"(?is)<!doctype\s+html\b", prefix):
        _invalid()


def _json(text: str) -> Any:
    reject_challenge(text)
    try:
        return json.loads(text)
    except (ValueError, RecursionError):
        _invalid()


def _objects(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def validate_search(text: str) -> None:
    data = _json(text)
    # Both shapes are supported by the existing author-scope filter.
    if _objects(data):
        return
    if not isinstance(data, dict) or not _objects(data.get("results")):
        _invalid()
    if data.get("error") or data.get("errors"):
        _invalid()
    for field in ("total_count", "page_num", "num_pages"):
        value = data.get(field)
        if value is not None and (type(value) is not int or value < 0):
            _invalid()


def validate_catalogue(text: str) -> None:
    data = _json(text)
    if not isinstance(data, dict) or not _objects(data.get("text_groups")):
        _invalid()
    if data.get("error") or data.get("errors"):
        _invalid()


def validate_metadata(text: str) -> None:
    data = _json(text)
    if not isinstance(data, dict) or not isinstance(data.get("urn"), str):
        _invalid()
    if (
        not data["urn"].startswith("urn:cts:")
        or data.get("error")
        or data.get("errors")
    ):
        _invalid()


def validate_passage_json(text: str) -> None:
    validate_metadata(text)
    data = _json(text)
    if not isinstance(data.get("text_html"), str):
        _invalid()


def validate_cts(text: str, request: str) -> None:
    reject_challenge(text)
    if re.match(r"(?i)^\s*invalid\s+urn\b", text):
        raise UpstreamFailure(
            "INVALID_URN", "The upstream service rejected the requested URN."
        )
    try:
        root = fromstring(text)
    except (ET.ParseError, DefusedXmlException, RecursionError):
        _invalid()
    namespace, _, local = root.tag.rpartition("}")
    if namespace not in {
        "",
        "{http://chs.harvard.edu/xmlns/cts",
        "{http://chs.harvard.edu/xmlns/cts3",
        "{http://chs.harvard.edu/xmlns/cts3/ti",
        "{http://www.tei-c.org/ns/1.0",
    }:
        _invalid()
    # Only protocol errors count; TEI content may itself contain the word "error".
    errors = [
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1].casefold() in {"error", "ctserror"}
        and not element.tag.startswith("{http://www.tei-c.org/ns/1.0}")
    ]
    if errors:
        details = " ".join(" ".join(e.itertext()) + " " + str(e.attrib) for e in errors)
        invalid_urn = re.search(r"invalid[\s_-]*urn", details, re.IGNORECASE)
        raise UpstreamFailure(
            "INVALID_URN" if invalid_urn else "UPSTREAM_CTS_ERROR",
            "The upstream service rejected the requested URN."
            if invalid_urn
            else "The upstream service returned a CTS error.",
        )
    allowed = {request}
    if request == "GetCapabilities":
        allowed.add("TextInventory")
    if request in {"GetPassage", "GetPassagePlus"}:
        allowed.add("TEI")
    if request == "GetPassagePlus":
        # Perseus also answers GetPassagePlus with a GetPassage envelope.
        allowed.add("GetPassage")
    if local not in allowed:
        _invalid()
