"""Parse and merge CTS and Scaife inventories to discover authors, works, and editions."""

from __future__ import annotations

import asyncio
import json
import re
import xml.etree.ElementTree as ET
from copy import deepcopy
from typing import Any

from defusedxml.ElementTree import fromstring as _safe_xml_fromstring

from . import _common
from . import cts as _cts
from . import scaife as _scaife

__all__ = [
    "_author_name_matches_response",
    "_author_resources_from_capabilities",
    "_capabilities_root",
    "_language_from_cts_urn",
    "_list_text_groups_from_capabilities",
    "_matching_author_entries_from_capabilities",
    "_matching_author_entries_from_scaife_catalog",
    "_merge_author_entries",
    "_query_match_rank",
    "_resolve_author_entries",
    "_resource_entry",
    "_scaife_work_entry",
    "_text_group_entry",
    "_text_matches_query",
    "_work_entry",
    "_work_matches_language",
    "_work_resources_from_capabilities",
]


def _resource_entry(element: ET.Element) -> dict[str, Any]:
    """Convert a CTS edition or translation element into a compact resource record."""
    labels = _common._direct_child_texts(
        element, "label"
    ) or _common._direct_child_texts(element, "title")
    descriptions = _common._direct_child_texts(element, "description")
    entry = {
        "type": _common._local_name(element.tag),
        "urn": element.attrib.get("urn"),
        "language": _common._element_language(element),
        "label": labels[0] if labels else None,
        "description": descriptions[0] if descriptions else None,
    }
    return {key: value for key, value in entry.items() if value is not None}


def _work_entry(work: ET.Element) -> dict[str, Any]:
    """Convert a CTS work element into titles, language, and grouped resources."""
    resources = [
        _resource_entry(child)
        for child in _common._direct_children(work)
        if _common._local_name(child.tag) not in {"title"}
    ]
    return {
        "urn": work.attrib.get("urn"),
        "language": _common._element_language(work),
        "titles": _common._direct_child_texts(work, "title"),
        "editions": [
            resource for resource in resources if resource["type"] == "edition"
        ],
        "translations": [
            resource for resource in resources if resource["type"] == "translation"
        ],
        "resources": resources,
    }


def _text_group_entry(
    text_group: ET.Element, include_works: bool = True
) -> dict[str, Any]:
    """Convert a CTS textgroup into author names and an optional list of works."""
    works = [_work_entry(work) for work in _common._direct_children(text_group, "work")]
    entry: dict[str, Any] = {
        "urn": text_group.attrib.get("urn"),
        "names": _common._direct_child_texts(text_group, "groupname"),
        "works_count": len(works),
    }
    if include_works:
        entry["works"] = works
    return entry


def _capabilities_root(capabilities_xml: str) -> ET.Element:
    """Parse inventory XML with entity expansion and unsafe constructs disabled."""
    return _safe_xml_fromstring(capabilities_xml)


def _work_matches_language(work: dict[str, Any], language: str | None) -> bool:
    """Match a work against a normalized language, accepting all when unspecified."""
    normalized = _common._normalize_cts_language(language)
    return normalized is None or work.get("language") == normalized


def _text_matches_query(values: list[str | None], query: str | None) -> bool:
    """Match a case-insensitive substring across values; an empty query matches all."""
    normalized_query = _common._normalize_space(query).casefold()
    if not normalized_query:
        return True
    return normalized_query in " ".join(value or "" for value in values).casefold()


def _query_match_rank(values: list[str | None], query: str) -> tuple[int, int]:
    """Rank exact, word-prefix, prefix, and substring matches, then prefer shorter values."""
    normalized_query = _common._normalize_space(query).casefold()
    normalized_values = [_common._normalize_space(value).casefold() for value in values]

    def value_rank(value: str) -> tuple[int, int]:
        """Rank one normalized candidate by match position and candidate length."""
        if value == normalized_query:
            return (0, len(value))
        if re.match(rf"^{re.escape(normalized_query)}(?:$|\W)", value):
            return (1, len(value))
        if value.startswith(normalized_query):
            return (2, len(value))
        return (3, len(value))

    matches = [
        value_rank(value) for value in normalized_values if normalized_query in value
    ]
    return min(matches, default=(4, 0))


