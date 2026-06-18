import json

import pytest

from perseus_mcp.server import _author_resources_from_capabilities


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
        <translation urn="urn:cts:greekLit:tlg0012.tlg001.perseus-eng2">
          <label xml:lang="eng">Iliad, English translation</label>
        </translation>
      </work>
      <work urn="urn:cts:greekLit:tlg0012.tlg002" xml:lang="grc">
        <title xml:lang="eng">Odyssey</title>
      </work>
    </TextGroup>
    <TextGroup urn="urn:cts:greekLit:tlg0007">
      <groupname xml:lang="eng">Plutarch</groupname>
    </TextGroup>
  </TextInventory>
</GetCapabilities>
"""


def test_author_resources_matches_author_name_and_lists_resources() -> None:
    result = json.loads(_author_resources_from_capabilities(CAPABILITIES_XML, "homer"))

    assert result["match_count"] == 1
    author = result["authors"][0]
    assert author["urn"] == "urn:cts:greekLit:tlg0012"
    assert author["names"] == ["Homer"]
    assert author["works"][0]["titles"] == ["Iliad"]
    assert author["works"][0]["language"] == "grc"
    assert author["works"][0]["editions"] == [
        {
            "type": "edition",
            "urn": "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2",
            "label": "Iliad, Murray edition",
            "description": "Greek edition text",
        }
    ]
    assert author["works"][0]["translations"][0]["urn"].endswith("perseus-eng2")


def test_author_resources_matches_lowercase_live_cts_textgroup() -> None:
    live_style_xml = CAPABILITIES_XML.replace("TextGroup", "textgroup")

    result = json.loads(_author_resources_from_capabilities(live_style_xml, "Homer"))

    assert result["match_count"] == 1
    assert result["authors"][0]["names"] == ["Homer"]


def test_author_resources_sorts_exact_name_before_partial_match() -> None:
    capabilities_xml = CAPABILITIES_XML.replace(
        '<TextGroup urn="urn:cts:greekLit:tlg0012">',
        '<TextGroup urn="urn:cts:greekLit:tlg0013">'
        '<groupname xml:lang="eng">Homeric Hymns</groupname>'
        "</TextGroup>"
        '<TextGroup urn="urn:cts:greekLit:tlg0012">',
    )

    result = json.loads(_author_resources_from_capabilities(capabilities_xml, "Homer"))

    assert result["match_count"] == 2
    assert result["authors"][0]["names"] == ["Homer"]


def test_author_resources_matches_textgroup_urn_fragment() -> None:
    result = json.loads(_author_resources_from_capabilities(CAPABILITIES_XML, "tlg0007"))

    assert result["match_count"] == 1
    assert result["authors"][0]["names"] == ["Plutarch"]


def test_author_resources_rejects_empty_author_query() -> None:
    with pytest.raises(ValueError, match="author must not be empty"):
        _author_resources_from_capabilities(CAPABILITIES_XML, "  ")
