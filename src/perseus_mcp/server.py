from __future__ import annotations

import asyncio
from contextlib import suppress
from copy import deepcopy
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
import unicodedata
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring as _safe_xml_fromstring
from fastmcp import FastMCP

mcp = FastMCP("perseus")

CTS_BASE = "https://www.perseus.tufts.edu/hopper/CTS"
SCAIFE_SEARCH = "https://scaife.perseus.org/search/json/"
SCAIFE_LIBRARY = "https://scaife.perseus.org/library/"
SCAIFE_LIBRARY_CATALOG = f"{SCAIFE_LIBRARY.rstrip('/')}/json/"
DEFAULT_CACHE_TTL_SECONDS = 24 * 60 * 60
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
_CTS_URN_RE = re.compile(r"urn:cts:[^\s\"'<>]+")
_MEMORY_CACHE: dict[str, tuple[float, str]] = {}
_HTTP_CLIENT: httpx.AsyncClient | None = None
_HTTP_CLIENT_LOOP: asyncio.AbstractEventLoop | None = None


class UpstreamRateLimitWarning(UserWarning):
    """Warn that Perseus or Scaife rejected a request because of rate limiting."""


class MetadataCacheWarning(UserWarning):
    """Warn that the optional metadata cache could not be updated."""


async def _close_http_client(
    client: httpx.AsyncClient,
    client_loop: asyncio.AbstractEventLoop | None,
) -> None:
    """Close a client without failing when its owning loop has already ended."""
    if client.is_closed:
        return
    try:
        await client.aclose()
    except RuntimeError as exc:
        if (
            str(exc) != "Event loop is closed"
            or client_loop is None
            or not client_loop.is_closed()
        ):
            raise


async def _shared_client() -> httpx.AsyncClient:
    """Return a process-wide httpx.AsyncClient, reused across tool calls.

    Opening a brand new client (and therefore a new TCP/TLS connection) for
    every tool call is wasteful for a long-lived MCP server, especially for
    passage-processing workflows that make many sequential requests to the
    same Perseus/Scaife hosts. Reusing one client lets httpx pool and reuse
    connections instead.

    The client is recreated if the running event loop has changed (or the
    previous client was closed), since an httpx.AsyncClient's underlying
    transport is bound to the loop it was created on. In normal operation
    there is exactly one loop for the lifetime of the process; this check
    mainly matters for test suites that call ``asyncio.run()`` per test.
    """
    global _HTTP_CLIENT, _HTTP_CLIENT_LOOP
    running_loop = asyncio.get_running_loop()
    if (
        _HTTP_CLIENT is None
        or _HTTP_CLIENT.is_closed
        or _HTTP_CLIENT_LOOP is not running_loop
    ):
        if _HTTP_CLIENT is not None and not _HTTP_CLIENT.is_closed:
            await _close_http_client(_HTTP_CLIENT, _HTTP_CLIENT_LOOP)
        _HTTP_CLIENT = httpx.AsyncClient(follow_redirects=True)
        _HTTP_CLIENT_LOOP = running_loop
    return _HTTP_CLIENT


async def aclose_http_client() -> None:
    """Close the shared HTTP client, if one has been created.

    Not required for normal stdio server operation (the OS reclaims
    connections on process exit), but useful for tests and any embedding
    that wants a clean shutdown.
    """
    global _HTTP_CLIENT, _HTTP_CLIENT_LOOP
    client = _HTTP_CLIENT
    client_loop = _HTTP_CLIENT_LOOP
    try:
        if client is not None:
            await _close_http_client(client, client_loop)
    finally:
        _HTTP_CLIENT = None
        _HTTP_CLIENT_LOOP = None


async def _get(url: str, params: dict[str, Any] | None = None, timeout: float = 20.0) -> str:
    client = await _shared_client()
    response = await client.get(url, params=params, timeout=timeout)
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        retry_guidance = (
            f" Retry after {retry_after} seconds."
            if retry_after and retry_after.isdigit()
            else " Wait before retrying and reduce request concurrency."
        )
        warnings.warn(
            f"Upstream service rate limit (HTTP 429) from {response.request.url}."
            f"{retry_guidance} The request was not retried automatically.",
            UpstreamRateLimitWarning,
            stacklevel=2,
        )
    response.raise_for_status()
    return response.text


