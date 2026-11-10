"""Expose Scaife searches with Greek normalization and optional author scoping."""

from __future__ import annotations

from typing import Any

from .. import _app, _common
from .. import discovery as _discovery
from .. import greek as _greek
from .. import http as _http
from .. import scaife as _scaife
from .. import upstream as _upstream

__all__ = ["get_passage_highlights", "search_perseus", "search_within_text"]


@_app._upstream_tool
async def search_perseus(
    query: str,
    language: str = "greek",
    query_format: str = "auto",
    author: str | None = None,
    search_kind: str = "form",
    preserve_operators: bool = False,
    page_num: int = 1,
    text_group: str | None = None,
    work: str | None = None,
    result_format: str = "instances",
) -> str:
    """Search Perseus texts via Scaife API.

    For Greek searches, `query` may be Unicode Greek or Beta Code.  The default
    `query_format="auto"` detects explicit Beta Code marks such as `=`, `/`,
    `(`, `)`, and `*`, and also accepts short unaccented Beta Code queries such
    as `logos`.  Set `query_format="betacode"` to force conversion or
    `query_format="unicode"` to preserve ASCII text in Greek searches.
    The `language` value determines whether Greek query normalization is applied;
    it is not sent to Scaife as a corpus language filter.
    Optional `author` resolves a CTS author/textgroup name or URN, then locally
    filters the current Scaife result page to matching CTS URN prefixes.
    `search_kind` may be "form" or "lemma". Set `preserve_operators=True` for
    Scaife operator queries such as quoted phrases, `-`, `|`, `*`, or `~`.
    Optional `page_num`, `text_group`, `work`, and `result_format` are passed
    to Scaife's library search endpoint. When `author` resolves to exactly one
    CTS textgroup and no explicit `text_group` or `work` is supplied, the
    author scope is sent to Scaife as a server-side `text_group` filter.
    """
    normalized_search_kind = _common._normalize_search_kind(search_kind)
    normalized_query = _greek._normalize_query_for_search(
        query, language, query_format, preserve_operators
    )
    normalized_page_num = _common._positive_int(page_num, "page_num")
    normalized_result_format = _common._normalize_search_result_format(result_format)

    authors: list[dict[str, Any]] = []
    resolved_author_text_group: str | None = None
    if author is not None and _common._normalize_space(author):
        authors = await _discovery._resolve_author_entries(author, language)
        resolved_author_text_group = _scaife._single_author_text_group_urn(authors)

    effective_text_group = _common._normalize_space(text_group) or None
    effective_work = _common._normalize_space(work) or None
    if (
        effective_text_group is None
        and effective_work is None
        and resolved_author_text_group is not None
    ):
        effective_text_group = resolved_author_text_group

    params: dict[str, Any] = {
        "q": normalized_query,
        "kind": normalized_search_kind,
        "format": normalized_result_format,
        "type": "library",
        "page_num": normalized_page_num,
    }
    if effective_text_group:
        params["text_group"] = effective_text_group
    if effective_work:
        params["work"] = effective_work

    response_text = await _http._get(
        _scaife.SCAIFE_SEARCH,
        params=params,
        validator=_upstream.validate_search,
    )
    if author is None or not _common._normalize_space(author):
        return response_text

    if effective_text_group and effective_text_group == resolved_author_text_group:
        return _scaife._add_author_scope_metadata(
            response_text, author, authors, effective_text_group
        )

    return _scaife._filter_scaife_search_response_by_author(
        response_text, author, authors
    )


@_app._upstream_tool
async def search_within_text(
    query: str,
    text_urn: str,
    language: str = "greek",
    query_format: str = "auto",
    search_kind: str = "form",
    preserve_operators: bool = False,
    size: int = 10,
    offset: int = 0,
) -> str:
    """Search within a single Scaife text/edition URN.

    `size` must be between 1 and 500.
    """
    normalized_query = _greek._normalize_query_for_search(
        query, language, query_format, preserve_operators
    )
    return await _http._get(
        _scaife.SCAIFE_SEARCH,
        params={
            "q": normalized_query,
            "kind": _common._normalize_search_kind(search_kind),
            "type": "reader",
            "text": text_urn,
            "size": _common._bounded_list_limit(size, "size"),
            "offset": _common._non_negative_int(offset, "offset"),
            "fields": "",
        },
        validator=_upstream.validate_search,
    )


@_app._upstream_tool
async def get_passage_highlights(
    query: str,
    passage_urn: str,
    language: str = "greek",
    query_format: str = "auto",
    search_kind: str = "form",
    preserve_operators: bool = False,
) -> str:
    """Get Scaife token highlight positions for a query within one passage."""
    normalized_query = _greek._normalize_query_for_search(
        query, language, query_format, preserve_operators
    )
    return await _http._get(
        _scaife.SCAIFE_SEARCH,
        params={
            "q": normalized_query,
            "kind": _common._normalize_search_kind(search_kind),
            "type": "reader",
            "passage": passage_urn,
            "size": 1,
            "fields": "highlights",
        },
        validator=_upstream.validate_search,
    )
