"""Expose Scaife metadata and passage representations as MCP tools."""

from __future__ import annotations

from .. import _app
from .. import http as _http
from .. import scaife as _scaife
from .. import upstream as _upstream

__all__ = [
    "get_scaife_library_metadata",
    "get_scaife_passage_json",
    "get_scaife_passage_text",
]


@_app._upstream_tool
async def get_scaife_library_metadata(urn: str) -> str:
    """Get Scaife JSON metadata for a textgroup, work, edition, or translation URN."""
    return await _http._get(
        _scaife._scaife_library_url(urn),
        validator=_upstream.validate_metadata,
    )


@_app._upstream_tool
async def get_scaife_passage_json(urn: str) -> str:
    """Get Scaife JSON passage metadata/content for a passage URN."""
    return await _http._get(
        _scaife._scaife_passage_json_url(urn),
        validator=_upstream.validate_passage_json,
    )


@_app._upstream_tool
async def get_scaife_passage_text(urn: str) -> str:
    """Get Scaife plaintext for a passage URN."""
    return await _http._get(
        _scaife._scaife_passage_text_url(urn),
        validator=_upstream.validate_text,
    )
