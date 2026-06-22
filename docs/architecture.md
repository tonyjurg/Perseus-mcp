---
title: Architecture
description: Internal design, request flow, and extension points for the Perseus MCP server.
permalink: /architecture/
---

# Perseus MCP Server: How It Works

This document explains internal design, request flow, and extension points for the `perseus` MCP server.

## High-Level Design

The server is a single-process Python MCP tool host built with FastMCP:

- **Implementation**: `src/perseus_mcp/server.py`
- **Installed entry points**: `perseus-mcp` and `python -m perseus_mcp`
- **MCP host**: `mcp = FastMCP("perseus")`
- **Transport/runtime**: provided by FastMCP when calling `mcp.run()`

All tool functions are async and return text payloads. Many are raw upstream
responses, while discovery, plaintext, and navigation fallback tools shape
responses locally.

## Architecture Goals and Tradeoffs

This project is intentionally small and adapter-like. It does not attempt to
mirror or warehouse Perseus data locally. Instead, it exposes a stable MCP tool
surface over public Perseus/Scaife HTTP services so an LLM client can discover,
search, retrieve, and navigate Greek texts on demand.

The main design goals are:

1. **LLM-client portability**: any MCP-capable application should be able to run
   the same local command and receive the same tool names, descriptions, input
   schemas, and text outputs.
2. **Scholarly fidelity**: raw CTS XML and Scaife JSON remain available for core
   retrieval and search operations so users can inspect upstream data rather
   than a lossy local rewrite. Convenience helpers such as
   `get_passage_plaintext`, `get_author_resources`, and navigation fallbacks are
   added where they reduce repetitive parsing or compensate for malformed
   upstream responses.
3. **Low operational burden**: the MCP server itself requires no database,
   indexing job, API key, or background service. A user installs Python
   dependencies and runs the MCP server command from their client. Optional
   client-side LLM adapters, such as the OpenRouter notebook, have their own
   provider credentials and install notebook-only helpers such as
   `python-dotenv` in their setup cells.
4. **Readable extension path**: adding another CTS operation should be a small
   tool wrapper around `_cts_request(...)`, making the implementation easy to
   audit for classicists, students, and developers.

The tradeoff is that availability and latency depend on the upstream Perseus and
Scaife services. The server also returns mostly text payloads instead of a fully
normalized domain model; that preserves source fidelity but means some clients
will parse XML/JSON in their own workflow.

## Why FastMCP?

FastMCP is used because it keeps this server close to the conceptual model of
MCP: typed Python functions become MCP tools. For this repository, that choice
provides several practical benefits:

- **Minimal boilerplate**: `@mcp.tool` decorates an async Python function and
  exposes it as a tool, so each tool definition stays near the CTS or Scaife
  request it performs.
- **Type-hint driven schemas**: function signatures such as
  `get_valid_references(urn: str, level: int | None = None)` describe the input
  contract in code and are surfaced to MCP clients.
- **Standard local transport for many LLM clients**: clients such as Cursor,
  Claude Desktop, and MCP Inspector can launch the same `uv run perseus-mcp`
  command over stdio. The server does not need a custom HTTP wrapper per LLM.
- **Async-friendly network calls**: the tools perform remote HTTP requests, so
  an async server and `httpx.AsyncClient` fit the workload naturally.
- **Notebook/test ergonomics**: the MCP examples can connect with
  `fastmcp.Client(mcp)` in-process, demonstrating the real MCP tool interface
  without requiring a separate subprocess during exploration.

A lower-level MCP implementation would give more manual control over protocol
details, but it would add boilerplate that is not central to the research task.
A standalone REST API would be familiar to web developers, but LLM applications
would still need an MCP adapter to expose tools. FastMCP is therefore the
smallest abstraction that serves the core user story: make Perseus research
tools available to the LLM of the user's choice.

## External Services

### 1) Perseus CTS endpoint

Base URL:

- `https://www.perseus.tufts.edu/hopper/CTS`

