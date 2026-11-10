"""Store validated metadata in memory and on disk with expiry and atomic writes."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import time
import warnings
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from . import _common
from . import upstream as _upstream

__all__ = [
    "DEFAULT_CACHE_TTL_SECONDS",
    "_MEMORY_CACHE",
    "MetadataCacheWarning",
    "_cache_dir",
    "_cache_enabled",
    "_cache_key",
    "_cache_path",
    "_cache_status",
    "_cache_ttl_seconds",
    "_cached_text",
    "_clear_cache",
    "_disk_cache_get",
    "_disk_cache_set",
    "_memory_cache_get",
    "_memory_cache_set",
    "_remove_readonly_cache_entry",
    "_remove_readonly_cache_entry_legacy",
    "_rmtree",
]


DEFAULT_CACHE_TTL_SECONDS = 24 * 60 * 60


_MEMORY_CACHE: dict[str, tuple[float, str]] = {}


class MetadataCacheWarning(UserWarning):
    """Warn that the optional metadata cache could not be updated."""


def _cache_enabled() -> bool:
    """Return whether the environment permits metadata caching."""
    value = _common._normalize_space(
        os.environ.get("PERSEUS_MCP_DISABLE_CACHE")
    ).casefold()
    return value not in {"1", "true", "yes", "on"}


def _cache_ttl_seconds() -> int:
    """Read the cache lifetime in seconds; zero disables expiry, not caching."""
    value = _common._normalize_space(os.environ.get("PERSEUS_MCP_CACHE_TTL_SECONDS"))
    if not value:
        return DEFAULT_CACHE_TTL_SECONDS
    try:
        ttl = int(value)
    except ValueError as exc:
        raise ValueError("PERSEUS_MCP_CACHE_TTL_SECONDS must be an integer") from exc
    return max(0, ttl)


def _cache_dir() -> Path:
    """Resolve the configured cache directory, defaulting to the working directory."""
    configured = _common._normalize_space(os.environ.get("PERSEUS_MCP_CACHE_DIR"))
    if configured:
        return Path(configured).expanduser()
    return Path.cwd() / ".cache" / "perseus-mcp"


def _cache_key(parts: dict[str, Any]) -> str:
    """Hash a canonical JSON representation of request parameters for a disk-safe key."""
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_path(namespace: str, key: str, extension: str = "txt") -> Path:
    """Locate an entry within its cache namespace without creating directories."""
    return _cache_dir() / namespace / f"{key}.{extension}"


def _memory_cache_get(name: str) -> str | None:
    """Return an unexpired, previously validated memory entry or None."""
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
    """Store validated text with its insertion time when caching is enabled."""
    if _cache_enabled():
        _MEMORY_CACHE[name] = (time.time(), value)


def _disk_cache_get(path: Path) -> str | None:
    """Read unexpired UTF-8 text; return None on a miss or unreadable entry."""
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
    disk_validator: Callable[[str], None] = _upstream.validate_text,
) -> str:
    """Cache validated fetch results; validate untrusted disk entries on load.

    disk_validator runs only on disk loads, not memory hits or fresh fetches.
    Fetchers must validate before returning (the production fetchers use _get).
    Memory entries have already passed upstream or disk validation.
    """
    key = _cache_key(key_parts)
    memory_key = f"{namespace}:{key}"
    path = _cache_path(namespace, key, extension)

    if not refresh:
        cached = _memory_cache_get(memory_key)
        if cached is not None:
            return cached
        cached = _disk_cache_get(path)
        if cached is not None:
            try:
                disk_validator(cached)
            except _upstream.UpstreamFailure as exc:
                _MEMORY_CACHE.pop(memory_key, None)
                with suppress(OSError):
                    path.unlink(missing_ok=True)
                warnings.warn(
                    f"Ignoring invalid {namespace} cache entry ({exc.code}).",
                    MetadataCacheWarning,
                    stacklevel=2,
                )
            else:
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


def _cache_status() -> str:
    """Serialize cache configuration, entry counts, and disk usage as JSON."""
    cache_dir = _cache_dir()
    files = (
        [path for path in cache_dir.rglob("*") if path.is_file()]
        if cache_dir.exists()
        else []
    )
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


def _remove_readonly_cache_entry(function, path: str, error: BaseException) -> None:
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
    """Clear memory and remove the configured disk cache; return a JSON summary."""
    _MEMORY_CACHE.clear()
    cache_dir = _cache_dir()
    removed = cache_dir.exists()
    if removed:
        _rmtree(cache_dir)
    return json.dumps(
        {
            "cache_dir": str(cache_dir),
            "memory_entries": 0,
            "disk_cache_removed": removed,
        },
        ensure_ascii=False,
        indent=2,
    )