async def _cts_request(request: str, urn: str | None = None, **extra_params: Any) -> str:
    params: dict[str, Any] = {"request": request, **extra_params}
    if urn:
        params["urn"] = urn
    return await _get(CTS_BASE, params=params)


def _cache_enabled() -> bool:
    value = _normalize_space(os.environ.get("PERSEUS_MCP_DISABLE_CACHE")).casefold()
    return value not in {"1", "true", "yes", "on"}


def _cache_ttl_seconds() -> int:
    value = _normalize_space(os.environ.get("PERSEUS_MCP_CACHE_TTL_SECONDS"))
    if not value:
        return DEFAULT_CACHE_TTL_SECONDS
    try:
        ttl = int(value)
    except ValueError as exc:
        raise ValueError("PERSEUS_MCP_CACHE_TTL_SECONDS must be an integer") from exc
    return max(0, ttl)


def _cache_dir() -> Path:
    configured = _normalize_space(os.environ.get("PERSEUS_MCP_CACHE_DIR"))
    if configured:
        return Path(configured).expanduser()
    return Path.cwd() / ".cache" / "perseus-mcp"


def _cache_key(parts: dict[str, Any]) -> str:
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_path(namespace: str, key: str, extension: str = "txt") -> Path:
    return _cache_dir() / namespace / f"{key}.{extension}"


def _memory_cache_get(name: str) -> str | None:
    if not _cache_enabled():
        return None
    cached = _MEMORY_CACHE.get(name)
    if cached is None:
        return None
    timestamp, value = cached
    ttl = _cache_ttl_seconds()
    if ttl and time.time() - timestamp > ttl:
        _MEMORY_CACHE.pop(name, None)
        return None
    return value


def _memory_cache_set(name: str, value: str) -> None:
    if _cache_enabled():
        _MEMORY_CACHE[name] = (time.time(), value)


def _disk_cache_get(path: Path) -> str | None:
    if not _cache_enabled():
        return None
    try:
        if not path.exists():
            return None
        ttl = _cache_ttl_seconds()
        if ttl and time.time() - path.stat().st_mtime > ttl:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        # Another process may clear or replace the optional cache between the
        # existence check, stat, and read. Treat an unavailable entry as a
        # cache miss so the caller can fetch a fresh upstream response.
        return None


def _disk_cache_set(path: Path, value: str) -> None:
    """Write a cache entry atomically.

    PERSEUS_MCP_CACHE_DIR is documented as safe to share across multiple
    local processes (an MCP server plus one or more notebook kernels). A
    plain ``path.write_text(...)`` is not atomic, so two processes writing
    the same cache key around the same time could interleave and leave a
    corrupted file that fails to parse on the next read. Writing to a
    process-unique temporary file in the same directory and then using
    ``os.replace`` (atomic on POSIX and Windows when source/destination are
    on the same volume) avoids that.
    """
    if not _cache_enabled():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp-{os.getpid()}-{time.monotonic_ns()}")
    try:
        tmp_path.write_text(value, encoding="utf-8")
        os.replace(tmp_path, path)
    except (OSError, UnicodeError):
        with suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise


async def _cached_text(
    namespace: str,
    key_parts: dict[str, Any],
    fetcher,
    *,
    extension: str = "xml",
    refresh: bool = False,
) -> str:
    key = _cache_key(key_parts)
    memory_key = f"{namespace}:{key}"
    path = _cache_path(namespace, key, extension)

    if not refresh:
        cached = _memory_cache_get(memory_key)
        if cached is not None:
            return cached
        cached = _disk_cache_get(path)
        if cached is not None:
            _memory_cache_set(memory_key, cached)
            return cached

    value = await fetcher()
    _memory_cache_set(memory_key, value)
    try:
        _disk_cache_set(path, value)
    except (OSError, UnicodeError) as exc:
        warnings.warn(
            f"Could not update optional metadata cache at {path}: {exc}. "
            "Returning the upstream response without disk caching.",
            MetadataCacheWarning,
            stacklevel=2,
        )
    return value