CTS tools call this endpoint with a query parameter named `request`, plus optional parameters such as `urn` and `level`.

### 2) Scaife search endpoint

Base URL:

- `https://scaife.perseus.org/search/json/`

`search_perseus` normalizes Greek Unicode/Beta Code input, then calls this
endpoint with `q`, `kind`, `type=library`, and `page_num=1`. The `kind`
parameter is exposed as `search_kind` and may be `form` or `lemma`. The
`language` argument determines whether Greek query normalization is applied; it
is not currently sent as a Scaife language filter.

## Core HTTP Helpers

### `_get(url, params=None, timeout=20.0)`

- Lazily creates and reuses one process-wide `httpx.AsyncClient`
- Recreates the client if the active event loop changes or the client is closed
- Uses timeout 20s by default and follows redirects
- Executes GET request
- Raises for non-2xx status (`response.raise_for_status()`)
- Returns `response.text`

`aclose_http_client()` is available to embeddings and tests that need explicit
shutdown. Normal stdio operation keeps the pooled client alive for the server
process so sequential calls can reuse TCP/TLS connections.

### `_cts_request(request, urn=None, **extra_params)`

- Builds CTS query params in one place
- Adds `request=<CTS operation>` and optional `urn`
- Forwards to `_get(CTS_BASE, params=...)`

This abstraction keeps tool methods concise and consistent.

## Tool Behavior

All tools are decorated with `@mcp.tool` and become MCP-exposed functions.

- `get_passage(urn)` → CTS `GetPassage`
- `get_passage_plus(urn)` → CTS `GetPassagePlus`
- `get_passage_plaintext(urn)` → CTS `GetPassage`, then local XML text extraction
- `get_valid_references(urn, level=None)` → CTS `GetValidReff`, optional `level`
- `get_valid_references_json(urn, level=None, limit=100, offset=0)` → cached CTS `GetValidReff`, then local reference parsing and paging with a 1–500 limit
- `count_valid_references(urn, level=None)` → cached CTS `GetValidReff`, then local reference counting
- `get_capabilities()` → CTS `GetCapabilities`
- `get_cache_status()` → local metadata cache status
- `refresh_metadata_cache()` → refresh cached CTS capabilities and Scaife library catalog
- `clear_metadata_cache()` → clear memory and disk metadata cache entries
- `list_text_groups(language=None, query=None, limit=100)` → CTS `GetCapabilities`, then local textgroup/work filtering and JSON shaping with a 1–500 limit
- `get_author_resources(author, language=None)` → CTS `GetCapabilities`, then local textgroup filtering and JSON shaping
- `find_author_names(query, language=None, limit=100)` → cached CTS `GetCapabilities` plus the cached Scaife library catalog, merged by textgroup URN and locally matched against textgroup name fields only with a 1–500 limit
- `get_work_resources(urn_or_title, language=None)` → CTS `GetCapabilities`, then local work/language filtering and JSON shaping
- `get_label(urn)` → CTS `GetLabel`
- `get_first_urn(urn)` → CTS `GetFirstUrn`, with a `GetValidReff` fallback when the upstream response is malformed
- `get_prev_next_urn(urn)` → CTS `GetPrevNextUrn`, with a `GetValidReff` fallback when the upstream response is malformed
- `search_perseus(query, language="greek", query_format="auto", author=None, search_kind="form", preserve_operators=False, page_num=1, text_group=None, work=None, result_format="instances")` → Scaife JSON search API with normalized Greek query text, form/lemma search, optional operator preservation, pagination, server-side textgroup/work scoping, and optional author-scope filtering
- `search_within_text(query, text_urn, ...)` → Scaife reader search API scoped to one text/edition URN
- `get_passage_highlights(query, passage_urn, ...)` → Scaife reader search API with `fields=highlights`
- `get_scaife_library_metadata(urn)` → Scaife `/library/<urn>/json/`
- `get_scaife_passage_json(urn)` → Scaife `/library/passage/<urn>/json/`
- `get_scaife_passage_text(urn)` → Scaife `/library/passage/<urn>/text/`

