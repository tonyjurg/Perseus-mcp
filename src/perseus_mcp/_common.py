"""Normalize XML text, language names, and pagination arguments shared by the tools."""

from __future__ import annotations

import xml.etree.ElementTree as ET

__all__ = [
    "_COMMON_LANGUAGE_CODES",
    "_MAX_LIST_LIMIT",
    "_XML_LANG",
    "_bounded_list_limit",
    "_direct_child_texts",
    "_direct_children",
    "_element_language",
    "_element_text",
    "_local_name",
    "_non_negative_int",
    "_normalize_cts_language",
    "_normalize_search_kind",
    "_normalize_search_language",
    "_normalize_search_result_format",
    "_normalize_space",
    "_positive_int",
]


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


def _local_name(tag: str) -> str:
    """Return an XML tag name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _normalize_space(text: str | None) -> str:
    """Collapse whitespace and map a missing string to an empty string."""
    return " ".join((text or "").split())


def _element_text(element: ET.Element) -> str:
    """Join descendant XML text and normalize its whitespace."""
    return _normalize_space("".join(element.itertext()))


def _direct_children(
    element: ET.Element, local_name: str | None = None
) -> list[ET.Element]:
    """Return direct children, optionally matching a case-insensitive local tag name."""
    if local_name is None:
        return list(element)
    normalized_name = local_name.casefold()
    return [
        child
        for child in element
        if _local_name(child.tag).casefold() == normalized_name
    ]


def _direct_child_texts(element: ET.Element, local_name: str) -> list[str]:
    """Return normalized, nonempty text values from matching direct children."""
    values: list[str] = []
    for child in _direct_children(element, local_name):
        value = _element_text(child)
        if value:
            values.append(value)
    return values


def _element_language(element: ET.Element) -> str | None:
    """Read the XML language attribute, accepting expanded and literal spellings."""
    return element.attrib.get(_XML_LANG) or element.attrib.get("xml:lang")


def _normalize_cts_language(language: str | None) -> str | None:
    """Map known Greek/Latin aliases to CTS codes and preserve other normalized codes."""
    normalized = _normalize_space(language).casefold().replace("-", "_")
    if not normalized:
        return None
    return _COMMON_LANGUAGE_CODES.get(normalized, normalized)


def _normalize_search_language(language: str | None) -> str:
    """Normalize a user-facing search language to Scaife's two-letter code.

    Accepts "greek"/"grc"/"gr" and case-insensitive variants for Greek, and
    "latin"/"lat"/"la" for Latin (see _COMMON_LANGUAGE_CODES). A missing or
    blank value defaults to Greek. Any other value raises ValueError instead
    of being silently truncated to its first two characters, which
    previously produced a nonsensical Scaife language code with no
    indication that the input was not recognized.
    """
    normalized_input = _normalize_space(language)
    if not normalized_input:
        return "gr"
    cts_language = _normalize_cts_language(normalized_input)
    if cts_language == "grc":
        return "gr"
    if cts_language == "lat":
        return "la"
    raise ValueError(
        "language must be a recognized Greek or Latin value, such as "
        f"'greek', 'grc', 'gr', 'latin', 'lat', or 'la' (got {language!r})"
    )


def _normalize_search_kind(search_kind: str | None) -> str:
    """Validate form or lemma search, defaulting an empty value to form."""
    normalized = _normalize_space(search_kind).casefold() or "form"
    if normalized not in {"form", "lemma"}:
        raise ValueError("search_kind must be one of: form, lemma")
    return normalized


def _normalize_search_result_format(result_format: str | None) -> str:
    """Validate instances or passages output, defaulting to instances."""
    normalized = _normalize_space(result_format).casefold() or "instances"
    if normalized not in {"instances", "passages"}:
        raise ValueError("result_format must be one of: instances, passages")
    return normalized


def _positive_int(value: int, name: str) -> int:
    """Return a value of at least one or raise ValueError naming the argument."""
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


_MAX_LIST_LIMIT = 500


def _bounded_list_limit(value: int, name: str = "limit") -> int:
    """Validate a result-page ``limit`` and cap it at _MAX_LIST_LIMIT.

    These limits bound how many entries a single tool call can return.
    Without an upper bound, a caller (or an LLM guessing at arguments) could
    request an arbitrarily large limit and get back a payload sized for
    nothing in particular, which is wasteful for the upstream fetch and
    expensive to push into a model's context window.
    """
    value = _positive_int(value, name)
    if value > _MAX_LIST_LIMIT:
        raise ValueError(f"{name} must not exceed {_MAX_LIST_LIMIT}")
    return value


def _non_negative_int(value: int, name: str) -> int:
    """Return a nonnegative value or raise ValueError naming the argument."""
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value
