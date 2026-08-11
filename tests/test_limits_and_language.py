import asyncio

import pytest

from perseus_mcp import server
from perseus_mcp.server import (
    _author_name_matches_response,
    _bounded_list_limit,
    _list_text_groups_from_capabilities,
    _normalize_search_language,
    _valid_references_json,
)

# --- _bounded_list_limit -----------------------------------------------


def test_bounded_list_limit_accepts_value_within_range() -> None:
    assert _bounded_list_limit(1) == 1
    assert _bounded_list_limit(500) == 500


def test_bounded_list_limit_rejects_non_positive_value() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        _bounded_list_limit(0)


def test_bounded_list_limit_rejects_value_over_max() -> None:
    with pytest.raises(ValueError, match="must not exceed 500"):
        _bounded_list_limit(501)


# --- callers that previously had no upper bound on `limit` --------------


def test_valid_references_json_rejects_excessive_limit() -> None:
    references_xml = (
        '<GetValidReff xmlns="http://chs.harvard.edu/xmlns/cts">'
        "<reply><urn>urn:cts:greekLit:tlg0012.tlg001:1.1</urn></reply>"
        "</GetValidReff>"
    )
    with pytest.raises(ValueError, match="must not exceed 500"):
        _valid_references_json(references_xml, "urn:cts:greekLit:tlg0012.tlg001", limit=10_000)


def test_list_text_groups_rejects_excessive_limit() -> None:
    with pytest.raises(ValueError, match="must not exceed 500"):
        _list_text_groups_from_capabilities("<GetCapabilities/>", limit=10_000)


def test_list_text_groups_rejects_negative_offset() -> None:
    with pytest.raises(ValueError, match="offset must not be negative"):
        _list_text_groups_from_capabilities("<GetCapabilities/>", offset=-1)


def test_find_author_names_rejects_excessive_limit() -> None:
    with pytest.raises(ValueError, match="must not exceed 500"):
        _author_name_matches_response([], "Hom", limit=10_000)


def test_find_author_names_rejects_negative_offset() -> None:
    with pytest.raises(ValueError, match="offset must not be negative"):
        _author_name_matches_response([], "Hom", offset=-1)


def test_find_author_names_still_validates_empty_query_first() -> None:
    # Empty-query validation should still fire even with a too-large limit,
    # since the error message for a clearly missing query is more useful.
    with pytest.raises(ValueError, match="query must not be empty"):
        asyncio.run(server.find_author_names("   ", limit=10_000))


def test_search_within_text_rejects_excessive_size() -> None:
    with pytest.raises(ValueError, match="size must not exceed 500"):
        asyncio.run(
            server.search_within_text(
                "arma",
                "urn:cts:latinLit:phi0690.phi003",
                language="latin",
                size=10_000,
            )
        )


# --- _normalize_search_language ------------------------------------------


def test_normalize_search_language_accepts_known_aliases() -> None:
    assert _normalize_search_language("Ancient Greek") == "gr"
    assert _normalize_search_language("latin") == "la"
    assert _normalize_search_language("grc") == "gr"
    assert _normalize_search_language("lat") == "la"
    assert _normalize_search_language("GR") == "gr"
    assert _normalize_search_language("LA") == "la"


def test_normalize_search_language_defaults_to_greek_for_missing_value() -> None:
    assert _normalize_search_language(None) == "gr"
    assert _normalize_search_language("") == "gr"
    assert _normalize_search_language("   ") == "gr"


def test_normalize_search_language_rejects_unrecognized_value() -> None:
    with pytest.raises(ValueError, match="language must be a recognized"):
        _normalize_search_language("english")


def test_normalize_search_language_error_message_includes_offending_value() -> None:
    with pytest.raises(ValueError, match=r"got 'xyz'"):
        _normalize_search_language("xyz")
