---
title: End-User Guide
description: Install, run, and use the Perseus MCP server in MCP-capable clients.
permalink: /enduser/
---

# Perseus MCP Server: End-User Guide

This guide explains how to install, run, and use the `perseus` MCP server in tools like Cursor or Claude Desktop.

## What You Get

The server provides tools for Greek text research against Perseus CTS and Scaife search. It is designed as a local MCP bridge: your LLM client starts this server, discovers its tools, and can then call those tools with structured arguments instead of relying on ad hoc web browsing or copied URLs.

Use it when you want an LLM to help with tasks such as:

- finding Perseus CTS URNs for authors and works;
- retrieving Greek passages by citation;
- moving to neighboring passages;
- searching Greek text with Unicode Greek or Beta Code input;
- keeping the upstream Perseus/Scaife response available for verification.

The current implementation exposes twenty-three text-returning tools:

- `get_passage(urn)`
- `get_passage_plus(urn)`
- `get_passage_plaintext(urn)`
- `get_valid_references(urn, level=None)`
- `get_valid_references_json(urn, level=None, limit=100, offset=0)`
- `count_valid_references(urn, level=None)`
- `get_capabilities()`
- `get_cache_status()`
- `refresh_metadata_cache()`
- `clear_metadata_cache()`
- `list_text_groups(language=None, query=None, limit=100)`
- `get_author_resources(author, language=None)`
- `find_author_names(query, language=None, limit=100)`
- `get_work_resources(urn_or_title)`
- `get_label(urn)`
- `get_first_urn(urn)`
- `get_prev_next_urn(urn)`
- `search_perseus(query, language="greek", query_format="auto", author=None, search_kind="form", preserve_operators=False, page_num=1, text_group=None, work=None, result_format="instances")`
- `search_within_text(query, text_urn, ...)`
- `get_passage_highlights(query, passage_urn, ...)`
- `get_scaife_library_metadata(urn)`
- `get_scaife_passage_json(urn)`
- `get_scaife_passage_text(urn)`

Raw CTS operations return XML text, `search_perseus` returns Scaife JSON text,
discovery helpers return locally shaped JSON text, and
`get_passage_plaintext` returns readable passage text.

`search_perseus` defaults to form search. Set `search_kind="lemma"` for lemma
search. For Scaife operator queries, set `preserve_operators=True` and usually
`query_format="unicode"` so characters such as quotes, `-`, `|`, `*`, and `~`
reach Scaife unchanged.
Use `page_num`, `text_group`, and `work` to page or scope Scaife library search
server-side. `search_within_text` uses Scaife's reader search endpoint for one
edition/text URN.

CTS capabilities and valid reference metadata are cached locally by default.
Use `get_cache_status()`, `refresh_metadata_cache()`, and
`clear_metadata_cache()` to inspect or manage the cache. Set
`PERSEUS_MCP_DISABLE_CACHE=1` to disable it, `PERSEUS_MCP_CACHE_DIR` to change
the disk location, or `PERSEUS_MCP_CACHE_TTL_SECONDS` to adjust expiry.
By default, the disk cache is relative to the Python process current working
directory. A server started from the project root uses `.cache/perseus-mcp`,
while a notebook kernel started inside `examples/` would otherwise use
`examples/.cache/perseus-mcp`. This does not start two MCP servers; it only
means two separate Python processes can have separate disk cache directories
and separate in-memory caches. Set `PERSEUS_MCP_CACHE_DIR` to one absolute path
when you want notebooks and MCP clients to share the same disk cache.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) recommended (or pip)
- An MCP-capable client (Cursor, Claude Desktop, MCP Inspector)

## Install

From the project root:

```bash
uv sync
```

Alternative:

```bash
pip install -e .
```

## Run the Server

```bash
uv run server.py
```

## Quick Tool Testing (Inspector)

```bash
npx @modelcontextprotocol/inspector uv run server.py
```

Use the inspector UI to call tools and verify responses.

## Use with the LLM Client of Your Choice

MCP separates the tool server from the model. This repository does not choose an
LLM for you. Instead, it exposes tools that any MCP-capable client can attach to
a model from its supported providers. The same local server command is the key
piece of configuration:

```bash
uv --directory /full/path/to/Perseus-mcp run server.py
```

When configuring a client, map that command into the client's MCP-server config.
Most clients ask for the same conceptual fields:

