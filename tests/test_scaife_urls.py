import asyncio

from perseus_mcp import server
from perseus_mcp.server import (
    _scaife_library_url,
    _scaife_passage_json_url,
    _scaife_passage_text_url,
)


def test_scaife_library_url_preserves_well_formed_urn() -> None:
    urn = "urn:cts:greekLit:tlg0012.tlg001"
    assert _scaife_library_url(urn) == (
        "https://scaife.perseus.org/library/urn:cts:greekLit:tlg0012.tlg001/json/"
    )


def test_scaife_passage_json_url_preserves_well_formed_urn() -> None:
    urn = "urn:cts:greekLit:tlg0012.tlg001:1.1"
    assert _scaife_passage_json_url(urn) == (
        "https://scaife.perseus.org/library/passage/"
        "urn:cts:greekLit:tlg0012.tlg001:1.1/json/"
    )


def test_scaife_passage_text_url_preserves_well_formed_urn() -> None:
    urn = "urn:cts:greekLit:tlg0012.tlg001:1.1"
    assert _scaife_passage_text_url(urn) == (
        "https://scaife.perseus.org/library/passage/"
        "urn:cts:greekLit:tlg0012.tlg001:1.1/text/"
    )


def test_scaife_library_url_encodes_fragment_character() -> None:
    # A literal '#' would otherwise be interpreted as a URL fragment marker
    # and silently truncate everything after it before the request is sent.
    urn = "urn:cts:greekLit:tlg0012.tlg001#bad"
    url = _scaife_library_url(urn)
    assert "#" not in url
    assert "%23" in url


def test_scaife_passage_json_url_encodes_query_character() -> None:
    # A literal '?' would otherwise inject an unintended query string.
    urn = "urn:cts:greekLit:tlg0012.tlg001:1.1?evil=1"
    url = _scaife_passage_json_url(urn)
    assert url.count("?") == 0
    assert "%3F" in url


def test_scaife_passage_text_url_encodes_whitespace() -> None:
    urn = "urn:cts:greekLit:tlg0012.tlg001 oops"
    url = _scaife_passage_text_url(urn)
    assert " " not in url
    assert "%20" in url


def test_get_scaife_passage_json_requests_encoded_url(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def fake_get(url: str, params=None, timeout: float = 20.0) -> str:
        captured["url"] = url
        return "{}"

    monkeypatch.setattr(server, "_get", fake_get)

    asyncio.run(server.get_scaife_passage_json("urn:cts:greekLit:tlg0012.tlg001:1.1#x"))

    assert "#" not in captured["url"]
    assert "%23" in captured["url"]
