"""Expose metadata cache inspection, refresh, and removal as MCP tools."""

from __future__ import annotations

import asyncio
import json

from .. import _app
from .. import cache as _cache
from .. import cts as _cts
from .. import scaife as _scaife

__all__ = ["clear_metadata_cache", "get_cache_status", "refresh_metadata_cache"]


@_app._upstream_tool
async def get_cache_status() -> str:
    """Get local metadata cache status."""
    return _cache._cache_status()


@_app._upstream_tool
async def refresh_metadata_cache() -> str:
    """Refresh cached CTS and Scaife library metadata."""
    capabilities_xml, scaife_catalog_json = await asyncio.gather(
        _cts._get_capabilities_cached(refresh=True),
        _scaife._get_scaife_library_catalog_cached(refresh=True),
    )
    return json.dumps(
        {
            "refreshed": True,
            "cache": json.loads(_cache._cache_status()),
            "capabilities_bytes": len(capabilities_xml.encode("utf-8")),
            "scaife_catalog_bytes": len(scaife_catalog_json.encode("utf-8")),
        },
        ensure_ascii=False,
        indent=2,
    )


@_app._upstream_tool
async def clear_metadata_cache() -> str:
    """Clear local metadata cache files and in-memory cache entries."""
    return _cache._clear_cache()
