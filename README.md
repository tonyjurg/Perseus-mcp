[![Project Status: WIP – Initial development is in progress, but there has not yet been a stable, usable release suitable for the public.](https://www.repostatus.org/badges/latest/wip.svg)](https://www.repostatus.org/#wip) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.20708961-007ec6.svg)](https://doi.org/10.5281/zenodo.20708961) [![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python)](https://www.python.org/) ![Jupyter](https://img.shields.io/badge/Jupyter-F37626?logo=jupyter&logoColor=white) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/tonyjurg/Perseus-mcp)

# Perseus-mcp

*Give Claude / Cursor / Windsurf direct access to the entire Perseus Digital Library* — ancient Greek texts, precise CTS navigation, plaintext, search, and more.

A high-quality MCP server specialized in Classical Greek literature. It runs as a local FastMCP server so MCP-capable applications can attach these Perseus tools to the LLM/model provider of your choice.

## Features

This server exposes twenty-three MCP tools. Every tool returns a text payload: some
are raw Perseus CTS XML or Scaife JSON, while the discovery and plaintext
helpers return locally shaped JSON or readable text.

- `get_passage(urn)` — fetch a CTS passage by URN.
- `get_passage_plus(urn)` — fetch passage text plus contextual metadata.
- `get_passage_plaintext(urn)` — fetch a CTS passage as plain readable text.
- `get_valid_references(urn, level=None)` — retrieve navigable citation references for a work or edition.
- `get_valid_references_json(urn, level=None, limit=100, offset=0)` — retrieve paged citation references as JSON.
- `count_valid_references(urn, level=None)` — count valid references without returning the full list.
- `get_capabilities()` — list available texts/editions from Perseus CTS.
- `get_cache_status()` — inspect local metadata cache state.
- `refresh_metadata_cache()` — refresh cached CTS capabilities.
- `clear_metadata_cache()` — clear in-memory and disk metadata cache entries.
- `list_text_groups(language=None, query=None, limit=100)` — list matching authors/textgroups and works.
- `get_author_resources(author, language=None)` — list works, editions, and translations for a matching author name or CTS textgroup URN.
- `find_author_names(query, language=None, limit=100)` — find author/textgroup names by partial name match.
- `get_work_resources(urn_or_title)` — list editions, translations, and resources for a work.
- `get_label(urn)` — fetch human-readable metadata labels for a URN.
- `get_first_urn(urn)` — get the first navigable URN under a work/edition.
- `get_prev_next_urn(urn)` — get neighboring passage URNs for navigation.
- `search_perseus(query, language="greek", query_format="auto", author=None, search_kind="form", preserve_operators=False, page_num=1, text_group=None, work=None, result_format="instances")` — search texts via Scaife search API. Greek queries may be entered as Unicode Greek (for example `μῆνιν`) or Beta Code (for example `mh=nin`).
- `search_within_text(query, text_urn, ...)` — search within a single Scaife text/edition URN.
- `get_passage_highlights(query, passage_urn, ...)` — get Scaife token highlight positions for one passage.
- `get_scaife_library_metadata(urn)` — get Scaife JSON metadata for a library URN.
- `get_scaife_passage_json(urn)` — get Scaife JSON for a passage URN.
- `get_scaife_passage_text(urn)` — get Scaife plaintext for a passage URN.

## Greek Search Input

`search_perseus` normalizes Greek search terms before sending them to Scaife.
You can pass Unicode Greek directly, or use Beta Code such as `mh=nin a)/eide`.
The default `query_format="auto"` detects explicit Beta Code marks like `=`, `/`, `(`, `)`, and `*`, and also treats short unaccented Greek-looking queries such as `logos` as Beta Code.
If an ASCII query is ambiguous, set `query_format="betacode"` to force conversion or `query_format="unicode"` to preserve it exactly.
Search queries are normalized to composed Greek Unicode (NFC), matching sampled Perseus Greek text.
The tool uses Scaife's JSON search route and returns the JSON response as text.
The `language` argument controls Greek query normalization; it is not currently
sent to Scaife as a corpus language filter.
Pass `author` to resolve a CTS author/textgroup name or URN. When it resolves
to exactly one textgroup, Scaife receives a server-side `text_group` filter;
ambiguous matches fall back to local CTS URN-prefix filtering of the current
result page.
Use `search_kind="lemma"` for lemma search; the default `search_kind="form"`
keeps existing form-search behavior. For Scaife operator queries such as
quoted phrases, `-`, `|`, `*`, or `~`, set `preserve_operators=True` so Beta
Code auto-detection does not consume operator characters. For example:
`search_perseus('"μῆνιν ἄειδε"', query_format="unicode", preserve_operators=True)`,
`search_perseus("μῆνιν -ἄειδε", query_format="unicode", preserve_operators=True)`,
or `search_perseus("λόγος | ἀνήρ", search_kind="lemma", query_format="unicode", preserve_operators=True)`.
Use `page_num` for pagination and pass `text_group` or `work` to use Scaife's
server-side scope filters. When `author` resolves to exactly one CTS textgroup,
`search_perseus` sends that textgroup to Scaife instead of filtering only the
returned page locally.

## Local Metadata Cache

Discovery and navigation tools cache stable CTS metadata locally to avoid
repeated multi-megabyte `GetCapabilities` and `GetValidReff` requests. The
default disk cache lives in `.cache/perseus-mcp` under the current working
directory and also uses an in-memory cache for the running server process.
Configure it with:

- `PERSEUS_MCP_CACHE_DIR` — override the disk cache directory.
- `PERSEUS_MCP_CACHE_TTL_SECONDS` — set cache TTL; default is 86400 seconds.
- `PERSEUS_MCP_DISABLE_CACHE=1` — disable both memory and disk cache reads/writes.

The current working directory is the directory from which the Python process is
started. Running the MCP server from the repository root uses
`.cache/perseus-mcp`; running a notebook from `examples/` would otherwise use
`examples/.cache/perseus-mcp`. That is not a second server instance, only a
second cache location for a separate Python process. To keep one cache location
across notebooks and MCP clients, set `PERSEUS_MCP_CACHE_DIR` to an absolute
path such as `/path/to/Perseus-mcp/.cache/perseus-mcp`.

## URN Discovery

Available edition URNs can differ between Perseus CTS and Scaife search results,
and the live inventory can change. Use `get_author_resources`,
`get_work_resources`, or `list_text_groups` before constructing
edition-specific CTS passage URNs. The notebooks select advertised CTS editions
from discovery results instead of assuming that a Scaife edition URN is valid
for Perseus CTS.

The live Perseus CTS implementation may return malformed HTML for
`GetFirstUrn` and `GetPrevNextUrn`. The MCP tools detect that response and
derive valid XML results from `GetValidReff`.

## Setup

### 1) Install dependencies

Using `uv`:

```bash
uv sync
```

Or with `pip`:

```bash
pip install -e .
```

For development and tests:

```bash
pip install -e ".[dev]"
```

### 2) Run tests

```bash
pytest
```

With `uv`, use:

```bash
uv run --extra dev pytest
```

### 3) Run locally

```bash
uv run server.py
```

### 4) Inspect tools (optional)

```bash
npx @modelcontextprotocol/inspector uv run server.py
```


## Example notebooks

The `examples/` directory includes Jupyter notebooks that demonstrate both direct endpoint calls and MCP client usage with real Greek data:

- `examples/01_basic_cts_workflow.ipynb` — minimal direct CTS requests.
- `examples/02_search_and_navigation.ipynb` — direct Scaife JSON search and CTS navigation from valid references.
- `examples/03_mcp_connection_homer_iliad.ipynb` — FastMCP client connection, Homer resource discovery, and *Iliad* Greek passage analysis.
- `examples/04_mcp_greek_search_and_navigation.ipynb` — MCP Greek search with Unicode/Beta Code, valid references, and passage navigation.
- `examples/05_mcp_all_tools.ipynb` — complete MCP tool catalog with descriptions and input schemas.
- `examples/06_openrouter_llm_mcp_interaction.ipynb` — optional OpenRouter LLM tool-calling loop over the local MCP tools, using NVIDIA Nemotron 3 Super (free) by default.
- `examples/07_mcp_advanced_search_options.ipynb` — MCP form/lemma search, Scaife operator queries, and author-scoped search examples.
- `examples/08_mcp_new_cache_and_search_tools.ipynb` — advanced demonstration of cache tools, paged references, scoped search, reader search, highlights, and Scaife metadata/text retrieval.
- `examples/09_openrouter_philo_politeia_analysis.ipynb` — OpenRouter-assisted, evidence-first analysis of `πολιτεία` in Philo of Alexandria using scoped MCP search results and cited passages.

Run them after installing the project dependencies. The MCP notebooks use
FastMCP's in-process client transport and call the same tools exposed to
external MCP clients. The optional OpenRouter notebook also requires an
OpenRouter API key; the MCP server itself does not.

### Configure the OpenRouter API key

For `examples/06_openrouter_llm_mcp_interaction.ipynb` and
`examples/09_openrouter_philo_politeia_analysis.ipynb`, copy `.env.example` to
`.env` in the project root and replace the placeholder:

```dotenv
OPENROUTER_API_KEY=sk-or-v1-...
```

Get your API key at [openrouter.ai](https://openrouter.ai/settings/keys). See
[OpenRouter's API key documentation](https://openrouter.ai/docs/api-keys) for
authentication details.
The `.env` file is ignored by Git. You can also set `OPENROUTER_API_KEY` in your
environment or enter it securely when the notebook prompts.

Notebook `06_` can be saved and committed with its LLM and tool-call outputs so
they render on GitHub. Python variables and kernel memory are not stored in an
`.ipynb` file, and the notebook does not print the API key. Before committing a
credentialed run, review the visible outputs and scan for a full OpenRouter key:

```bash
rg "sk-or-v1-[A-Za-z0-9_-]{20,}" examples/06_openrouter_llm_mcp_interaction.ipynb
```

The command should produce no output. It does not match the documented
`sk-or-v1-...` placeholder.

## Using with any MCP-capable LLM client

This project does not require a specific LLM. Configure your client to launch the local MCP server with:

```bash
uv --directory /full/path/to/Perseus-mcp run server.py
```

Most MCP clients need the same pieces: server name `perseus`, command `uv`, args `--directory /full/path/to/Perseus-mcp run server.py`, and an empty environment unless you have local customizations. See `docs/enduser.md` for generic client guidance and `docs/architecture.md` for the architecture choices, including why FastMCP is used.

### Claude Desktop and Claude Code

The server runs with Claude over stdio, with no OpenRouter or API key required (OpenRouter is only needed for the optional demo client).

**Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "perseus": {
      "command": "uv",
      "args": ["--directory", "/full/path/to/Perseus-mcp", "run", "server.py"]
    }
  }
}
```

Restart Claude Desktop; the Perseus tools appear in the tools list.

**Claude Code** — one line:

```bash
claude mcp add perseus -- uv --directory /full/path/to/Perseus-mcp run server.py
```

Verified against a stdio MCP handshake: all 23 tools register and live calls return (tested with `search_perseus` and `list_text_groups`).

## Contributing and reporting issues

Bug reports, documentation fixes, focused feature requests, and pull requests
are welcome. Please report problems through the GitHub issue tracker and include
the command, Python version, MCP client, tool arguments, traceback, and any
relevant CTS URN or Greek search query when possible.

See `docs/contributing.md` for contribution guidance.

## Responsible disclosure

This project was created with assistance from OpenAI Codex. The human
maintainer remains responsible for reviewing, testing, and accepting all code
and documentation changes.

## License

This project is released under the MIT License. See `LICENSE` for details.
