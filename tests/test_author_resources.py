import json
from copy import deepcopy

import pytest

from perseus_mcp.server import (
    _author_resources_from_capabilities,
    _merge_author_entries,
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


def test_merge_author_entries_deduplicates_works_within_incoming_group() -> None:
    merged = _merge_author_entries(
        [{"urn": "urn:cts:greekLit:tlg0012", "names": ["Homer"], "works": []}],
        [
            {
                "urn": "urn:cts:greekLit:tlg0012",
                "names": ["Homer"],
                "works": [
                    {"urn": "urn:cts:greekLit:tlg0012.tlg001"},
                    {"urn": "urn:cts:greekLit:tlg0012.tlg001"},
                ],
            }
        ],
    )

    assert merged[0]["works_count"] == 1
    assert merged[0]["works"] == [{"urn": "urn:cts:greekLit:tlg0012.tlg001"}]


def test_merge_author_entries_does_not_mutate_inputs() -> None:
    author = {
        "urn": "urn:cts:greekLit:tlg0012",
        "names": ["Homer"],
        "works": [{"urn": "urn:cts:greekLit:tlg0012.tlg001"}],
    }
    original = deepcopy(author)

    merged = _merge_author_entries([author])
    merged[0]["names"].append("Homerus")
    merged[0]["works"][0]["titles"] = ["Iliad"]

    assert author == original


def test_merge_author_entries_combines_duplicate_work_metadata() -> None:
    work_urn = "urn:cts:greekLit:tlg0012.tlg001"
    edition_urn = f"{work_urn}.perseus-grc1"
    translation_urn = f"{work_urn}.perseus-eng1"
    merged = _merge_author_entries(
        [
            {
                "urn": "urn:cts:greekLit:tlg0012",
                "names": ["Homer"],
                "works": [
                    {
                        "urn": work_urn,
                        "language": "grc",
                        "titles": ["Iliad"],
                        "editions": [
                            {
                                "urn": edition_urn,
                                "type": "edition",
                                "label": "Greek edition",
                            }
                        ],
                        "translations": [],
                        "resources": [
                            {
                                "urn": edition_urn,
                                "type": "edition",
                                "label": "Greek edition",
                            }
                        ],
                    }
                ],
            }
        ],
        [
            {
                "urn": "urn:cts:greekLit:tlg0012",
                "names": ["Homerus"],
                "works": [
                    {
                        "urn": work_urn,
                        "titles": ["The Iliad"],
                        "editions": [
                            {
                                "urn": edition_urn,
                                "type": "edition",
                                "description": "Critical text",
                            }
                        ],
                        "translations": [
                            {
                                "urn": translation_urn,
                                "type": "translation",
                                "label": "English translation",
                            }
                        ],
                        "resources": [
                            {
                                "urn": edition_urn,
                                "type": "edition",
                                "description": "Critical text",
                            },
                            {
                                "urn": translation_urn,
                                "type": "translation",
                                "label": "English translation",
                            },
                        ],
                    }
                ],
            }
        ],
    )

    author = merged[0]
    work = author["works"][0]
    assert author["names"] == ["Homer", "Homerus"]
    assert work["language"] == "grc"
    assert work["titles"] == ["Iliad", "The Iliad"]
    assert work["editions"][0] == {
        "urn": edition_urn,
        "type": "edition",
        "label": "Greek edition",
        "description": "Critical text",
    }
    assert work["translations"][0]["urn"] == translation_urn
    assert [resource["urn"] for resource in work["resources"]] == [
        edition_urn,
        translation_urn,
    ]
