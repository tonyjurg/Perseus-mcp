"""Bound caller-controlled strings and check CTS structure before cache or network use."""

from __future__ import annotations

import unicodedata

MAX_URN_LENGTH = 1024
MAX_QUERY_LENGTH = 2048
_FORBIDDEN_URN_CHARACTERS = frozenset('%/?#\\"&<>^`|{}~')
_DISALLOWED_TEXT_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})


def validate_text(
    value: str,
    name: str = "query",
    *,
    maximum: int = MAX_QUERY_LENGTH,
    allow_empty: bool = False,
) -> str:
    """Reject oversized or non-text input before normalization, without echoing it."""
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if len(value) > maximum:
        raise ValueError(f"{name} must not exceed {maximum} characters")
    if not allow_empty and not value.strip():
        raise ValueError(f"{name} must not be empty")
    if any(
        unicodedata.category(character) in _DISALLOWED_TEXT_CATEGORIES
        for character in value
    ):
        raise ValueError(f"{name} must not contain control or invisible characters")
    return value


def _identifier(value: str, *, hyphens: bool = True) -> bool:
    """Recognize nonempty Unicode identifiers without CTS structural separators."""
    return bool(value) and all(
        character.isalnum()
        or character == "_"
        or (hyphens and character == "-")
        or unicodedata.category(character).startswith("M")
        for character in value
    )


def _subreference(value: str) -> bool:
    """Accept one or two literal substrings with optional positive occurrence indexes."""
    elements = value.split("-")
    if not 1 <= len(elements) <= 2:
        return False
    for element in elements:
        literal, bracket, index = element.partition("[")
        if not literal or "@" in literal or "]" in literal:
            return False
        if bracket:
            if not index.endswith("]"):
                return False
            index = index[:-1]
            if not (index.isascii() and index.isdecimal() and index.strip("0")):
                return False
    return True


def _node(value: str) -> bool:
    """Check dotted citation labels and an optional Unicode substring reference."""
    citation, at, subreference = value.partition("@")
    return all(_identifier(part, hyphens=False) for part in citation.split(".")) and (
        not at or _subreference(subreference)
    )


def _passage(value: str) -> bool:
    """Check a node or node range with at most one substring range per endpoint."""
    # At most three separators: the node range plus two substring ranges.
    if value.count("-") > 3:
        return False
    if _node(value):
        return True
    return any(
        _node(value[:index]) and _node(value[index + 1 :])
        for index, character in enumerate(value)
        if character == "-"
    )


def validate_urn(value: str, name: str = "urn") -> str:
    """Validate bounded CTS syntax, retaining the catalogue's no-final-colon spelling.

    This checks structure, not whether a namespace, work, or citation exists.
    Author/work/edition/exemplar URNs may have an empty or omitted passage;
    passage labels, ranges, and Unicode subreferences remain supported.
    """
    validate_text(value, name, maximum=MAX_URN_LENGTH)
    invalid = f"{name} must be a CTS URN: urn:cts:namespace:textgroup[.work[.version[.exemplar]]][:passage]"
    if any(
        character.isspace() or character in _FORBIDDEN_URN_CHARACTERS
        for character in value
    ):
        raise ValueError(invalid)
    parts = value.split(":")
    if len(parts) not in {4, 5} or parts[:2] != ["urn", "cts"]:
        raise ValueError(invalid)
    namespace, work = parts[2:4]
    hierarchy = work.split(".")
    if not _identifier(namespace) or not 1 <= len(hierarchy) <= 4:
        raise ValueError(invalid)
    if not all(_identifier(part) for part in hierarchy):
        raise ValueError(invalid)
    if len(parts) == 5 and parts[4] and (len(hierarchy) < 2 or not _passage(parts[4])):
        raise ValueError(invalid)
    return value


def validate_optional_urn(value: str | None, name: str) -> str | None:
    """Keep omitted/blank search scopes optional while bounding their raw input."""
    if value is None:
        return None
    validate_text(value, name, maximum=MAX_URN_LENGTH, allow_empty=True)
    return validate_urn(value, name) if value.strip() else None


def validate_selector(value: str, name: str) -> str:
    """Bound author/title selectors and validate them as URNs when supplied as URNs."""
    validate_text(value, name)
    if value.strip().casefold().startswith("urn:"):
        validate_urn(value, name)
    return value