Scaife library and passage helpers percent-encode the caller-supplied URN as
one URL path segment. CTS separators such as `:` and `.` remain readable, while
reserved characters cannot become fragments, query strings, or extra paths.

### Local metadata cache

CTS `GetCapabilities` and `GetValidReff` responses are stable enough to cache
for local development and are large enough that repeated live requests make the
tools feel slow. The server caches those responses in memory and on disk under
`.cache/perseus-mcp` by default. Cache keys include the request type, CTS base
URL, URN, and level. Environment variables control the behavior:

- `PERSEUS_MCP_CACHE_DIR`
- `PERSEUS_MCP_CACHE_TTL_SECONDS`
- `PERSEUS_MCP_DISABLE_CACHE`

Cache clearing uses a `shutil.rmtree` permission handler that makes protected
entries writable and retries removal. This handles the common Windows/OneDrive
case where synchronized cache directories are read-only reparse points.

The default disk cache path is relative to `Path.cwd()` for the running Python
process. A notebook kernel launched from `examples/` and an MCP server launched
from the repository root are separate Python processes, so each has its own
in-memory cache and, unless `PERSEUS_MCP_CACHE_DIR` is set, a different disk
cache root. This does not create duplicate MCP server instances by itself; it
only affects where cache files are read and written. Use an absolute
`PERSEUS_MCP_CACHE_DIR` when multiple local entry points should share one disk
cache.

Disk cache updates use a process-qualified temporary sibling followed by
`os.replace(...)`. Keeping the temporary file on the same volume makes the
final replacement atomic on supported Windows and POSIX filesystems and avoids
readers observing partial writes.

### Author resource filtering

`get_author_resources(author)` is a convenience layer over CTS `GetCapabilities`.
It fetches the capabilities XML, finds matching `TextGroup` or `textgroup`
entries by case-insensitive author/group name or textgroup URN fragment, and
returns JSON instead of raw XML.
Each matched author entry includes the textgroup URN, names, works, work languages, titles, editions, and translations so clients can discover resource URNs without manually parsing the full capabilities response.
`find_author_names(query)` merges CTS and Scaife textgroups by URN, searches
only their author/textgroup name fields, and returns a narrower response for
partial name discovery. The resolver tolerates either inventory being
unavailable.

When `search_perseus(..., author=...)` is used, the server first performs the
same merged author resolution. If the author resolves to exactly one textgroup
and no explicit `text_group` or `work` is supplied,
the textgroup is sent to Scaife as a server-side `text_group` filter. Ambiguous
author matches still fall back to local post-filtering of the current Scaife
result page by CTS URN prefixes.

`search_kind="lemma"` sends `kind=lemma` to Scaife; the default `form` sends
`kind=form`. `preserve_operators=True` bypasses Beta Code auto-detection and
NFC-normalizes the query directly, preserving Scaife operator characters such
as quotes, `-`, `|`, `*`, and `~`.

### Navigation fallbacks

The live Perseus CTS service may return malformed HTML for `GetFirstUrn` and
`GetPrevNextUrn`. The server first attempts those CTS operations directly. If
the response is not well-formed XML with the expected root element, it requests
`GetValidReff` and constructs a small well-formed XML response from the ordered
reference URNs. For `get_prev_next_urn`, the fallback derives the work or
edition URN by removing the passage component after the final colon.

This fallback preserves the tool contract but is locally shaped output rather
than a verbatim upstream response.

All XML received from Perseus or Scaife is parsed with `defusedxml`, which
rejects DTD and custom-entity constructs before local traversal. The standard
library `ElementTree` API remains in use only for constructing trusted fallback
XML locally.

### Greek query normalization