def _language_from_cts_urn(urn: str | None) -> str | None:
    """Infer Greek or Latin from a CTS namespace, returning None for other namespaces."""
    if not urn:
        return None
    namespace = urn.split(":", 3)[2].casefold() if urn.count(":") >= 3 else ""
    if namespace == "greeklit":
        return "grc"
    if namespace == "latinlit":
        return "lat"
    return None


def _scaife_work_entry(work: dict[str, Any]) -> dict[str, Any]:
    """Adapt a Scaife work to the shared inventory shape without inventing metadata."""
    urn = work.get("urn")
    return {
        "urn": urn,
        "language": _language_from_cts_urn(urn),
        "titles": [],
        "editions": [],
        "translations": [],
        "resources": [],
    }


def _matching_author_entries_from_scaife_catalog(
    catalog_json: str,
    author: str,
    language: str | None = None,
    *,
    names_only: bool = False,
) -> list[dict[str, Any]]:
    """Find authors in Scaife catalogue JSON, optionally matching names alone."""
    query = _common._normalize_space(author)
    if not query:
        raise ValueError("author must not be empty")

    data = json.loads(catalog_json)
    text_groups = data.get("text_groups", []) if isinstance(data, dict) else []
    normalized_language = _common._normalize_cts_language(language)
    authors: list[dict[str, Any]] = []

    for text_group in text_groups:
        if not isinstance(text_group, dict):
            continue
        label = _common._normalize_space(text_group.get("label"))
        names = [label] if label else []
        searchable: list[str | None] = names
        if not names_only:
            searchable = [text_group.get("urn"), *names]
        if not _text_matches_query(searchable, query):
            continue

        works = [
            _scaife_work_entry(work)
            for work in text_group.get("works", [])
            if isinstance(work, dict)
        ]
        if normalized_language is not None:
            works = [
                work for work in works if work.get("language") == normalized_language
            ]
            if not works:
                continue

        authors.append(
            {
                "urn": text_group.get("urn"),
                "names": names,
                "works_count": len(works),
                "works": works,
            }
        )

    authors.sort(
        key=lambda entry: _query_match_rank(
            [entry.get("urn"), *entry.get("names", [])], query
        )
    )
    return authors


