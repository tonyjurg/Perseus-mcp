from __future__ import annotations

import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from typing import Any

import httpx
from fastmcp import FastMCP

mcp = FastMCP("perseus")

CTS_BASE = "https://www.perseus.tufts.edu/hopper/CTS"
SCAIFE_SEARCH = "https://scaife.perseus.org/search/json/"
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_COMMON_LANGUAGE_CODES = {
    "gr": "grc",
    "greek": "grc",
    "grc": "grc",
    "ancient greek": "grc",
    "ancient_greek": "grc",
    "la": "lat",
    "lat": "lat",
    "latin": "lat",
}

_GREEK_LANGUAGE_CODES = {
    "gr": "gr",
    "greek": "gr",
    "grc": "gr",
    "ancient greek": "gr",
    "ancient_greek": "gr",
    "la": "la",
    "lat": "la",
    "latin": "la",
}

_BETACODE_LETTERS = {
    "a": "α",
    "b": "β",
    "g": "γ",
    "d": "δ",
    "e": "ε",
    "z": "ζ",
    "h": "η",
    "q": "θ",
    "i": "ι",
    "k": "κ",
    "l": "λ",
    "m": "μ",
    "n": "ν",
    "c": "ξ",
    "x": "ξ",
    "o": "ο",
    "p": "π",
    "r": "ρ",
    "s": "σ",
    "t": "τ",
    "u": "υ",
    "f": "φ",
    "v": "ϝ",
    "y": "ψ",
    "w": "ω",
}
_BETACODE_COMBINING_MARKS = {
    ")": "\u0313",  # smooth breathing
    "(": "\u0314",  # rough breathing
    "/": "\u0301",  # acute
    "\\": "\u0300",  # grave
    "=": "\u0342",  # circumflex
    "|": "\u0345",  # iota subscript
    "+": "\u0308",  # diaeresis
}
_BETACODE_MARKERS = frozenset("*()/\\=|+")
_BETACODE_WORD_RE = re.compile(r"[A-Za-z*()/\\=|+]+")


async def _get(url: str, params: dict[str, Any] | None = None, timeout: float = 20.0) -> str:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.text


async def _cts_request(request: str, urn: str | None = None, **extra_params: Any) -> str:
    params: dict[str, Any] = {"request": request, **extra_params}
    if urn:
        params["urn"] = urn
    return await _get(CTS_BASE, params=params)


def _local_name(tag: str) -> str:
    """Return an XML tag name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _normalize_space(text: str | None) -> str:
    return " ".join((text or "").split())


def _element_text(element: ET.Element) -> str:
    return _normalize_space("".join(element.itertext()))


def _direct_children(element: ET.Element, local_name: str | None = None) -> list[ET.Element]:
    if local_name is None:
        return list(element)
    normalized_name = local_name.casefold()
    return [
        child
        for child in element
        if _local_name(child.tag).casefold() == normalized_name
    ]


def _direct_child_texts(element: ET.Element, local_name: str) -> list[str]:
    values: list[str] = []
    for child in _direct_children(element, local_name):
        value = _element_text(child)
        if value:
            values.append(value)
    return values


def _element_language(element: ET.Element) -> str | None:
    return element.attrib.get(_XML_LANG) or element.attrib.get("xml:lang")


def _normalize_cts_language(language: str | None) -> str | None:
    normalized = _normalize_space(language).casefold().replace("-", "_")
    if not normalized:
        return None
    return _COMMON_LANGUAGE_CODES.get(normalized, normalized)


def _normalize_search_language(language: str | None) -> str:
    cts_language = _normalize_cts_language(language)
    if cts_language == "grc":
        return "gr"
    if cts_language == "lat":
        return "la"
    return (language or "gr")[:2]


def _normalize_language(language: str | None) -> str:
    """Normalize a user-facing search language to Scaife's two-letter code."""
    return _normalize_search_language(language)


def _looks_like_betacode(query: str) -> bool:
    if any(marker in query for marker in _BETACODE_MARKERS):
        return True
    compact = query.replace(" ", "")
    return compact.isascii() and compact.isalpha() and len(compact) <= 32