Before Greek searches are sent to Scaife, `search_perseus` normalizes input with `_normalize_greek_query(...)`.
Unicode Greek is NFC-normalized, while detected or forced Beta Code is transliterated to Unicode Greek, including common breathings, accents, diaeresis, iota subscript, uppercase markers, and final sigma handling.
Search-language input is restricted to the documented Greek and Latin aliases;
blank input defaults to Greek and unrecognized values raise `ValueError`.
`query_format` may be `auto`, `betacode`, or `unicode`; `auto` detects explicit Beta Code marks and short unaccented Beta Code-like queries.
Operator searches should use `preserve_operators=True`, because characters such
as `+`, `|`, and `*` also have Beta Code meanings.

### Unicode normalization findings

The Greek search path normalizes outgoing Greek queries to NFC because Perseus Greek text samples use composed Unicode for polytonic Greek.
For example, canonical Iliad text such as `μῆνιν ἄειδε θεὰ ... Ἀχιλῆος` contains precomposed code points like `U+1FC6 GREEK SMALL LETTER ETA WITH PERISPOMENI`, `U+1F04 GREEK SMALL LETTER ALPHA WITH PSILI AND OXIA`, and `U+1F08 GREEK CAPITAL LETTER ALPHA WITH PSILI`.
A local Unicode check of that sample reports NFC-normalized text and not NFD-normalized text, so Beta Code conversion should emit composed Unicode Greek before search requests are sent to Scaife.

You can re-check a sample manually from the project root with:

```bash
python - <<'PY'
import unicodedata

sample = "μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος"
print("NFC", unicodedata.is_normalized("NFC", sample))
print("NFD", unicodedata.is_normalized("NFD", sample))
for character in sample:
    if character.strip():
        print(f"U+{ord(character):04X}", unicodedata.name(character, "UNKNOWN"))
PY
```

## Error Model

Errors are not swallowed:

- HTTP errors from upstream propagate as exceptions.
- Unsafe DTD or entity declarations in upstream XML are rejected rather than
  expanded.
- A Perseus `429 Too Many Requests` response therefore reaches the client as an
  `httpx.HTTPStatusError`. The current HTTP helper does not implement automatic
  retry, exponential backoff, or `Retry-After` handling. Callers running passage
  loops should limit concurrency, add pacing, and retry later rather than
  immediately repeating the failed request.
- Some HTTP 200 responses can still contain invalid or unexpected content; the
  first/previous/next navigation tools detect the known malformed-HTML case.
- This is useful during research/dev because failures are explicit.

Potential future enhancement:

- Add user-friendly error wrapping with structured tool error messages.

## Data Contract

Current return type is **text payloads** for mixed raw and locally shaped data:

- CTS endpoints often return XML/text payloads
- Scaife search typically returns JSON text
- selected helper tools return JSON strings created locally from CTS XML, for
  example author/work discovery results
- navigation fallbacks return XML strings created locally from ordered
  `GetValidReff` results

This shape is deliberate for mixed human/LLM use. Raw XML or JSON lets a user
verify exactly what came from Perseus/Scaife, while helper tools provide a
friendlier path for common tasks where full CTS XML is too verbose. In an LLM
client, the recommended pattern is to ask for discovery JSON first, choose a URN,
then fetch passage text or raw XML as needed.

Potential future enhancement:

- Parse XML/JSON and return normalized structured objects for easier downstream agent consumption.

## Extending the Server

To add a new CTS operation:

1. Add a new async function with `@mcp.tool`.
2. Call `_cts_request("<OperationName>", urn=..., ...)`.
3. Document it in `README.md` and `docs/enduser.md`.

To add a non-CTS endpoint:

1. Add constants for base URL(s).
2. Build a thin tool function that calls `_get(...)`.
3. Decide whether to return raw payload or normalized output.

## Operational Notes

- Single-file implementation minimizes startup and maintenance overhead.
- Async I/O is suitable for network-bound calls and concurrent tool usage.
- Stable CTS metadata is cached locally in memory and on disk; passage,
  search, and Scaife reader calls still go to upstream services on demand.

