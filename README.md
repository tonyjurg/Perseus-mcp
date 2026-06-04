[![Project Status: Concept – Minimal or no implementation has been done yet, or the repository is only intended to be a limited example, demo, or proof-of-concept.](https://www.repostatus.org/badges/latest/concept.svg)](https://www.repostatus.org/#concept)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python)](https://www.python.org/) ![Jupyter](https://img.shields.io/badge/Jupyter-F37626?logo=jupyter&logoColor=white) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/tonyjurg/Perseus-mcp)

# Perseus-mcp

MCP server for Perseus Greek text research. It runs as a local FastMCP server so MCP-capable applications can attach these Perseus tools to the LLM/model provider of your choice.

## Features

This server exposes twelve MCP tools. Every tool returns a text payload: some
are raw Perseus CTS XML or Scaife JSON, while the discovery and plaintext
helpers return locally shaped JSON or readable text.

- `get_passage(urn)` — fetch a CTS passage by URN.
- `get_passage_plus(urn)` — fetch passage text plus contextual metadata.
- `get_passage_plaintext(urn)` — fetch a CTS passage as plain readable text.
- `get_valid_references(urn, level=None)` — retrieve navigable citation references for a work or edition.
- `get_capabilities()` — list available texts/editions from Perseus CTS.
- `list_text_groups(language=None, query=None, limit=100)` — list matching authors/textgroups and works.
- `get_author_resources(author, language=None)` — list works, editions, and translations for a matching author name or CTS textgroup URN.
- `get_work_resources(urn_or_title)` — list editions, translations, and resources for a work.
- `get_label(urn)` — fetch human-readable metadata labels for a URN.
- `get_first_urn(urn)` — get the first navigable URN under a work/edition.
- `get_prev_next_urn(urn)` — get neighboring passage URNs for navigation.
- `search_perseus(query, language="greek", query_format="auto")` — search texts via Scaife search API. Greek queries may be entered as Unicode Greek (for example `μῆνιν`) or Beta Code (for example `mh=nin`).

## Greek Search Input

`search_perseus` normalizes Greek search terms before sending them to Scaife.
You can pass Unicode Greek directly, or use Beta Code such as `mh=nin a)/eide`.
The default `query_format="auto"` detects explicit Beta Code marks like `=`, `/`, `(`, `)`, and `*`, and also treats short unaccented Greek-looking queries such as `logos` as Beta Code.
If an ASCII query is ambiguous, set `query_format="betacode"` to force conversion or `query_format="unicode"` to preserve it exactly.
Search queries are normalized to composed Greek Unicode (NFC), matching sampled Perseus Greek text.
The tool uses Scaife's JSON search route and returns the JSON response as text.
The `language` argument controls Greek query normalization; it is not currently
sent to Scaife as a corpus language filter.

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

Run them after installing the project dependencies. The MCP notebooks use
FastMCP's in-process client transport and call the same tools exposed to
external MCP clients. The optional OpenRouter notebook also requires an
OpenRouter API key; the MCP server itself does not.

### Configure the OpenRouter API key

For `examples/06_openrouter_llm_mcp_interaction.ipynb`, copy `.env.example` to
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

## Contributing and reporting issues

Bug reports, documentation fixes, focused feature requests, and pull requests
are welcome. Please report problems through the GitHub issue tracker and include
the command, Python version, MCP client, tool arguments, traceback, and any
relevant CTS URN or Greek search query when possible.

See `docs/contributing.md` for contribution guidance.

## License

This project is released under the MIT License. See `LICENSE` for details.
