import pytest
from defusedxml.common import EntitiesForbidden

from perseus_mcp.server import (
    _capabilities_root,
    _is_xml_response,
    _passage_plaintext_from_xml,
    _reference_urns_from_xml,
)


# A "billion laughs" style entity-expansion payload. A handful of nested
# entity definitions like this can expand to an enormous in-memory string;
# defusedxml refuses to expand any custom entities at all rather than trying
# to bound the expansion.
_BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
]>
<lolz>&lol2;</lolz>
"""

_NORMAL_REFERENCES_XML = (
    '<GetValidReff xmlns="http://chs.harvard.edu/xmlns/cts">'
    "<reply><urn>urn:cts:greekLit:tlg0012.tlg001:1.1</urn></reply>"
    "</GetValidReff>"
)

_NORMAL_PASSAGE_XML = (
    '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
    "<text><body><div><l>Sing, O goddess, the anger</l></div></body></text>"
    "</TEI>"
)

_NORMAL_CAPABILITIES_XML = (
    '<GetCapabilities xmlns="http://chs.harvard.edu/xmlns/cts">'
    "<TextInventory/></GetCapabilities>"
)


def test_well_formed_xml_still_parses_normally() -> None:
    # Sanity check: switching to defusedxml must not change behavior for
    # ordinary, well-formed upstream responses.
    assert _reference_urns_from_xml(_NORMAL_REFERENCES_XML) == [
        "urn:cts:greekLit:tlg0012.tlg001:1.1"
    ]
    assert "Sing, O goddess" in _passage_plaintext_from_xml(_NORMAL_PASSAGE_XML)
    assert _capabilities_root(_NORMAL_CAPABILITIES_XML).tag.endswith("GetCapabilities")
    assert _is_xml_response(_NORMAL_CAPABILITIES_XML, "GetCapabilities") is True


def test_reference_urns_from_xml_rejects_entity_expansion_payload() -> None:
    with pytest.raises(EntitiesForbidden):
        _reference_urns_from_xml(_BILLION_LAUGHS)


def test_passage_plaintext_from_xml_rejects_entity_expansion_payload() -> None:
    with pytest.raises(EntitiesForbidden):
        _passage_plaintext_from_xml(_BILLION_LAUGHS)


def test_capabilities_root_rejects_entity_expansion_payload() -> None:
    with pytest.raises(EntitiesForbidden):
        _capabilities_root(_BILLION_LAUGHS)


def test_is_xml_response_treats_entity_expansion_payload_as_not_matching() -> None:
    # Unlike the other parsing call sites, _is_xml_response is a best-effort
    # probe ("does this look like the expected XML reply?") and should
    # degrade to False rather than raising, matching its existing behavior
    # for plain malformed XML.
    assert _is_xml_response(_BILLION_LAUGHS, "GetCapabilities") is False