def _betacode_word_to_greek(word: str) -> str:
    output: list[str] = []
    pending_marks: list[str] = []
    uppercase_next = False

    for index, character in enumerate(word):
        if character == "*":
            uppercase_next = True
            continue
        if character in _BETACODE_COMBINING_MARKS:
            mark = _BETACODE_COMBINING_MARKS[character]
            if output:
                output[-1] += mark
            else:
                pending_marks.append(mark)
            continue

        greek = _BETACODE_LETTERS.get(character.casefold())
        if character.casefold() == "s" and not any(
            later.isalpha() for later in word[index + 1 :]
        ):
            greek = "ς"
        if greek is None:
            output.append(character)
            continue
        if uppercase_next or character.isupper():
            greek = greek.upper()
            uppercase_next = False
        if pending_marks:
            greek += "".join(pending_marks)
            pending_marks.clear()
        output.append(greek)

    if pending_marks and output:
        output[-1] += "".join(pending_marks)
    return unicodedata.normalize("NFC", "".join(output))


def _betacode_to_greek(query: str) -> str:
    return _BETACODE_WORD_RE.sub(
        lambda match: _betacode_word_to_greek(match.group(0)), query
    )


def _normalize_greek_query(query: str, query_format: str = "auto") -> str:
    """Normalize Unicode Greek or Beta Code search text to NFC Unicode Greek."""
    normalized_format = _normalize_space(query_format).casefold() or "auto"
    if normalized_format not in {"auto", "betacode", "unicode"}:
        raise ValueError("query_format must be one of: auto, betacode, unicode")

    if normalized_format == "unicode":
        return unicodedata.normalize("NFC", query)
    if normalized_format == "betacode" or _looks_like_betacode(query):
        return _betacode_to_greek(query)
    return unicodedata.normalize("NFC", query)


def _resource_entry(element: ET.Element) -> dict[str, Any]:
    labels = _direct_child_texts(element, "label") or _direct_child_texts(element, "title")
    descriptions = _direct_child_texts(element, "description")
    entry = {
        "type": _local_name(element.tag),
        "urn": element.attrib.get("urn"),
        "language": _element_language(element),
        "label": labels[0] if labels else None,
        "description": descriptions[0] if descriptions else None,
    }
    return {key: value for key, value in entry.items() if value is not None}


def _work_entry(work: ET.Element) -> dict[str, Any]:
    resources = [
        _resource_entry(child)
        for child in _direct_children(work)
        if _local_name(child.tag) not in {"title"}
    ]
    return {
        "urn": work.attrib.get("urn"),
        "language": _element_language(work),
        "titles": _direct_child_texts(work, "title"),
        "editions": [resource for resource in resources if resource["type"] == "edition"],
        "translations": [
            resource for resource in resources if resource["type"] == "translation"
        ],
        "resources": resources,
    }


def _text_group_entry(text_group: ET.Element, include_works: bool = True) -> dict[str, Any]:
    works = [_work_entry(work) for work in _direct_children(text_group, "work")]
    entry: dict[str, Any] = {
        "urn": text_group.attrib.get("urn"),
        "names": _direct_child_texts(text_group, "groupname"),
        "works_count": len(works),
    }
    if include_works:
        entry["works"] = works
    return entry


def _capabilities_root(capabilities_xml: str) -> ET.Element:
    return ET.fromstring(capabilities_xml)


def _work_matches_language(work: dict[str, Any], language: str | None) -> bool:
    normalized = _normalize_cts_language(language)
    return normalized is None or work.get("language") == normalized


def _text_matches_query(values: list[str | None], query: str | None) -> bool:
    normalized_query = _normalize_space(query).casefold()
    if not normalized_query:
        return True
    return normalized_query in " ".join(value or "" for value in values).casefold()


def _query_match_rank(values: list[str | None], query: str) -> int:
    normalized_query = _normalize_space(query).casefold()
    normalized_values = [_normalize_space(value).casefold() for value in values]
    return 0 if normalized_query in normalized_values else 1


