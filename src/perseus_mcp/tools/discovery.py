"""Expose author and work discovery from the upstream inventories as MCP tools."""

from __future__ import annotations

from .. import _app, _common
from .. import cts as _cts
from .. import discovery as _discovery

__all__ = [
    "find_author_names",
    "get_author_resources",
    "get_work_resources",
    "list_text_groups",
]


@_app._upstream_tool
async def list_text_groups(
    language: str | None = None,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> str:
    """List authors/textgroups and their works from CTS capabilities.

    Optional `language` accepts values such as "greek", "grc", "latin", or
    "lat". Optional `query` matches author names, textgroup URNs, or work
    titles. `limit` must be between 1 and 500. Use `offset` with `has_more`
    to page through matching textgroups.
    """
    capabilities_xml = await _cts._get_capabilities_cached()
    return _discovery._list_text_groups_from_capabilities(
        capabilities_xml, language, query, limit, offset
    )


@_app._upstream_tool
async def get_author_resources(author: str, language: str | None = None) -> str:
    """List CTS works/editions/translations for an author name or textgroup URN.

    Examples:
    - author: "Homer"
    - author: "tlg0012"
    - author: "urn:cts:greekLit:tlg0012"
    """
    capabilities_xml = await _cts._get_capabilities_cached()
    return _discovery._author_resources_from_capabilities(
        capabilities_xml, author, language
    )


@_app._upstream_tool
async def find_author_names(
    query: str,
    language: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> str:
    """Find author/textgroup names by partial name match across Perseus catalogs.

    This merges the legacy CTS capabilities inventory with Scaife's library
    catalog, then matches author/textgroup name fields only, not work titles.
    A result can therefore be found when either upstream inventory contains it.
    `limit` must be between 1 and 500. Use `offset` with `has_more` to page
    through all matching authors.
    Examples:
    - query: "Hom"
    - query: "Plut"
    """
    if not _common._normalize_space(query):
        raise ValueError("query must not be empty")
    authors = await _discovery._resolve_author_entries(query, language, names_only=True)
    return _discovery._author_name_matches_response(
        authors, query, language, limit, offset
    )


@_app._upstream_tool
async def get_work_resources(urn_or_title: str, language: str | None = None) -> str:
    """List editions/translations/resources for a matching work URN or title.

    Optional `language` accepts values such as "greek", "grc", "latin", or
    "lat" and filters by the original work language.

    Examples:
    - urn_or_title: "urn:cts:greekLit:tlg0012.tlg001"
    - urn_or_title: "Iliad"
    """
    capabilities_xml = await _cts._get_capabilities_cached()
    return _discovery._work_resources_from_capabilities(
        capabilities_xml, urn_or_title, language
    )