| Field | Value |
| --- | --- |
| Server name | `perseus` |
| Command | `uv` |
| Arguments | `--directory`, `/full/path/to/Perseus-mcp`, `run`, `server.py` |
| Environment | usually empty |
| Transport | stdio/local process, if the client asks |

After connection, ask your client to list MCP tools or inspect the `perseus`
server. You should see tools such as `find_author_names`, `get_author_resources`,
`get_passage_plaintext`, `get_prev_next_urn`, and `search_perseus`.

### Prompting pattern for any LLM

For reliable results, ask the model to use the tools in a research sequence:

1. **Discover**: call
   `get_author_resources("urn:cts:greekLit:tlg0012", language="greek")` or
   `list_text_groups(language="greek", query="Homer")`.
2. **Select a URN**: choose an edition/work URN from the JSON or XML result.
3. **Fetch or navigate**: call `get_passage_plaintext(...)`,
   `get_valid_references(...)`, or `get_prev_next_urn(...)`.
4. **Verify**: when precision matters, call `get_passage(...)` or
   `get_passage_plus(...)` to inspect the raw CTS XML.

If your preferred LLM application does not support MCP natively, you can still
use the notebooks or write a small Python adapter with FastMCP's `Client` to call
these tools and pass the results into that application manually. The optional
`examples/06_openrouter_llm_mcp_interaction.ipynb` notebook demonstrates such a
client-side adapter for OpenRouter; it requires an OpenRouter API key, unlike
the MCP server and its public Perseus/Scaife upstream calls.

To configure that optional notebook, copy `.env.example` to `.env` in the
project root and replace the placeholder:

```dotenv
OPENROUTER_API_KEY=sk-or-v1-...
```

