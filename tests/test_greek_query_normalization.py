import asyncio

import server
from server import _normalize_greek_query, _normalize_language


def test_explicit_betacode_search_query_becomes_unicode_greek() -> None:
    assert _normalize_greek_query("mh=nin a)/eide qea/") == "μῆνιν ἄειδε θεά"


def test_unicode_greek_search_query_is_preserved_and_normalized() -> None:
    assert _normalize_greek_query("μῆνιν") == "μῆνιν"


def test_short_unaccented_betacode_gets_final_sigma() -> None:
    assert _normalize_greek_query("logos") == "λογος"


def test_query_format_can_force_unicode_for_ambiguous_ascii() -> None:
    assert _normalize_greek_query("logos", query_format="unicode") == "logos"


def test_common_language_names_normalize_to_scaife_code() -> None:
    assert _normalize_language("Ancient Greek") == "gr"
    assert _normalize_language("latin") == "la"


def test_search_perseus_uses_scaife_json_search_route(monkeypatch) -> None:
    request: dict[str, object] = {}

    async def fake_get(url, params=None, timeout=20.0):
        request.update(url=url, params=params, timeout=timeout)
        return '{"results": []}'

    monkeypatch.setattr(server, "_get", fake_get)

    result = asyncio.run(
        server.search_perseus("mh=nin", language="greek", query_format="betacode")
    )

    assert result == '{"results": []}'
    assert request["url"] == "https://scaife.perseus.org/search/json/"
    assert request["params"] == {
        "q": _normalize_greek_query("mh=nin"),
        "kind": "form",
        "type": "library",
        "page_num": 1,
    }