async def _get_capabilities_cached(refresh: bool = False) -> str:
    return await _cached_text(
        "capabilities",
        {"request": "GetCapabilities", "base": CTS_BASE},
        lambda: _cts_request("GetCapabilities"),
        refresh=refresh,
    )


async def _get_scaife_library_catalog_cached(refresh: bool = False) -> str:
    return await _cached_text(
        "scaife_library",
        {"url": SCAIFE_LIBRARY_CATALOG},
        lambda: _get(SCAIFE_LIBRARY_CATALOG),
        extension="json",
        refresh=refresh,
    )


async def _get_valid_references_cached(
    urn: str, level: int | None = None, refresh: bool = False
) -> str:
    params: dict[str, Any] = {}
    if level is not None:
        params["level"] = str(level)
    return await _cached_text(
        "valid_reff",
        {"request": "GetValidReff", "base": CTS_BASE, "urn": urn, **params},
        lambda: _cts_request("GetValidReff", urn=urn, **params),
        refresh=refresh,
    )


def _cache_status() -> str:
    cache_dir = _cache_dir()
    files = [path for path in cache_dir.rglob("*") if path.is_file()] if cache_dir.exists() else []
    return json.dumps(
        {
            "enabled": _cache_enabled(),
            "cache_dir": str(cache_dir),
            "ttl_seconds": _cache_ttl_seconds(),
            "memory_entries": len(_MEMORY_CACHE),
            "disk_files": len(files),
            "disk_bytes": sum(path.stat().st_size for path in files),
        },
        ensure_ascii=False,
        indent=2,
    )


def _remove_readonly_cache_entry(
    function, path: str, error: BaseException
) -> None:
    """Make a protected cache entry writable and retry its removal.

    On Unix, a protected parent directory can prevent even ``chmod`` from
    reaching the failed entry. Restore access to the parent first, then make
    the entry writable and retry the failed removal operation.
    """
    if not isinstance(error, PermissionError):
        raise error

    parent = os.path.dirname(path)
    if parent and parent != path:
        parent_mode = stat.S_IMODE(os.stat(parent, follow_symlinks=False).st_mode)
        os.chmod(
            parent,
            parent_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR,
        )

    path_mode = os.stat(path, follow_symlinks=False).st_mode
    if stat.S_ISDIR(path_mode):
        required_mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
    else:
        required_mode = stat.S_IRUSR | stat.S_IWUSR
    os.chmod(path, stat.S_IMODE(path_mode) | required_mode)

    if function in (os.open, os.scandir):
        _rmtree(path)
        return

    function(path)


def _remove_readonly_cache_entry_legacy(function, path: str, exc_info) -> None:
    """Adapt the Python 3.11 ``onerror`` callback to the ``onexc`` handler."""
    _remove_readonly_cache_entry(function, path, exc_info[1])


