"""Validate upstream representations without exposing response bodies in errors."""

import json
import math
import os
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import lru_cache
from html.parser import HTMLParser
from typing import Any

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

MAX_RETRY_AFTER_SECONDS = 3600

DEFAULT_RETRY_POLICY = {
    "UPSTREAM_CHALLENGE": False,
    "INVALID_PAYLOAD": False,
    "INVALID_URN": False,
    "UPSTREAM_CTS_ERROR": False,
    "UPSTREAM_HTTP_ERROR": False,
    "UPSTREAM_TIMEOUT": True,
    "UPSTREAM_CONNECTION_ERROR": True,
    "UPSTREAM_TRANSPORT_ERROR": False,
    "UPSTREAM_RESPONSE_TOO_LARGE": False,
}


@lru_cache(maxsize=8)
def _retry_policy(configuration: str) -> dict[str, bool]:
    """Parse and cache retry overrides, rejecting unknown codes and non-boolean values."""
    policy = {}
    if configuration:
        try:
            overrides = json.loads(configuration)
        except ValueError:
            raise ValueError("PERSEUS_MCP_RETRY_POLICY must be a JSON object") from None
        if not isinstance(overrides, dict) or any(
            key not in DEFAULT_RETRY_POLICY or type(value) is not bool
            for key, value in overrides.items()
        ):
            raise ValueError(
                "PERSEUS_MCP_RETRY_POLICY must map known error codes to booleans"
            )
        policy.update(overrides)
    return policy


def validate_retry_policy() -> None:
    """Reject invalid retry-policy configuration before starting the server."""
    _retry_policy(os.environ.get("PERSEUS_MCP_RETRY_POLICY", ""))


def retry_allowed(code: str, status: int | None = None) -> bool:
    """Return the configured retry hint, otherwise using error-code and HTTP-status defaults."""
    overrides = _retry_policy(os.environ.get("PERSEUS_MCP_RETRY_POLICY", ""))
    if code in overrides:
        return overrides[code]
    if code == "UPSTREAM_HTTP_ERROR" and status is not None:
        return status in {429, 500, 502, 503, 504}
    return DEFAULT_RETRY_POLICY.get(code, False)


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> int | None:
    """Convert Retry-After to a delay capped at one hour."""
    if value is None:
        return None
    value = value.strip()
    try:
        if re.fullmatch(r"[0-9]+", value):
            seconds = value.lstrip("0") or "0"
            # Bound conversion too, even for arbitrarily long digit strings.
            if len(seconds) > len(str(MAX_RETRY_AFTER_SECONDS)):
                return MAX_RETRY_AFTER_SECONDS
            return min(int(seconds), MAX_RETRY_AFTER_SECONDS)
        deadline = parsedate_to_datetime(value)
        # Obsolete asctime HTTP dates have no timezone; HTTP dates use UTC.
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        remaining = (deadline - (now or datetime.now(UTC))).total_seconds()
        return min(MAX_RETRY_AFTER_SECONDS, max(0, math.ceil(remaining)))
    except (ValueError, TypeError, OverflowError):
        return None


class UpstreamFailure(Exception):
    """An expected upstream failure with a safe, stable public description."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int | None = None,
        *,
        retry_after_seconds: int | None = None,
    ):
        """Initialize the error details used in the public JSON payload."""
        self.code = code
        self.message = message
        self.status = status
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"{code}: {message}")

    def as_json(self) -> str:
        """Serialize the safe error code, message, HTTP status, delay, and retry hint."""
        return json.dumps(
            {
                "code": self.code,
                "message": self.message,
                "upstream_http_status": self.status,
                "retry_after_seconds": self.retry_after_seconds,
                "automatic_retry_allowed": retry_allowed(self.code, self.status),
            }
        )


class _PageMarkers(HTMLParser):
    """Recognize HTML documents and Anubis challenge markers without rendering them."""

    def __init__(self):
        """Initialize empty page and challenge markers."""
        super().__init__()
        self.challenge = False
        self.html = False

    def handle_starttag(self, tag, attrs):
        """Record HTML and challenge indicators from an opening tag and its attributes."""
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
    """Raise UPSTREAM_CHALLENGE when an HTML/XML prefix contains Anubis markers."""
    prefix = text.lstrip("\ufeff \t\r\n")[:65536]
    if not prefix.startswith("<"):
        return
    page = _PageMarkers()
    page.feed(prefix)
    if page.challenge:
        raise UpstreamFailure(
            "UPSTREAM_CHALLENGE",
            "The upstream service returned an access challenge; no results were "
            "obtained. The request was not retried automatically.",
            status,
        )


def _invalid() -> None:
    """Raise a safe INVALID_PAYLOAD failure without including upstream response content."""
    raise UpstreamFailure(
        "INVALID_PAYLOAD", "The upstream response has an unexpected format."
    )


def validate_text(text: str) -> None:
    """Reject access challenges and HTML pages where plaintext is expected."""
    reject_challenge(text)
    prefix = text.lstrip("\ufeff \t\r\n")[:65536]
    page = _PageMarkers()
    if prefix.startswith("<"):
        page.feed(prefix)
    if page.html or re.match(r"(?is)<!doctype\s+html\b", prefix):
        _invalid()


def _json(text: str) -> Any:
    """Decode JSON after challenge detection, mapping parse failures to INVALID_PAYLOAD."""
    reject_challenge(text)
    try:
        return json.loads(text)
    except (ValueError, RecursionError):
        _invalid()


def _objects(value: Any) -> bool:
    """Return whether a value is a list containing only JSON objects."""
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def validate_search(text: str) -> None:
    """Validate Scaife search result shapes and nonnegative pagination counters."""
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
    """Validate Scaife textgroup catalogue JSON and reject embedded errors."""
    data = _json(text)
    if not isinstance(data, dict) or not _objects(data.get("text_groups")):
        _invalid()
    if data.get("error") or data.get("errors"):
        _invalid()


def validate_metadata(text: str) -> None:
    """Require a CTS URN in Scaife metadata JSON and reject embedded errors."""
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
    """Validate Scaife passage metadata and require a string text_html field."""
    validate_metadata(text)
    data = _json(text)
    if not isinstance(data.get("text_html"), str):
        _invalid()


def validate_cts(text: str, request: str) -> None:
    """Validate a CTS operation by local root name, independent of its namespace.

    Args:
        text: Upstream XML response, or an upstream error body.
        request: Expected CTS operation such as GetPassage or GetCapabilities.

    Raises:
        UpstreamFailure: For challenges, invalid URNs, CTS errors, malformed XML,
            or an unexpected root. Error messages never include response bodies.

    Accepts TEI passage roots, TextInventory capabilities, and GetPassage
    envelopes returned for GetPassagePlus.
    """
    reject_challenge(text)
    if re.match(r"(?i)^\s*invalid\s+urn\b", text):
        raise UpstreamFailure(
            "INVALID_URN", "The upstream service rejected the requested URN."
        )
    try:
        root = fromstring(text)
    except (ET.ParseError, DefusedXmlException, RecursionError):
        _invalid()
    # Match the server's namespace-independent parsing. Namespace drift alone
    # must not reject otherwise valid responses or evict valid disk caches.
    local = root.tag.rsplit("}", 1)[-1]
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