Get your API key at [openrouter.ai](https://openrouter.ai/settings/keys). See
[OpenRouter's API key documentation](https://openrouter.ai/docs/api-keys) for
authentication details.
Notebook `06_` loads the project-root `.env` file without overriding an existing
environment variable. The `.env` file is ignored by Git and must not be
committed.

You may save and commit notebook `06_` with its LLM and tool-call outputs so
they render on GitHub. The notebook file does not store Python variables or
kernel memory, and the implementation does not print the key. Review visible
outputs and run this secret scan before committing:

```bash
rg "sk-or-v1-[A-Za-z0-9_-]{20,}" examples/06_openrouter_llm_mcp_interaction.ipynb
```

The command should produce no output. It does not match the documented
`sk-or-v1-...` placeholder.

## Configure Cursor

Edit your `mcp.json`:

- macOS: `~/Library/Application Support/Cursor/mcp.json`
- Windows: `%APPDATA%\Cursor\mcp.json`

Example:

```json
{
  "mcpServers": {
    "perseus": {
      "command": "uv",
      "args": ["--directory", "/full/path/to/Perseus-mcp", "run", "server.py"],
      "env": {}
    }
  }
}
```

Restart Cursor, then confirm the `perseus` server and tools appear.

## Configure Claude Desktop

Claude Desktop is an MCP-capable host for local stdio servers. The latest
Claude-related project documentation already treats Claude Desktop like Cursor
and MCP Inspector: it launches the same local `perseus` server and then exposes
the discovered tools to the selected Claude conversation. The only Claude-specific
part is where you place the JSON configuration and how you restart/debug the
desktop app.

Open Claude Desktop settings, go to **Developer**, and choose **Edit Config**.
You can also edit the configuration file directly:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add or merge the `perseus` entry under `mcpServers`:

```json
{
  "mcpServers": {
    "perseus": {
      "command": "uv",
      "args": [
        "--directory",
        "/full/path/to/Perseus-mcp",
        "run",
        "server.py"
      ],
      "env": {}
    }
  }
}
```

Use an absolute project path. If Claude Desktop cannot find `uv`, replace
`"uv"` with the full executable path returned by `which uv` on macOS or
`where uv` on Windows. Save the file and completely quit and reopen Claude
Desktop so it reloads the MCP server list.

After restart, open a new Claude conversation and look for the MCP/tool indicator
or ask Claude to list available MCP tools. You should see the same `perseus`
tools documented above, including `get_author_resources`,
`get_passage_plaintext`, `get_prev_next_urn`, and `search_perseus`.

## Generic MCP JSON Example

Some clients use a JSON structure similar to Cursor's but with different file
locations. If your client supports local stdio MCP servers, adapt this shape:

```json
{
  "mcpServers": {
    "perseus": {
      "command": "uv",
      "args": [
        "--directory",
        "/full/path/to/Perseus-mcp",
        "run",
        "server.py"
      ],
      "env": {}
    }
  }
}
```

Check your client's documentation for the exact config-file path and whether it
uses `mcpServers`, `servers`, or another top-level key. The command and argument
values are the important part.

## Discovery Tools

The discovery helpers are useful when you do not yet know the exact CTS URN to fetch:

- `list_text_groups(language=None, query=None, limit=100)` lists author/textgroup matches and their works. Use `language="greek"` or `language="latin"` to focus the inventory, and `query` to match author names, textgroup URNs, or work titles.
- `get_author_resources(author, language=None)` returns detailed JSON for a matching author or textgroup, including work URNs, titles, languages, editions, translations, and other resource URNs.
- `find_author_names(query, language=None, limit=100)` matches only CTS author/textgroup name fields, so partial queries such as `"Hom"` return author names without also matching work titles.
- `get_work_resources(urn_or_title)` narrows directly to a work title or work URN and returns its editions/translations/resources with author context.
- `get_passage_plaintext(urn)` fetches a passage through CTS and extracts readable text from the returned XML.

Examples:

- `list_text_groups(language="greek", query="Homer")`
- `list_text_groups(language="latin", query="Ovid")`
- `find_author_names("Hom", language="greek")`
- `get_author_resources("urn:cts:greekLit:tlg0012", language="greek")`
- `get_work_resources("Iliad")`
- `get_passage_plaintext("urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.1")`

## URN Tips

Typical CTS URN patterns:

- Work level: `urn:cts:greekLit:tlg0012.tlg001`
- Passage level: `urn:cts:greekLit:tlg0012.tlg001:1.1-1.10`
- Edition-specific: `urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.1`

Do not assume that an edition URN returned by Scaife search is also available
from Perseus CTS. Discover CTS editions first with `get_author_resources(...)`
or `get_work_resources(...)`. For example, recorded notebook runs have shown a
Perseus CTS *Iliad* edition ending in `perseus-grc1` while Scaife search results
used `perseus-grc2`; either inventory may change.

Recommended workflow:

1. Start with `find_author_names(...)`, `list_text_groups(...)`, `get_author_resources(...)`, or `get_work_resources(...)` to discover useful URNs without parsing the full capabilities XML manually.
2. Use `get_label(urn)` for human-readable metadata.
3. Use `get_valid_references(urn)` and optionally `level` to discover citations.
4. Fetch text with `get_passage(...)`, `get_passage_plus(...)`, or `get_passage_plaintext(...)`.
5. Navigate using `get_prev_next_urn(...)`.

`get_first_urn(...)` and `get_prev_next_urn(...)` normally request the
corresponding CTS operations. If Perseus returns malformed HTML for those
operations, the server derives a well-formed XML result from
`GetValidReff`.

## Troubleshooting

- **HTTP 4xx/5xx**: Remote service may be unavailable, URN may be invalid, or endpoint behavior may have changed.
- **No tools in client**: Verify the command/path in your MCP config, and ensure `uv --directory /full/path/to/Perseus-mcp run server.py` works manually.
- **Client connects but the model does not call tools**: explicitly ask the model to use the `perseus` MCP tools, or use the client's tool picker/approval UI if it has one.
- **Wrong model/provider**: model choice is controlled by your LLM client, not by this server. Keep this MCP server config the same and choose the desired model in the client.
- **Search mismatch**: `search_perseus` accepts Unicode Greek or Beta Code for Greek queries. For ambiguous ASCII, set `query_format="betacode"` or `query_format="unicode"`. For Scaife operator queries, set `preserve_operators=True`; otherwise Beta Code auto-detection may consume characters such as `+`, `|`, or `*`. The `language` argument controls query normalization but is not currently sent to Scaife as a corpus language filter. The optional `author` argument uses a server-side Scaife `text_group` filter when it resolves to one textgroup, and otherwise falls back to local filtering over the current result page.
- **Unexpected edition URN**: Scaife search and Perseus CTS do not always expose the same edition identifiers. Use the discovery tools before calling CTS passage or navigation tools.

