import json

import pytest

from server import (
    _author_resources_from_capabilities,
    _first_urn_xml,
    _list_text_groups_from_capabilities,
    _normalize_search_language,
    _passage_plaintext_from_xml,
    _prev_next_xml,
    _reference_urns_from_xml,
    _work_resources_from_capabilities,
)


CAPABILITIES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<GetCapabilities xmlns="http://chs.harvard.edu/xmlns/cts">
  <TextInventory>
    <TextGroup urn="urn:cts:greekLit:tlg0012">
      <groupname xml:lang="eng">Homer</groupname>
      <work urn="urn:cts:greekLit:tlg0012.tlg001" xml:lang="grc">
        <title xml:lang="eng">Iliad</title>
        <edition urn="urn:cts:greekLit:tlg0012.tlg001.perseus-grc2">
          <label xml:lang="eng">Iliad, Murray edition</label>
          <description xml:lang="eng">Greek edition text</description>
        </edition>
        <translation urn="urn:cts:greekLit:tlg0012.tlg001.perseus-eng2" xml:lang="eng">
          <label xml:lang="eng">Iliad, English translation</label>
        </translation>
      </work>
      <work urn="urn:cts:greekLit:tlg0012.tlg002" xml:lang="grc">
        <title xml:lang="eng">Odyssey</title>
      </work>
    </TextGroup>
    <TextGroup urn="urn:cts:latinLit:phi0959">
      <groupname xml:lang="eng">Ovid</groupname>
      <work urn="urn:cts:latinLit:phi0959.phi006" xml:lang="lat">
        <title xml:lang="eng">Metamorphoses</title>
        <edition urn="urn:cts:latinLit:phi0959.phi006.perseus-lat2">
          <label xml:lang="eng">Metamorphoses, Latin edition</label>
        </edition>
      </work>
    </TextGroup>
  </TextInventory>
</GetCapabilities>
"""


PASSAGE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<GetPassage xmlns="http://chs.harvard.edu/xmlns/cts">
  <reply>
    <TEI xmlns="http://www.tei-c.org/ns/1.0">
      <text>
        <body>
          <div>
            <l n="1">μῆνιν ἄειδε θεὰ</l>
            <l n="2">arma virumque cano</l>
          </div>
        </body>
      </text>
    </TEI>
  </reply>
</GetPassage>
"""


def test_list_text_groups_filters_by_latin_language_and_query() -> None:
    result = json.loads(
        _list_text_groups_from_capabilities(CAPABILITIES_XML, language="latin", query="ovid")
    )

    assert result["language"] == "lat"
    assert result["match_count"] == 1
    assert result["text_groups"][0]["names"] == ["Ovid"]
    assert result["text_groups"][0]["works"][0]["titles"] == ["Metamorphoses"]


def test_author_resources_lists_editions_and_translations() -> None:
    result = json.loads(_author_resources_from_capabilities(CAPABILITIES_XML, "homer"))

    assert result["match_count"] == 1
    work = result["authors"][0]["works"][0]
    assert work["urn"] == "urn:cts:greekLit:tlg0012.tlg001"
    assert work["editions"][0]["urn"] == "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2"
    assert work["translations"][0]["language"] == "eng"


def test_author_resources_rejects_empty_author_query() -> None:
    with pytest.raises(ValueError, match="author must not be empty"):
        _author_resources_from_capabilities(CAPABILITIES_XML, "  ")


def test_work_resources_matches_title_and_returns_author_context() -> None:
    result = json.loads(_work_resources_from_capabilities(CAPABILITIES_XML, "Iliad"))

    assert result["match_count"] == 1
    assert result["matches"][0]["author"]["names"] == ["Homer"]
    assert result["matches"][0]["work"]["titles"] == ["Iliad"]


def test_passage_plaintext_extracts_readable_lines() -> None:
    plaintext = _passage_plaintext_from_xml(PASSAGE_XML)

    assert plaintext == "μῆνιν ἄειδε θεὰ\narma virumque cano"


def test_prev_next_xml_uses_valid_reference_order() -> None:
    references_xml = """<GetValidReff>
      <reply>
        <urn>urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.9</urn>
        <urn>urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.10</urn>
        <urn>urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.11</urn>
      </reply>
    </GetValidReff>"""
    current = "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.10"

    result = _prev_next_xml(current, _reference_urns_from_xml(references_xml))

    assert "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.9" in result
    assert "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.11" in result


def test_first_urn_xml_uses_first_valid_reference() -> None:
    work = "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1"
    references = [
        f"{work}:1.1",
        f"{work}:1.2",
    ]

    result = _first_urn_xml(work, references)

    assert f"<urn>{work}:1.1</urn>" in result


def test_search_language_normalizes_greek_and_latin_names() -> None:
    assert _normalize_search_language("Ancient Greek") == "gr"
    assert _normalize_search_language("latin") == "la"
