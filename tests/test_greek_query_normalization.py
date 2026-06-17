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
        "format": "instances",
        "type": "library",
        "page_num": 1,
    }


def test_search_perseus_accepts_page_and_scaife_scope_parameters(monkeypatch) -> None:
    request: dict[str, object] = {}

    async def fake_get(url, params=None, timeout=20.0):
        request.update(url=url, params=params, timeout=timeout)
        return '{"results": []}'

    monkeypatch.setattr(server, "_get", fake_get)

    result = asyncio.run(
        server.search_perseus(
            "logos",
            language="greek",
            query_format="unicode",
            page_num=3,
            text_group="urn:cts:greekLit:tlg0012",
            work="urn:cts:greekLit:tlg0012.tlg001",
            result_format="passages",
        )
    )

    assert result == '{"results": []}'
    assert request["params"] == {
        "q": "logos",
        "kind": "form",
        "format": "passages",
        "type": "library",
        "page_num": 3,
        "text_group": "urn:cts:greekLit:tlg0012",
        "work": "urn:cts:greekLit:tlg0012.tlg001",
    }


def test_search_within_text_uses_reader_search(monkeypatch) -> None:
    request: dict[str, object] = {}

    async def fake_get(url, params=None, timeout=20.0):
        request.update(url=url, params=params, timeout=timeout)
        return '{"results": []}'

    monkeypatch.setattr(server, "_get", fake_get)

    result = asyncio.run(
        server.search_within_text(
            "logos",
            text_urn="urn:cts:greekLit:tlg0012.tlg001.perseus-grc2",
            language="greek",
            query_format="unicode",
            search_kind="lemma",
            size=5,
            offset=10,
        )
    )

    assert result == '{"results": []}'
    assert request["params"] == {
        "q": "logos",
        "kind": "lemma",
        "type": "reader",
        "text": "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2",
        "size": 5,
        "offset": 10,
        "fields": "",
    }


def test_get_passage_highlights_uses_reader_highlight_search(monkeypatch) -> None:
    request: dict[str, object] = {}

    async def fake_get(url, params=None, timeout=20.0):
        request.update(url=url, params=params, timeout=timeout)
        return '{"results": []}'

    monkeypatch.setattr(server, "_get", fake_get)

    result = asyncio.run(
        server.get_passage_highlights(
            "Î¼á¿†Î½Î¹Î½",
            passage_urn="urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1",
            query_format="unicode",
        )
    )

    assert result == '{"results": []}'
    assert request["params"] == {
        "q": "Î¼á¿†Î½Î¹Î½",
        "kind": "form",
        "type": "reader",
        "passage": "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1",
        "size": 1,
        "fields": "highlights",
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
        "format": "instances",
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
        "format": "instances",
        "type": "library",
        "page_num": 1,
    }
