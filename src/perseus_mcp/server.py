"""Backward-compatible entry point for notebooks, direct Python calls, and stdio MCP.

Implementation lives in the focused modules and :mod:`perseus_mcp.tools`.
Legacy attributes (including private test/embedding hooks) forward reads and
writes to their owning module so there is only one HTTP client and cache.
New internal code imports the owning modules, never this compatibility facade.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import shutil
import stat
import sys
import time
import unicodedata
import warnings
import xml.etree.ElementTree as ET
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from copy import deepcopy
from functools import partial, wraps
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import quote

import httpx
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring as _safe_xml_fromstring
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from . import _app, _common
from . import cache as _cache
from . import cts as _cts
from . import discovery as _discovery
from . import greek as _greek
from . import http as _http
from . import scaife as _scaife
from . import upstream as _upstream
from .tools import cache as _tools_cache
from .tools import cts as _tools_cts
from .tools import discovery as _tools_discovery
from .tools import scaife as _tools_scaife
from .tools import search as _tools_search

_MODULES = (
    _app,
    _cts,
    _scaife,
    _cache,
    _common,
    _greek,
    _http,
    _discovery,
    _tools_cts,
    _tools_cache,
    _tools_discovery,
    _tools_search,
    _tools_scaife,
)
_OWNERS = {name: module for module in _MODULES for name in module.__all__}
_OWNERS.update(
    {
        name: _upstream
        for name in [
            "UpstreamFailure",
            "parse_retry_after",
            "reject_challenge",
            "validate_catalogue",
            "validate_cts",
            "validate_metadata",
            "validate_passage_json",
            "validate_retry_policy",
            "validate_search",
            "validate_text",
        ]
    }
)
globals().update({name: getattr(module, name) for name, module in _OWNERS.items()})
__all__ = [
    "ET",
    "Any",
    "Callable",
    "DefusedXmlException",
    "FastMCP",
    "Path",
    "ToolError",
    "_safe_xml_fromstring",
    "asynccontextmanager",
    "asyncio",
    "deepcopy",
    "hashlib",
    "httpx",
    "json",
    "main",
    "math",
    "os",
    "partial",
    "quote",
    "re",
    "shutil",
    "stat",
    "suppress",
    "sys",
    "time",
    "unicodedata",
    "warnings",
    "wraps",
]
__all__ += list(_OWNERS)


class _ServerModule(ModuleType):
    """Forward legacy attribute access to the single authoritative implementation."""

    def __getattribute__(self, name):
        """Read moved names from their owner, including reassigned client state."""
        owners = super().__getattribute__("_OWNERS")
        if name in owners:
            return getattr(owners[name], name)
        return super().__getattribute__(name)

    def __setattr__(self, name, value):
        """Keep legacy monkeypatches and embedding assignments effective."""
        owners = super().__getattribute__("_OWNERS")
        if name in owners:
            setattr(owners[name], name, value)
        super().__setattr__(name, value)


def main() -> None:
    """Validate configuration and run the shared MCP server over stdio."""
    _upstream.validate_retry_policy()
    _http._max_response_bytes()
    _http._body_timeout_seconds()
    _app.mcp.run()


sys.modules[__name__].__class__ = _ServerModule

if __name__ == "__main__":
    main()