def _rmtree(path: str | os.PathLike[str]) -> None:
    """Remove a tree with the supported error callback API."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_remove_readonly_cache_entry)
    else:
        shutil.rmtree(path, onerror=_remove_readonly_cache_entry_legacy)


def _clear_cache() -> str:
    _MEMORY_CACHE.clear()
    cache_dir = _cache_dir()
    removed = cache_dir.exists()
    if removed:
        _rmtree(cache_dir)
    return json.dumps(
        {"cache_dir": str(cache_dir), "memory_entries": 0, "disk_cache_removed": removed},
        ensure_ascii=False,
        indent=2,
    )


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
    normalized = _normalize_space(search_kind).casefold() or "form"
    if normalized not in {"form", "lemma"}:
        raise ValueError("search_kind must be one of: form, lemma")
    return normalized


def _normalize_search_result_format(result_format: str | None) -> str:
    normalized = _normalize_space(result_format).casefold() or "instances"
    if normalized not in {"instances", "passages"}:
        raise ValueError("result_format must be one of: instances, passages")
    return normalized


def _positive_int(value: int, name: str) -> int:
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
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


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
    return _safe_xml_fromstring(capabilities_xml)


def _work_matches_language(work: dict[str, Any], language: str | None) -> bool:
    normalized = _normalize_cts_language(language)
    return normalized is None or work.get("language") == normalized


def _text_matches_query(values: list[str | None], query: str | None) -> bool:
    normalized_query = _normalize_space(query).casefold()
    if not normalized_query:
        return True
    return normalized_query in " ".join(value or "" for value in values).casefold()


def _query_match_rank(values: list[str | None], query: str) -> tuple[int, int]:
    normalized_query = _normalize_space(query).casefold()
    normalized_values = [_normalize_space(value).casefold() for value in values]

    def value_rank(value: str) -> tuple[int, int]:
        if value == normalized_query:
            return (0, len(value))
        if re.match(rf"^{re.escape(normalized_query)}(?:$|\W)", value):
            return (1, len(value))
        if value.startswith(normalized_query):
            return (2, len(value))
        return (3, len(value))

    matches = [value_rank(value) for value in normalized_values if normalized_query in value]
    return min(matches, default=(4, 0))


def _language_from_cts_urn(urn: str | None) -> str | None:
    if not urn:
        return None
    namespace = urn.split(":", 3)[2].casefold() if urn.count(":") >= 3 else ""
    if namespace == "greeklit":
        return "grc"
    if namespace == "latinlit":
        return "lat"
    return None


def _scaife_work_entry(work: dict[str, Any]) -> dict[str, Any]:
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
    query = _normalize_space(author)
    if not query:
        raise ValueError("author must not be empty")

    data = json.loads(catalog_json)
    text_groups = data.get("text_groups", []) if isinstance(data, dict) else []
    normalized_language = _normalize_cts_language(language)
    authors: list[dict[str, Any]] = []

    for text_group in text_groups:
        if not isinstance(text_group, dict):
            continue
        label = _normalize_space(text_group.get("label"))
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
    merged: dict[str, dict[str, Any]] = {}

    def merge_resources(
        existing: list[dict[str, Any]],
        incoming: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
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
    async def from_cts() -> list[dict[str, Any]]:
        capabilities_xml = await _get_capabilities_cached()
        return _matching_author_entries_from_capabilities(
            capabilities_xml, author, language, names_only=names_only
        )

    async def from_scaife() -> list[dict[str, Any]]:
        catalog_json = await _get_scaife_library_catalog_cached()
        return _matching_author_entries_from_scaife_catalog(
            catalog_json, author, language, names_only=names_only
        )

    results = await asyncio.gather(from_cts(), from_scaife(), return_exceptions=True)
    successful = [result for result in results if isinstance(result, list)]
    if not successful:
        raise results[0]

    authors = _merge_author_entries(*successful)
    query = _normalize_space(author)
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
    query = _normalize_space(author)
    if not query:
        raise ValueError("author must not be empty")

    root = _capabilities_root(capabilities_xml)
    authors: list[dict[str, Any]] = []

    for text_group in root.iter():
        if _local_name(text_group.tag).casefold() != "textgroup":
            continue
        entry = _text_group_entry(text_group)
        searchable = entry.get("names", [])
        if not names_only:
            searchable = [entry.get("urn"), *searchable]
        if not _text_matches_query(searchable, query):
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
    return authors


def _list_text_groups_from_capabilities(
    capabilities_xml: str,
    language: str | None = None,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> str:
    limit = _bounded_list_limit(limit)
    offset = _non_negative_int(offset, "offset")
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

    page = text_groups[offset : offset + limit]

    return json.dumps(
        {
            "query": query,
            "language": _normalize_cts_language(language),
            "total_count": len(text_groups),
            "offset": offset,
            "limit": limit,
            "returned_count": len(page),
            "match_count": len(text_groups),
            "has_more": offset + len(page) < len(text_groups),
            "text_groups": page,
        },
        ensure_ascii=False,
        indent=2,
    )


def _author_resources_from_capabilities(
    capabilities_xml: str, author: str, language: str | None = None
) -> str:
    authors = _matching_author_entries_from_capabilities(
        capabilities_xml, author, language
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


def _author_name_matches_response(
    authors: list[dict[str, Any]],
    query: str,
    language: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> str:
    limit = _bounded_list_limit(limit)
    offset = _non_negative_int(offset, "offset")
    total_count = len(authors)
    authors = authors[offset : offset + limit]
    normalized_query = _normalize_space(query).casefold()

    return json.dumps(
        {
            "query": query,
            "language": _normalize_cts_language(language),
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
            "returned_count": len(authors),
            "match_count": total_count,
            "has_more": offset + len(authors) < total_count,
            "authors": [
                {
                    "urn": author.get("urn"),
                    "names": author.get("names", []),
                    "matched_names": [
                        name
                        for name in author.get("names", [])
                        if normalized_query in _normalize_space(name).casefold()
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
            if not _work_matches_language(work, language):
                continue
            searchable = [work.get("urn"), *work.get("titles", [])]
            if not _text_matches_query(searchable, query):
                continue
            matches.append({"author": author, "work": work})

    return json.dumps(
        {
            "query": urn_or_title,
            "language": _normalize_cts_language(language),
            "match_count": len(matches),
            "matches": matches,
        },
        ensure_ascii=False,
        indent=2,
    )


def _passage_plaintext_from_xml(passage_xml: str) -> str:
    root = _safe_xml_fromstring(passage_xml)

    def outermost_texts(names: set[str]) -> list[str]:
        text_parts: list[str] = []

        def visit(element: ET.Element) -> None:
            if _local_name(element.tag) in names:
                text = _element_text(element)
                if text:
                    text_parts.append(text)
                return
            for child in element:
                visit(child)

        visit(root)
        return text_parts

    text_parts = outermost_texts({"l", "p", "ab"})
    if not text_parts:
        text_parts = outermost_texts({"quote"})
    if not text_parts:
        text_parts = outermost_texts({"seg"})

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
        root = _safe_xml_fromstring(response_text)
    except (ET.ParseError, DefusedXmlException):
        return False
    return _local_name(root.tag).casefold() == expected_root.casefold()


def _reference_urns_from_xml(references_xml: str) -> list[str]:
    root = _safe_xml_fromstring(references_xml)
    return [
        _element_text(element)
        for element in root.iter()
        if _local_name(element.tag).casefold() == "urn" and _element_text(element)
    ]


def _valid_references_json(
    references_xml: str,
    urn: str,
    level: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> str:
    limit = _bounded_list_limit(limit)
    offset = _non_negative_int(offset, "offset")
    references = _reference_urns_from_xml(references_xml)
    page = references[offset : offset + limit]
    return json.dumps(
        {
            "urn": urn,
            "level": level,
            "total_count": len(references),
            "offset": offset,
            "limit": limit,
            "returned_count": len(page),
            "has_next": offset + limit < len(references),
            "references": page,
        },
        ensure_ascii=False,
        indent=2,
    )


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


def _urn_scope_values_from_author_entries(authors: list[dict[str, Any]]) -> list[str]:
    prefixes: list[str] = []

    def add(value: str | None) -> None:
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
    urns: list[str] = []

    if isinstance(value, str):
        urns.extend(match.group(0).rstrip(".,;)]}") for match in _CTS_URN_RE.finditer(value))
    elif isinstance(value, dict):
        for item in value.values():
            urns.extend(_extract_cts_urns(item))
    elif isinstance(value, list):
        for item in value:
            urns.extend(_extract_cts_urns(item))

    return urns


def _urn_matches_scope(urn: str, scope_urns: list[str]) -> bool:
    for scope_urn in scope_urns:
        if (
            urn == scope_urn
            or urn.startswith(f"{scope_urn}.")
            or urn.startswith(f"{scope_urn}:")
        ):
            return True
    return False


def _result_matches_author_scope(result: Any, scope_urns: list[str]) -> bool:
    return any(_urn_matches_scope(urn, scope_urns) for urn in _extract_cts_urns(result))


def _normalize_query_for_search(
    query: str,
    language: str = "greek",
    query_format: str = "auto",
    preserve_operators: bool = False,
) -> str:
    if not _normalize_space(query):
        raise ValueError("query must not be empty")
    lang_code = _normalize_search_language(language)
    if preserve_operators:
        return unicodedata.normalize("NFC", query)
    if lang_code == "gr":
        return _normalize_greek_query(query, query_format)
    return query


def _quote_urn_path_segment(urn: str) -> str:
    """Percent-encode a URN for safe use as a single URL path segment.

    CTS URNs legitimately contain colons and periods, so those are left
    unescaped for readability; everything else (spaces, '#', '?', '%',
    non-ASCII characters, etc.) is encoded so the value cannot truncate the
    URL, inject query parameters, or otherwise change the request target.
    """
    return quote(urn, safe=":.")


def _scaife_library_url(urn: str) -> str:
    return f"{SCAIFE_LIBRARY.rstrip('/')}/{_quote_urn_path_segment(urn)}/json/"


def _scaife_passage_json_url(urn: str) -> str:
    return f"{SCAIFE_LIBRARY.rstrip('/')}/passage/{_quote_urn_path_segment(urn)}/json/"


def _scaife_passage_text_url(urn: str) -> str:
    return f"{SCAIFE_LIBRARY.rstrip('/')}/passage/{_quote_urn_path_segment(urn)}/text/"


def _single_author_text_group_urn(authors: list[dict[str, Any]]) -> str | None:
    urns = [author.get("urn") for author in authors if author.get("urn")]
    return urns[0] if len(urns) == 1 else None


def _add_author_scope_metadata(
    response_text: str,
    author: str,
    authors: list[dict[str, Any]],
    text_group: str,
) -> str:
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
    data = json.loads(response_text)
    scope_urns = _urn_scope_values_from_author_entries(authors)

    if isinstance(data, dict) and isinstance(data.get("results"), list):
        results = data["results"]
        filtered_results = [
            result for result in results if _result_matches_author_scope(result, scope_urns)
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
            result for result in data if _result_matches_author_scope(result, scope_urns)
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

    return json.dumps(
        {
            "results": [],
            "author_scope": {
                "query": author,
                "match_count": len(authors),
                "urns": scope_urns,
                "note": "Scaife returned an unexpected JSON shape; no results could be filtered.",
            },
        },
        ensure_ascii=False,
        indent=2,
    )


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
    return await _get_valid_references_cached(urn, level)


@mcp.tool
async def get_valid_references_json(
    urn: str, level: int | None = None, limit: int = 100, offset: int = 0
) -> str:
    """Get valid citation references as paged JSON instead of raw CTS XML.

    `limit` must be between 1 and 500.
    """
    references_xml = await _get_valid_references_cached(urn, level)
    return _valid_references_json(references_xml, urn, level, limit, offset)


@mcp.tool
async def count_valid_references(urn: str, level: int | None = None) -> str:
    """Count valid citation references without returning the full reference list."""
    references_xml = await _get_valid_references_cached(urn, level)
    references = _reference_urns_from_xml(references_xml)
    return json.dumps(
        {"urn": urn, "level": level, "total_count": len(references)},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool
async def get_capabilities() -> str:
    """Get the list of available texts and editions from Perseus CTS."""
    return await _get_capabilities_cached()


@mcp.tool
async def get_cache_status() -> str:
    """Get local metadata cache status."""
    return _cache_status()


@mcp.tool
async def refresh_metadata_cache() -> str:
    """Refresh cached CTS and Scaife library metadata."""
    capabilities_xml, scaife_catalog_json = await asyncio.gather(
        _get_capabilities_cached(refresh=True),
        _get_scaife_library_catalog_cached(refresh=True),
    )
    return json.dumps(
        {
            "refreshed": True,
            "cache": json.loads(_cache_status()),
            "capabilities_bytes": len(capabilities_xml.encode("utf-8")),
            "scaife_catalog_bytes": len(scaife_catalog_json.encode("utf-8")),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool
async def clear_metadata_cache() -> str:
    """Clear local metadata cache files and in-memory cache entries."""
    return _clear_cache()


@mcp.tool
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
    capabilities_xml = await _get_capabilities_cached()
    return _list_text_groups_from_capabilities(
        capabilities_xml, language, query, limit, offset
    )


@mcp.tool
async def get_author_resources(author: str, language: str | None = None) -> str:
    """List CTS works/editions/translations for an author name or textgroup URN.

    Examples:
    - author: "Homer"
    - author: "tlg0012"
    - author: "urn:cts:greekLit:tlg0012"
    """
    capabilities_xml = await _get_capabilities_cached()
    return _author_resources_from_capabilities(capabilities_xml, author, language)


@mcp.tool
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
    if not _normalize_space(query):
        raise ValueError("query must not be empty")
    authors = await _resolve_author_entries(query, language, names_only=True)
    return _author_name_matches_response(authors, query, language, limit, offset)


@mcp.tool
async def get_work_resources(
    urn_or_title: str, language: str | None = None
) -> str:
    """List editions/translations/resources for a matching work URN or title.

    Optional `language` accepts values such as "greek", "grc", "latin", or
    "lat" and filters by the original work language.

    Examples:
    - urn_or_title: "urn:cts:greekLit:tlg0012.tlg001"
    - urn_or_title: "Iliad"
    """
    capabilities_xml = await _get_capabilities_cached()
    return _work_resources_from_capabilities(
        capabilities_xml, urn_or_title, language
    )


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

    references_xml = await _get_valid_references_cached(urn)
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
    references_xml = await _get_valid_references_cached(work_urn)
    return _prev_next_xml(urn, _reference_urns_from_xml(references_xml))


@mcp.tool
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
    normalized_search_kind = _normalize_search_kind(search_kind)
    normalized_query = _normalize_query_for_search(
        query, language, query_format, preserve_operators
    )
    normalized_page_num = _positive_int(page_num, "page_num")
    normalized_result_format = _normalize_search_result_format(result_format)

    authors: list[dict[str, Any]] = []
    resolved_author_text_group: str | None = None
    if author is not None and _normalize_space(author):
        authors = await _resolve_author_entries(author, language)
        resolved_author_text_group = _single_author_text_group_urn(authors)

    effective_text_group = _normalize_space(text_group) or None
    effective_work = _normalize_space(work) or None
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

    response_text = await _get(
        SCAIFE_SEARCH,
        params=params,
    )
    if author is None or not _normalize_space(author):
        return response_text

    if effective_text_group and effective_text_group == resolved_author_text_group:
        return _add_author_scope_metadata(
            response_text, author, authors, effective_text_group
        )

    return _filter_scaife_search_response_by_author(response_text, author, authors)


@mcp.tool
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
    normalized_query = _normalize_query_for_search(
        query, language, query_format, preserve_operators
    )
    return await _get(
        SCAIFE_SEARCH,
        params={
            "q": normalized_query,
            "kind": _normalize_search_kind(search_kind),
            "type": "reader",
            "text": text_urn,
            "size": _bounded_list_limit(size, "size"),
            "offset": _non_negative_int(offset, "offset"),
            "fields": "",
        },
    )


@mcp.tool
async def get_passage_highlights(
    query: str,
    passage_urn: str,
    language: str = "greek",
    query_format: str = "auto",
    search_kind: str = "form",
    preserve_operators: bool = False,
) -> str:
    """Get Scaife token highlight positions for a query within one passage."""
    normalized_query = _normalize_query_for_search(
        query, language, query_format, preserve_operators
    )
    return await _get(
        SCAIFE_SEARCH,
        params={
            "q": normalized_query,
            "kind": _normalize_search_kind(search_kind),
            "type": "reader",
            "passage": passage_urn,
            "size": 1,
            "fields": "highlights",
        },
    )


@mcp.tool
async def get_scaife_library_metadata(urn: str) -> str:
    """Get Scaife JSON metadata for a textgroup, work, edition, or translation URN."""
    return await _get(_scaife_library_url(urn))


@mcp.tool
async def get_scaife_passage_json(urn: str) -> str:
    """Get Scaife JSON passage metadata/content for a passage URN."""
    return await _get(_scaife_passage_json_url(urn))


@mcp.tool
async def get_scaife_passage_text(urn: str) -> str:
    """Get Scaife plaintext for a passage URN."""
    return await _get(_scaife_passage_text_url(urn))


def main() -> None:
    """Run the Perseus MCP server over the default stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
