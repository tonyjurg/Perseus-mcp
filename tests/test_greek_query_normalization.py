import asyncio

import pytest

import server
from server import _normalize_greek_query, _normalize_language, _normalize_search_kind


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


def test_search_kind_allows_form_and_lemma() -> None:
    assert _normalize_search_kind(None) == "form"
    assert _normalize_search_kind("form") == "form"
    assert _normalize_search_kind("LEMMA") == "lemma"


def test_search_kind_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="search_kind must be one of: form, lemma"):
        _normalize_search_kind("phrase")


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


def test_search_perseus_can_use_lemma_search_kind(monkeypatch) -> None:
    request: dict[str, object] = {}

    async def fake_get(url, params=None, timeout=20.0):
        request.update(url=url, params=params, timeout=timeout)
        return '{"results": []}'

    monkeypatch.setattr(server, "_get", fake_get)

    result = asyncio.run(
        server.search_perseus(
            "logos",
            language="greek",
            query_format="betacode",
            search_kind="lemma",
        )
    )

    assert result == '{"results": []}'
    assert request["params"] == {
        "q": _normalize_greek_query("logos", query_format="betacode"),
        "kind": "lemma",
        "type": "library",
        "page_num": 1,
    }


def test_search_perseus_can_preserve_operator_query(monkeypatch) -> None:
    request: dict[str, object] = {}

    async def fake_get(url, params=None, timeout=20.0):
        request.update(url=url, params=params, timeout=timeout)
        return '{"results": []}'

    monkeypatch.setattr(server, "_get", fake_get)

    result = asyncio.run(
        server.search_perseus(
            "μῆνιν | ἄειδε",
            language="greek",
            preserve_operators=True,
        )
    )

    assert result == '{"results": []}'
    assert request["params"] == {
        "q": "μῆνιν | ἄειδε",
        "kind": "form",
        "type": "library",
        "page_num": 1,
    }