def _list_text_groups_from_capabilities(
    capabilities_xml: str,
    language: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> str:
    root = _capabilities_root(capabilities_xml)
    text_groups: list[dict[str, Any]] = []

    for text_group in root.iter():
        if _local_name(text_group.tag).casefold() != "textgroup":
            continue
        entry = _text_group_entry(text_group)
        works = [work for work in entry["works"] if _work_matches_language(work, language)]
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
        if len(text_groups) >= limit:
            break

    return json.dumps(
        {
            "query": query,
            "language": _normalize_cts_language(language),
            "match_count": len(text_groups),
            "text_groups": text_groups,
        },
        ensure_ascii=False,
        indent=2,
    )


def _author_resources_from_capabilities(
    capabilities_xml: str, author: str, language: str | None = None
) -> str:
    query = _normalize_space(author)
    if not query:
        raise ValueError("author must not be empty")

    root = _capabilities_root(capabilities_xml)
    authors: list[dict[str, Any]] = []

    for text_group in root.iter():
        if _local_name(text_group.tag).casefold() != "textgroup":
            continue
        entry = _text_group_entry(text_group)
        if not _text_matches_query([entry.get("urn"), *entry.get("names", [])], query):
            continue
        works = [work for work in entry["works"] if _work_matches_language(work, language)]
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

    return json.dumps(
        {
            "query": author,
            "language": _normalize_cts_language(language),
            "match_count": len(authors),
            "authors": authors,
        },
        ensure_ascii=False,
        indent=2,
    )


def _work_resources_from_capabilities(capabilities_xml: str, urn_or_title: str) -> str:
    query = _normalize_space(urn_or_title)
    if not query:
        raise ValueError("urn_or_title must not be empty")

    root = _capabilities_root(capabilities_xml)
    matches: list[dict[str, Any]] = []

    for text_group in root.iter():
        if _local_name(text_group.tag).casefold() != "textgroup":
            continue
        author = _text_group_entry(text_group, include_works=False)
        for work_element in _direct_children(text_group, "work"):
            work = _work_entry(work_element)
            searchable = [work.get("urn"), *work.get("titles", [])]
            if not _text_matches_query(searchable, query):
                continue
            matches.append({"author": author, "work": work})

    return json.dumps(
        {"query": urn_or_title, "match_count": len(matches), "matches": matches},
        ensure_ascii=False,
        indent=2,
    )


def _passage_plaintext_from_xml(passage_xml: str) -> str:
    root = ET.fromstring(passage_xml)
    text_parts: list[str] = []
    preferred_text_nodes = {"l", "p", "ab", "seg", "quote"}

    for element in root.iter():
        if _local_name(element.tag) not in preferred_text_nodes:
            continue
        text = _element_text(element)
        if text and text not in text_parts:
            text_parts.append(text)

    if not text_parts:
        for element in root.iter():
            if _local_name(element.tag) in {"text", "body", "div"}:
                text = _element_text(element)
                if text:
                    text_parts.append(text)
                    break

    if not text_parts:
        text_parts.append(_element_text(root))
    return "\n".join(part for part in text_parts if part)


def _is_xml_response(response_text: str, expected_root: str) -> bool:
    try:
        root = ET.fromstring(response_text)
    except ET.ParseError:
        return False
    return _local_name(root.tag).casefold() == expected_root.casefold()


def _reference_urns_from_xml(references_xml: str) -> list[str]:
    root = ET.fromstring(references_xml)
    return [
        _element_text(element)
        for element in root.iter()
        if _local_name(element.tag).casefold() == "urn" and _element_text(element)
    ]


def _prev_next_xml(urn: str, reference_urns: list[str]) -> str:
    root = ET.Element("GetPrevNextUrn")
    request = ET.SubElement(root, "request")
    ET.SubElement(request, "requestName").text = "GetPrevNextUrn"
    ET.SubElement(request, "requestUrn").text = urn
    reply = ET.SubElement(root, "reply")

    try:
        index = reference_urns.index(urn)
    except ValueError:
        ET.SubElement(reply, "error").text = f"URN not found in valid references: {urn}"
        return ET.tostring(root, encoding="unicode")

    if index > 0:
        previous = ET.SubElement(reply, "previous")
        ET.SubElement(previous, "urn").text = reference_urns[index - 1]
    if index + 1 < len(reference_urns):
        following = ET.SubElement(reply, "next")
        ET.SubElement(following, "urn").text = reference_urns[index + 1]
    return ET.tostring(root, encoding="unicode")


def _first_urn_xml(urn: str, reference_urns: list[str]) -> str:
    root = ET.Element("GetFirstUrn")
    request = ET.SubElement(root, "request")
    ET.SubElement(request, "requestName").text = "GetFirstUrn"
    ET.SubElement(request, "requestUrn").text = urn
    reply = ET.SubElement(root, "reply")
    if reference_urns:
        ET.SubElement(reply, "urn").text = reference_urns[0]
    else:
        ET.SubElement(reply, "error").text = f"No valid references found for: {urn}"
    return ET.tostring(root, encoding="unicode")


@mcp.tool
async def get_passage(urn: str) -> str:
    """Get the text of a specific passage using a CTS URN.

    Examples:
    - urn:cts:greekLit:tlg0012.tlg001:1.1-1.10
    - urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.1
    """
    return await _cts_request("GetPassage", urn=urn)


@mcp.tool
async def get_passage_plus(urn: str) -> str:
    """Get passage text plus surrounding metadata/context for a CTS URN."""
    return await _cts_request("GetPassagePlus", urn=urn)


@mcp.tool
async def get_passage_plaintext(urn: str) -> str:
    """Get a passage as plain readable text instead of raw CTS XML."""
    passage_xml = await _cts_request("GetPassage", urn=urn)
    return _passage_plaintext_from_xml(passage_xml)


@mcp.tool
async def get_valid_references(urn: str, level: int | None = None) -> str:
    """Get valid citations/references for a work, useful for navigation.

    Optionally pass a citation `level` to constrain returned references.
    """
    params: dict[str, Any] = {}
    if level is not None:
        params["level"] = str(level)
    return await _cts_request("GetValidReff", urn=urn, **params)


@mcp.tool
async def get_capabilities() -> str:
    """Get the list of available texts and editions from Perseus CTS."""
    return await _cts_request("GetCapabilities")


@mcp.tool
async def list_text_groups(
    language: str | None = None, query: str | None = None, limit: int = 100
) -> str:
    """List authors/textgroups and their works from CTS capabilities.

    Optional `language` accepts values such as "greek", "grc", "latin", or
    "lat". Optional `query` matches author names, textgroup URNs, or work titles.
    """
    capabilities_xml = await _cts_request("GetCapabilities")
    return _list_text_groups_from_capabilities(capabilities_xml, language, query, limit)


@mcp.tool
async def get_author_resources(author: str, language: str | None = None) -> str:
    """List CTS works/editions/translations for an author name or textgroup URN.

    Examples:
    - author: "Homer"
    - author: "tlg0012"
    - author: "urn:cts:greekLit:tlg0012"
    """
    capabilities_xml = await _cts_request("GetCapabilities")
    return _author_resources_from_capabilities(capabilities_xml, author, language)


@mcp.tool
async def get_work_resources(urn_or_title: str) -> str:
    """List editions/translations/resources for a matching work URN or title.

    Examples:
    - urn_or_title: "urn:cts:greekLit:tlg0012.tlg001"
    - urn_or_title: "Iliad"
    """
    capabilities_xml = await _cts_request("GetCapabilities")
    return _work_resources_from_capabilities(capabilities_xml, urn_or_title)


@mcp.tool
async def get_label(urn: str) -> str:
    """Get human-readable labels/metadata for a CTS URN (work or edition)."""
    return await _cts_request("GetLabel", urn=urn)


@mcp.tool
async def get_first_urn(urn: str) -> str:
    """Get the first available reference URN for a work/edition URN."""
    response = await _cts_request("GetFirstUrn", urn=urn)
    if _is_xml_response(response, "GetFirstUrn"):
        return response

    references_xml = await _cts_request("GetValidReff", urn=urn)
    return _first_urn_xml(urn, _reference_urns_from_xml(references_xml))


@mcp.tool
async def get_prev_next_urn(urn: str) -> str:
    """Get previous and next URNs for a passage URN."""
    response = await _cts_request("GetPrevNextUrn", urn=urn)
    if _is_xml_response(response, "GetPrevNextUrn"):
        return response

    work_urn, separator, _ = urn.rpartition(":")
    if not separator:
        return response
    references_xml = await _cts_request("GetValidReff", urn=work_urn)
    return _prev_next_xml(urn, _reference_urns_from_xml(references_xml))


@mcp.tool
async def search_perseus(
    query: str, language: str = "greek", query_format: str = "auto"
) -> str:
    """Search Perseus texts via Scaife API.

    For Greek searches, `query` may be Unicode Greek or Beta Code.  The default
    `query_format="auto"` detects explicit Beta Code marks such as `=`, `/`,
    `(`, `)`, and `*`, and also accepts short unaccented Beta Code queries such
    as `logos`.  Set `query_format="betacode"` to force conversion or
    `query_format="unicode"` to preserve ASCII text in Greek searches.
    The `language` value determines whether Greek query normalization is applied;
    it is not sent to Scaife as a corpus language filter.
    """
    lang_code = _normalize_search_language(language)
    normalized_query = (
        _normalize_greek_query(query, query_format) if lang_code == "gr" else query
    )
    return await _get(
        SCAIFE_SEARCH,
        params={
            "q": normalized_query,
            "kind": "form",
            "type": "library",
            "page_num": 1,
        },
    )


if __name__ == "__main__":
    mcp.run()
