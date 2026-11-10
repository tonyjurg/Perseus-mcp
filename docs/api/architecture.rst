Modules and compatibility
=========================

Existing notebooks continue to use::

    from perseus_mcp import server
    from fastmcp import Client

    client = Client(server.mcp)

All 23 tool names, argument defaults, descriptions, return formats, and the
``perseus-mcp`` / ``python -m perseus_mcp`` entry points remain unchanged.
Direct calls such as ``await server.get_passage(urn)`` and the notebook's
``server._normalize_query_for_search(...)`` helper still work.

Responsibilities
----------------

* ``server`` preserves the old import surface and validates startup settings.
* ``_app`` owns the single FastMCP instance and the tool error adapter.
* ``http`` owns the shared HTTP client, streaming limits, and transport errors.
* ``cache`` owns memory/disk entries, expiry, atomic writes, and cache removal.
* ``cts`` requests and parses CTS XML and constructs navigation fallback XML.
* ``scaife`` builds URLs, caches the catalogue, and filters search results.
* ``greek`` handles Beta Code and Unicode search normalization.
* ``discovery`` parses and merges author/work inventories.
* ``_common`` normalizes XML text, languages, and pagination arguments.
* ``upstream`` validates payloads and defines safe errors and retry hints.
* ``tools`` contains the async MCP entry points grouped by responsibility.

Implementation modules import their dependencies directly; none imports
``server``. Importing ``server`` loads the tool modules, which register with the
shared application once under normal Python import semantics. Importing or
documenting the package starts no transport and fetches no upstream data.

Compatibility details
---------------------

The facade forwards moved attributes to their owning module, including writes
used by existing notebook/test monkeypatches. HTTP client and cache state have
one owner, so ``server._HTTP_CLIENT`` reflects client creation and cleanup even
when the operation was performed through ``perseus_mcp.http``.

Internal dependencies are accessed through their owning modules. The explicit ``__all__`` lists
identify historical names re-exported by the facade. Private helpers remain
available for compatibility but are implementation details. Function
``__module__`` values now identify their implementation modules; source inspection reflects those implementation paths.

Cache fetchers must return already validated text (production fetchers use
``http._get``). ``cache._cached_text`` runs ``disk_validator`` only for untrusted
disk loads; validated memory entries and fresh fetches avoid repeated parsing.
