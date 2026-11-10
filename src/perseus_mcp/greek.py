"""Convert Beta Code to Unicode Greek and normalize search queries without network access."""

from __future__ import annotations

import re
import unicodedata

from . import _common

__all__ = [
    "_BETACODE_COMBINING_MARKS",
    "_BETACODE_LETTERS",
    "_BETACODE_MARKERS",
    "_BETACODE_WORD_RE",
    "_betacode_to_greek",
    "_betacode_word_to_greek",
    "_looks_like_betacode",
    "_normalize_greek_query",
    "_normalize_query_for_search",
]


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
    "x": "χ",
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


def _looks_like_betacode(query: str) -> bool:
    """Detect explicit Beta Code marks or short ASCII alphabetic queries heuristically."""
    if any(marker in query for marker in _BETACODE_MARKERS):
        return True
    compact = query.replace(" ", "")
    return compact.isascii() and compact.isalpha() and len(compact) <= 32


def _betacode_word_to_greek(word: str) -> str:
    """Convert a Beta Code word, including accents, capitals, and final sigma, to NFC."""
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
    """Convert Beta Code words while preserving surrounding punctuation and whitespace."""
    return _BETACODE_WORD_RE.sub(
        lambda match: _betacode_word_to_greek(match.group(0)), query
    )


def _normalize_greek_query(query: str, query_format: str = "auto") -> str:
    """Normalize Unicode Greek or Beta Code search text to NFC Unicode Greek."""
    normalized_format = _common._normalize_space(query_format).casefold() or "auto"
    if normalized_format not in {"auto", "betacode", "unicode"}:
        raise ValueError("query_format must be one of: auto, betacode, unicode")

    if normalized_format == "unicode":
        return unicodedata.normalize("NFC", query)
    if normalized_format == "betacode" or _looks_like_betacode(query):
        return _betacode_to_greek(query)
    return unicodedata.normalize("NFC", query)


def _normalize_query_for_search(
    query: str,
    language: str = "greek",
    query_format: str = "auto",
    preserve_operators: bool = False,
) -> str:
    """Validate a nonempty query and normalize Greek unless operators must be preserved."""
    if not _common._normalize_space(query):
        raise ValueError("query must not be empty")
    lang_code = _common._normalize_search_language(language)
    if preserve_operators:
        return unicodedata.normalize("NFC", query)
    if lang_code == "gr":
        return _normalize_greek_query(query, query_format)
    return query