def _merge_author_entries(
    *author_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge author inventories by URN, retaining metadata and avoiding duplicate works."""
    merged: dict[str, dict[str, Any]] = {}

    def merge_resources(
        existing: list[dict[str, Any]],
        incoming: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Copy and merge resources by URN, filling missing fields from incoming records."""
        resources = deepcopy(existing)
        positions = {
            resource.get("urn"): index
            for index, resource in enumerate(resources)
            if resource.get("urn")
        }
        for resource in incoming:
            resource_urn = resource.get("urn")
            if not resource_urn or resource_urn not in positions:
                resources.append(deepcopy(resource))
                if resource_urn:
                    positions[resource_urn] = len(resources) - 1
                continue

            target = resources[positions[resource_urn]]
            for field, value in resource.items():
                if field not in target or target[field] in (None, "", []):
                    target[field] = deepcopy(value)
        return resources

    def merge_work(
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> None:
        """Merge incoming work fields and resource lists into the existing record in place."""
        for field, value in incoming.items():
            if field in {"titles", "editions", "translations", "resources"}:
                continue
            if field not in existing or existing[field] in (None, "", []):
                existing[field] = deepcopy(value)

        if "titles" in existing or "titles" in incoming:
            titles = existing.setdefault("titles", [])
            for title in incoming.get("titles", []):
                if title not in titles:
                    titles.append(title)

        for field in ("editions", "translations", "resources"):
            if field in existing or field in incoming:
                existing[field] = merge_resources(
                    existing.get(field, []),
                    incoming.get(field, []),
                )

    for authors in author_groups:
        for author in authors:
            urn = author.get("urn")
            key = urn or "|".join(author.get("names", [])).casefold()
            if key not in merged:
                merged[key] = {
                    **deepcopy(author),
                    "names": [],
                    "works": [],
                }

            existing = merged[key]
            existing_names = existing.setdefault("names", [])
            for name in author.get("names", []):
                if name not in existing_names:
                    existing_names.append(name)

            existing_works: list[dict[str, Any]] = existing.setdefault("works", [])
            existing_work_positions = {
                work.get("urn"): index
                for index, work in enumerate(existing_works)
                if work.get("urn")
            }
            for work in author.get("works", []):
                work_urn = work.get("urn")
                if work_urn and work_urn in existing_work_positions:
                    merge_work(existing_works[existing_work_positions[work_urn]], work)
                    continue
                existing_works.append(deepcopy(work))
                if work_urn:
                    existing_work_positions[work_urn] = len(existing_works) - 1
            existing["works_count"] = len(existing_works)

    return list(merged.values())


async def _resolve_author_entries(
    author: str,
    language: str | None = None,
    *,
    names_only: bool = False,
) -> list[dict[str, Any]]:
    """Fetch both catalogues concurrently and merge matches; allow one source to fail."""

    async def from_cts() -> list[dict[str, Any]]:
        """Load CTS inventory and extract matching authors."""
        capabilities_xml = await _cts._get_capabilities_cached()
        return _matching_author_entries_from_capabilities(
            capabilities_xml, author, language, names_only=names_only
        )

    async def from_scaife() -> list[dict[str, Any]]:
        """Load the Scaife catalogue and extract matching authors."""
        catalog_json = await _scaife._get_scaife_library_catalog_cached()
        return _matching_author_entries_from_scaife_catalog(
            catalog_json, author, language, names_only=names_only
        )

    results = await asyncio.gather(from_cts(), from_scaife(), return_exceptions=True)
    successful = [result for result in results if isinstance(result, list)]
    if not successful:
        raise results[0]

    authors = _merge_author_entries(*successful)
    query = _common._normalize_space(author)
    authors.sort(
        key=lambda entry: _query_match_rank(
            [entry.get("urn"), *entry.get("names", [])], query
        )
    )
    return authors


def _matching_author_entries_from_capabilities(
    capabilities_xml: str,
    author: str,
    language: str | None = None,
    *,
    names_only: bool = False,
) -> list[dict[str, Any]]:
    """Find CTS authors by name or URN, with optional original-language filtering."""
    query = _common._normalize_space(author)
    if not query:
        raise ValueError("author must not be empty")

    root = _capabilities_root(capabilities_xml)
    authors: list[dict[str, Any]] = []

    for text_group in root.iter():
        if _common._local_name(text_group.tag).casefold() != "textgroup":
            continue
        entry = _text_group_entry(text_group)
        searchable = entry.get("names", [])
        if not names_only:
            searchable = [entry.get("urn"), *searchable]
        if not _text_matches_query(searchable, query):
            continue
        works = [
            work for work in entry["works"] if _work_matches_language(work, language)
        ]
        if not works and language is not None:
            continue
        entry["works"] = works
        entry["works_count"] = len(works)
        authors.append(entry)

    authors.sort(
        key=lambda entry: _query_match_rank(
            [entry.get("urn"), *entry.get("names", [])], query
        )
    )
    return authors


def _list_text_groups_from_capabilities(
    capabilities_xml: str,
    language: str | None = None,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> str:
    """Return a JSON page of matching CTS authors and their works."""
    limit = _common._bounded_list_limit(limit)
    offset = _common._non_negative_int(offset, "offset")
    root = _capabilities_root(capabilities_xml)
    text_groups: list[dict[str, Any]] = []

    for text_group in root.iter():
        if _common._local_name(text_group.tag).casefold() != "textgroup":
            continue
        entry = _text_group_entry(text_group)
        works = [
            work for work in entry["works"] if _work_matches_language(work, language)
        ]
        if not works:
            continue
        searchable = [entry.get("urn"), *entry.get("names", [])]
        searchable.extend(title for work in works for title in work.get("titles", []))
        if not _text_matches_query(searchable, query):
            continue
        text_groups.append(
            {
                "urn": entry["urn"],
                "names": entry["names"],
                "works_count": len(works),
                "works": [
                    {
                        "urn": work["urn"],
                        "language": work["language"],
                        "titles": work["titles"],
                    }
                    for work in works
                ],
            }
        )

    page = text_groups[offset : offset + limit]

    return json.dumps(
        {
            "query": query,
            "language": _common._normalize_cts_language(language),
            "total_count": len(text_groups),
            "offset": offset,
            "limit": limit,
            "returned_count": len(page),
            "has_more": offset + len(page) < len(text_groups),
            "text_groups": page,
        },
        ensure_ascii=False,
        indent=2,
    )


def _author_resources_from_capabilities(
    capabilities_xml: str, author: str, language: str | None = None
) -> str:
    """Serialize matching CTS authors with their editions and translations."""
    authors = _matching_author_entries_from_capabilities(
        capabilities_xml, author, language
    )

    return json.dumps(
        {
            "query": author,
            "language": _common._normalize_cts_language(language),
            "match_count": len(authors),
            "authors": authors,
        },
        ensure_ascii=False,
        indent=2,
    )


def _author_name_matches_response(
    authors: list[dict[str, Any]],
    query: str,
    language: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> str:
    """Serialize a ranked page of author matches with pagination metadata."""
    limit = _common._bounded_list_limit(limit)
    offset = _common._non_negative_int(offset, "offset")
    total_count = len(authors)
    authors = authors[offset : offset + limit]
    normalized_query = _common._normalize_space(query).casefold()

    return json.dumps(
        {
            "query": query,
            "language": _common._normalize_cts_language(language),
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
            "returned_count": len(authors),
            "has_more": offset + len(authors) < total_count,
            "authors": [
                {
                    "urn": author.get("urn"),
                    "names": author.get("names", []),
                    "matched_names": [
                        name
                        for name in author.get("names", [])
                        if normalized_query in _common._normalize_space(name).casefold()
                    ],
                    "works_count": author.get("works_count", 0),
                    "works": [
                        {
                            "urn": work.get("urn"),
                            "language": work.get("language"),
                            "titles": work.get("titles", []),
                        }
                        for work in author.get("works", [])
                    ],
                }
                for author in authors
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def _work_resources_from_capabilities(
    capabilities_xml: str,
    urn_or_title: str,
    language: str | None = None,
) -> str:
    """Find works by URN or title and serialize their available resources."""
    query = _common._normalize_space(urn_or_title)
    if not query:
        raise ValueError("urn_or_title must not be empty")

    root = _capabilities_root(capabilities_xml)
    matches: list[dict[str, Any]] = []

    for text_group in root.iter():
        if _common._local_name(text_group.tag).casefold() != "textgroup":
            continue
        author = _text_group_entry(text_group, include_works=False)
        for work_element in _common._direct_children(text_group, "work"):
            work = _work_entry(work_element)
            if not _work_matches_language(work, language):
                continue
            searchable = [work.get("urn"), *work.get("titles", [])]
            if not _text_matches_query(searchable, query):
                continue
            matches.append({"author": author, "work": work})

    return json.dumps(
        {
            "query": urn_or_title,
            "language": _common._normalize_cts_language(language),
            "match_count": len(matches),
            "matches": matches,
        },
        ensure_ascii=False,
        indent=2,
    )
