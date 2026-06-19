import asyncio
import json
import os
import stat

import pytest

from perseus_mcp import server
from perseus_mcp.server import (
    _author_name_matches_from_capabilities,
    _author_resources_from_capabilities,
    _first_urn_xml,
    _filter_scaife_search_response_by_author,
    _list_text_groups_from_capabilities,
    _matching_author_entries_from_capabilities,
    _normalize_search_language,
    _passage_plaintext_from_xml,
    _prev_next_xml,
    _remove_readonly_cache_entry,
    _reference_urns_from_xml,
    _valid_references_json,
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


def test_author_name_matches_only_textgroup_names() -> None:
    result = json.loads(_author_name_matches_from_capabilities(CAPABILITIES_XML, "Hom"))

    assert result["match_count"] == 1
    assert result["authors"][0]["names"] == ["Homer"]
    assert result["authors"][0]["matched_names"] == ["Homer"]

    no_title_match = json.loads(
        _author_name_matches_from_capabilities(CAPABILITIES_XML, "Iliad")
    )
    assert no_title_match["match_count"] == 0


def test_author_name_matches_rejects_empty_query() -> None:
    with pytest.raises(ValueError, match="query must not be empty"):
        _author_name_matches_from_capabilities(CAPABILITIES_XML, "  ")


def test_work_resources_matches_title_and_returns_author_context() -> None:
    result = json.loads(_work_resources_from_capabilities(CAPABILITIES_XML, "Iliad"))

    assert result["match_count"] == 1
    assert result["matches"][0]["author"]["names"] == ["Homer"]
    assert result["matches"][0]["work"]["titles"] == ["Iliad"]


def test_work_resources_filters_by_language() -> None:
    latin_result = json.loads(
        _work_resources_from_capabilities(
            CAPABILITIES_XML, "Metamorphoses", language="latin"
        )
    )
    greek_result = json.loads(
        _work_resources_from_capabilities(
            CAPABILITIES_XML, "Metamorphoses", language="greek"
        )
    )

    assert latin_result["language"] == "lat"
    assert latin_result["match_count"] == 1
    assert greek_result["language"] == "grc"
    assert greek_result["match_count"] == 0


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


def test_valid_references_json_pages_reference_urns() -> None:
    work = "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1"
    references_xml = f"""<GetValidReff>
      <reply>
        <urn>{work}:1.1</urn>
        <urn>{work}:1.2</urn>
        <urn>{work}:1.3</urn>
      </reply>
    </GetValidReff>"""

    result = json.loads(
        _valid_references_json(references_xml, work, level=1, limit=2, offset=1)
    )

    assert result["total_count"] == 3
    assert result["returned_count"] == 2
    assert result["has_next"] is False
    assert result["references"] == [f"{work}:1.2", f"{work}:1.3"]


def test_search_language_normalizes_greek_and_latin_names() -> None:
    assert _normalize_search_language("Ancient Greek") == "gr"
    assert _normalize_search_language("latin") == "la"


def test_clear_cache_removes_readonly_directories(
    tmp_path,
    monkeypatch,
) -> None:
    cache_dir = tmp_path / "perseus-mcp"
    protected_dir = cache_dir / "capabilities"
    protected_dir.mkdir(parents=True)
    (protected_dir / "metadata.xml").write_text("<xml/>", encoding="utf-8")
    protected_dir.chmod(stat.S_IREAD)
    monkeypatch.setenv("PERSEUS_MCP_CACHE_DIR", str(cache_dir))

    result = json.loads(server._clear_cache())

    assert result["disk_cache_removed"] is True
    assert not cache_dir.exists()


def test_remove_readonly_cache_entry_reraises_other_errors(tmp_path) -> None:
    error = OSError("not a permissions error")

    with pytest.raises(OSError, match="not a permissions error"):
        _remove_readonly_cache_entry(
            lambda path: None,
            str(tmp_path),
            (OSError, error, None),
        )


def test_remove_readonly_cache_entry_removes_protected_directory(tmp_path) -> None:
    protected_dir = tmp_path / "protected"
    protected_dir.mkdir()
    protected_file = protected_dir / "metadata.xml"
    protected_file.write_text("<xml/>", encoding="utf-8")
    protected_dir.chmod(stat.S_IREAD)

    _remove_readonly_cache_entry(
        os.unlink,
        str(protected_file),
        (PermissionError, PermissionError("permission denied"), None),
    )

    assert not protected_file.exists()


def test_scaife_search_response_can_be_filtered_to_author_scope() -> None:
    authors = _matching_author_entries_from_capabilities(CAPABILITIES_XML, "Homer")
    response_text = json.dumps(
        {
            "results": [
                {"urn": "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.1"},
                {"urn": "urn:cts:latinLit:phi0959.phi006.perseus-lat2:1"},
            ]
        }
    )

    result = json.loads(
        _filter_scaife_search_response_by_author(response_text, "Homer", authors)
    )

    assert len(result["results"]) == 1
    assert result["results"][0]["urn"].startswith("urn:cts:greekLit:tlg0012")
    assert result["author_scope"]["unfiltered_page_result_count"] == 2


def test_search_perseus_uses_server_side_text_group_for_single_author(
    monkeypatch,
) -> None:
    request: dict[str, object] = {}

    async def fake_get(url, params=None, timeout=20.0):
        request.update(url=url, params=params, timeout=timeout)
        return '{"results": [], "total_count": 0}'

    async def fake_capabilities(refresh=False):
        return CAPABILITIES_XML

    monkeypatch.setattr(server, "_get", fake_get)
    monkeypatch.setattr(server, "_get_capabilities_cached", fake_capabilities)

    result = json.loads(
        asyncio.run(
            server.search_perseus(
                "mh=nin",
                language="greek",
                query_format="betacode",
                author="Homer",
            )
        )
    )

    assert request["params"]["text_group"] == "urn:cts:greekLit:tlg0012"
    assert result["author_scope"]["note"].startswith("Author scope was sent")
