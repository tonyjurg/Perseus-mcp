"""Build Scaife URLs, cache its catalogue, and apply author scopes to search results."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

from . import cache as _cache
from . import http as _http
from . import upstream as _upstream

__all__ = [
    "SCAIFE_LIBRARY",
    "SCAIFE_LIBRARY_CATALOG",
    "SCAIFE_SEARCH",
    "_CTS_URN_RE",
    "_add_author_scope_metadata",
    "_extract_cts_urns",
    "_filter_scaife_search_response_by_author",
    "_get_scaife_library_catalog_cached",
    "_quote_urn_path_segment",
    "_result_matches_author_scope",
    "_scaife_library_url",
    "_scaife_passage_json_url",
    "_scaife_passage_text_url",
    "_single_author_text_group_urn",
    "_urn_matches_scope",
    "_urn_scope_values_from_author_entries",
]


SCAIFE_SEARCH = "https://scaife.perseus.org/search/json/"


SCAIFE_LIBRARY = "https://scaife.perseus.org/library/"


SCAIFE_LIBRARY_CATALOG = f"{SCAIFE_LIBRARY.rstrip('/')}/json/"


_CTS_URN_RE = re.compile(r"urn:cts:[^\s\"'<>]+")


async def _get_scaife_library_catalog_cached(refresh: bool = False) -> str:
    """Return validated Scaife catalogue JSON, optionally refreshing both caches."""
    return await _cache._cached_text(
        "scaife_library",
        {"url": SCAIFE_LIBRARY_CATALOG},
        lambda: _http._get(
            SCAIFE_LIBRARY_CATALOG, validator=_upstream.validate_catalogue
        ),
        extension="json",
        refresh=refresh,
        disk_validator=_upstream.validate_catalogue,
    )


def _urn_scope_values_from_author_entries(authors: list[dict[str, Any]]) -> list[str]:
    """Collect unique author, work, and resource URNs for local search filtering."""
    prefixes: list[str] = []

    def add(value: str | None) -> None:
        """Append a nonempty scope URN once, preserving insertion order."""
        if value and value not in prefixes:
            prefixes.append(value)

    for author in authors:
        add(author.get("urn"))
        for work in author.get("works", []):
            add(work.get("urn"))
            for resource in work.get("resources", []):
                add(resource.get("urn"))

    return prefixes


def _extract_cts_urns(value: Any) -> list[str]:
    """Recursively extract CTS URNs from strings, lists, and JSON object values."""
    urns: list[str] = []

    if isinstance(value, str):
        urns.extend(
            match.group(0).rstrip(".,;)]}") for match in _CTS_URN_RE.finditer(value)
        )
    elif isinstance(value, dict):
        for item in value.values():
            urns.extend(_extract_cts_urns(item))
    elif isinstance(value, list):
        for item in value:
            urns.extend(_extract_cts_urns(item))

    return urns


def _urn_matches_scope(urn: str, scope_urns: list[str]) -> bool:
    """Match a URN at a scope boundary, including subordinate works and passages."""
    for scope_urn in scope_urns:
        if urn == scope_urn or urn.startswith((f"{scope_urn}.", f"{scope_urn}:")):
            return True
    return False


def _result_matches_author_scope(result: Any, scope_urns: list[str]) -> bool:
    """Return whether a search result contains any URN within the author scope."""
    return any(_urn_matches_scope(urn, scope_urns) for urn in _extract_cts_urns(result))


def _quote_urn_path_segment(urn: str) -> str:
    """Percent-encode a URN for safe use as a single URL path segment.

    CTS URNs legitimately contain colons and periods, so those are left
    unescaped for readability; everything else (spaces, '#', '?', '%',
    non-ASCII characters, etc.) is encoded so the value cannot truncate the
    URL, inject query parameters, or otherwise change the request target.
    """
    return quote(urn, safe=":.")


def _scaife_library_url(urn: str) -> str:
    """Build the JSON metadata URL for a safely encoded CTS URN."""
    return f"{SCAIFE_LIBRARY.rstrip('/')}/{_quote_urn_path_segment(urn)}/json/"


def _scaife_passage_json_url(urn: str) -> str:
    """Build the passage JSON URL for a safely encoded CTS URN."""
    return f"{SCAIFE_LIBRARY.rstrip('/')}/passage/{_quote_urn_path_segment(urn)}/json/"


def _scaife_passage_text_url(urn: str) -> str:
    """Build the passage plaintext URL for a safely encoded CTS URN."""
    return f"{SCAIFE_LIBRARY.rstrip('/')}/passage/{_quote_urn_path_segment(urn)}/text/"


def _single_author_text_group_urn(authors: list[dict[str, Any]]) -> str | None:
    """Return a textgroup URN only when exactly one nonempty author URN exists."""
    urns = [author.get("urn") for author in authors if author.get("urn")]
    return urns[0] if len(urns) == 1 else None


def _add_author_scope_metadata(
    response_text: str,
    author: str,
    authors: list[dict[str, Any]],
    text_group: str,
) -> str:
    """Annotate object-shaped results with the author filter sent to Scaife."""
    data = json.loads(response_text)
    if isinstance(data, dict):
        data["author_scope"] = {
            "query": author,
            "match_count": len(authors),
            "text_group": text_group,
            "note": "Author scope was sent to Scaife as a server-side text_group filter.",
        }
        return json.dumps(data, ensure_ascii=False, indent=2)
    return response_text


def _filter_scaife_search_response_by_author(
    response_text: str,
    author: str,
    authors: list[dict[str, Any]],
) -> str:
    """Filter the current result page by author URNs and annotate the scope/counts."""
    data = json.loads(response_text)
    scope_urns = _urn_scope_values_from_author_entries(authors)

    if isinstance(data, dict) and isinstance(data.get("results"), list):
        results = data["results"]
        filtered_results = [
            result
            for result in results
            if _result_matches_author_scope(result, scope_urns)
        ]
        data["results"] = filtered_results
        data["author_scope"] = {
            "query": author,
            "match_count": len(authors),
            "urns": scope_urns,
            "unfiltered_page_result_count": len(results),
            "filtered_page_result_count": len(filtered_results),
            "note": "Author scope is applied locally to the current Scaife result page.",
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    if isinstance(data, list):
        filtered_results = [
            result
            for result in data
            if _result_matches_author_scope(result, scope_urns)
        ]
        return json.dumps(
            {
                "results": filtered_results,
                "author_scope": {
                    "query": author,
                    "match_count": len(authors),
                    "urns": scope_urns,
                    "unfiltered_page_result_count": len(data),
                    "filtered_page_result_count": len(filtered_results),
                    "note": "Author scope is applied locally to the current Scaife result page.",
                },
            },
            ensure_ascii=False,
            indent=2,
        )

    raise _upstream.UpstreamFailure(
        "INVALID_PAYLOAD", "The upstream search response has an unexpected format."
    )
