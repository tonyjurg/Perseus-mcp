---
title: End-User Guide
description: Install, connect, and use the Perseus MCP server with supported clients.
permalink: /enduser/
---

# Perseus MCP: End-User Guide

Use Perseus MCP with Cursor, Claude Desktop, ChatGPT, or another MCP-capable
client to discover, search, retrieve, and navigate Greek and Latin texts from
Perseus CTS and Scaife.

The server does not require a Perseus, Scaife, or OpenRouter API key. Cursor,
Claude Desktop, and similar clients can run it locally. ChatGPT instead needs
an HTTPS-accessible MCP endpoint.

## Quick start

You need:

- Python 3.11 or newer;
- [uv](https://docs.astral.sh/uv/) (recommended);
- an MCP-capable client.

From the project directory:

```bash
uv sync
uv run perseus-mcp
```

If the second command starts without an error, the server is ready. Stop it
with `Ctrl+C`, then add it to your MCP client using the configuration below.

Prefer pip?

```bash
pip install -e .
perseus-mcp
```

## Connect your MCP client

For a local MCP client, the application launches this command:

```bash
uv --directory /full/path/to/Perseus-mcp run perseus-mcp
```

Replace `/full/path/to/Perseus-mcp` with the absolute path to this repository.

<details>
<summary><strong>Cursor configuration</strong></summary>

### Cursor

Open or create `mcp.json`:

- Windows: `%APPDATA%\Cursor\mcp.json`
- macOS: `~/Library/Application Support/Cursor/mcp.json`

Add:

```json
{
  "mcpServers": {
    "perseus": {
      "command": "uv",
      "args": [
        "--directory",
        "/full/path/to/Perseus-mcp",
        "run",
        "perseus-mcp"
      ]
    }
  }
}
```

Restart Cursor and confirm that the `perseus` server appears in its MCP tools.

</details>

<details>
<summary><strong>Claude Desktop configuration</strong></summary>

### Claude Desktop

In Claude Desktop, open **Settings → Developer → Edit Config**, or edit:

- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

Add the same server configuration:

```json
{
  "mcpServers": {
    "perseus": {
      "command": "uv",
      "args": [
        "--directory",
        "/full/path/to/Perseus-mcp",
        "run",
        "perseus-mcp"
      ]
    }
  }
}
```

Completely quit and reopen Claude Desktop. Start a new conversation and ask
Claude to list the available `perseus` tools.

If the client cannot find `uv`, replace `"uv"` with the full executable path
returned by:

```bash
where uv
```

On macOS or Linux:

```bash
which uv
```

</details>

<details>
<summary><strong>Other local MCP clients</strong></summary>

### Other local MCP clients

Use these values when a client asks for separate fields:

| Field | Value |
| --- | --- |
| Server name | `perseus` |
| Command | `uv` |
| Arguments | `--directory`, absolute project path, `run`, `perseus-mcp` |
| Transport | Local process / stdio |
| Environment | Usually empty |

Clients may call the configuration section `mcpServers`, `servers`, or
something similar. Consult the client documentation for its exact file
location and JSON shape.

</details>

<details>
<summary><strong>ChatGPT configuration</strong></summary>

### ChatGPT

ChatGPT supports MCP apps, but it cannot launch this repository as a local
stdio process. It connects to a server through a reachable HTTPS `/mcp`
endpoint.

The current Perseus MCP command therefore cannot be pasted directly into
ChatGPT. A ChatGPT-compatible deployment needs:

1. an HTTP transport for the FastMCP server;
2. an HTTPS deployment or a secure development tunnel;
3. a connector URL ending in `/mcp`.

After such an endpoint is available:

1. In ChatGPT, open **Settings → Apps & Connectors → Advanced settings**.
2. Enable **Developer mode**.
3. Under **Apps & Connectors**, choose **Create**.
4. Enter a name, description, and the HTTPS `/mcp` URL.
5. Create the connector and confirm that the Perseus tools are listed.
6. In a new conversation, add the connector from the tools menu.

For local development, OpenAI documents its Secure MCP Tunnel as one option.
An internet-facing deployment should also use appropriate authentication,
rate limiting, monitoring, and request limits.

See OpenAI's
[ChatGPT MCP connection guide](https://developers.openai.com/apps-sdk/deploy/connect-chatgpt)
for the current interface and deployment requirements.

</details>

<details>
<summary><strong>OpenRouter notebook workflow</strong></summary>

### OpenRouter

OpenRouter is not a native local MCP host. The project notebooks instead use a
small Python client that calls the local Perseus MCP tools and passes their
results into an OpenRouter-hosted model.

This workflow requires an OpenRouter API key, but the Perseus MCP server itself
still does not require one.

1. Copy `.env.example` to `.env`.
2. Add `OPENROUTER_API_KEY`.
3. Optionally set `OPENROUTER_MODEL`; the examples default to
   `openrouter/free`.
4. Run one of the OpenRouter notebooks.
5. Never commit `.env`.

Start with:

- [all example notebooks](https://tonyjurg.github.io/Perseus-mcp/notebooks/);
- [OpenRouter LLM MCP interaction](https://nbviewer.org/github/tonyjurg/Perseus-mcp/blob/main/examples/06_openrouter_llm_mcp_interaction.ipynb);
- [OpenRouter Philo *Politeia* analysis](https://nbviewer.org/github/tonyjurg/Perseus-mcp/blob/main/examples/09_openrouter_philo_politeia_analysis.ipynb).

Before committing notebook outputs, scan the notebook for an accidentally
saved key:

```bash
rg "sk-or-v1-[A-Za-z0-9_-]{20,}" examples/*.ipynb
```

The command should produce no output.

</details>

## Verify the connection

After restarting a local client, or adding the connector to a ChatGPT
conversation:

1. Confirm that the `perseus` MCP server is connected.
2. Ask the client to list its Perseus tools.
3. Try:

   > Use the Perseus tools to find Homer and list his available works.

You should see calls to tools such as `find_author_names`,
`get_author_resources`, or `list_text_groups`.

You can also test the server independently with MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uv run perseus-mcp
```

## A reliable research workflow

Ask the model to work in four stages:

1. **Discover** an author, work, or CTS URN.
2. **Select** the appropriate work or edition.
3. **Retrieve or navigate** passages.
4. **Verify** important results against raw CTS XML.

Example prompt:

> Use the Perseus tools to find Homer's *Iliad*. Select a Greek CTS edition,
> retrieve Iliad 1.1–1.7 as plain text, and then show the raw CTS response used
> to verify it.

Useful tools at each stage:

| Task | Recommended tools |
| --- | --- |
| Find an author | `find_author_names`, `list_text_groups` |
| Find works and editions | `get_author_resources`, `get_work_resources` |
| Retrieve a passage | `get_passage_plaintext`, `get_passage`, `get_passage_plus` |
| Explore citations | `get_valid_references_json`, `count_valid_references` |
| Move through a text | `get_first_urn`, `get_prev_next_urn` |
| Search the corpus | `search_perseus` |
| Search one edition | `search_within_text`, `get_passage_highlights` |
| Inspect Scaife data | `get_scaife_library_metadata`, `get_scaife_passage_json` |

## Discover authors, works, and URNs

Start with discovery instead of guessing CTS URNs.

Examples:

```text
find_author_names("Hom", language="greek")
list_text_groups(language="latin", query="Ovid")
get_author_resources("Homer", language="greek")
get_work_resources("Iliad")
```

Typical CTS URNs:

| Level | Example |
| --- | --- |
| Work | `urn:cts:greekLit:tlg0012.tlg001` |
| Passage | `urn:cts:greekLit:tlg0012.tlg001:1.1-1.10` |
| Edition passage | `urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.1` |

Perseus CTS and Scaife may expose different editions of the same work. Use
`get_author_resources` or `get_work_resources` to discover a CTS edition before
requesting a CTS passage.

## Retrieve and navigate passages

For readable text:

```text
get_passage_plaintext(
  "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.1"
)
```

For the original CTS response:

```text
get_passage(
  "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.1"
)
```

For neighboring citations:

```text
get_prev_next_urn(
  "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1:1.1"
)
```

If Perseus returns malformed HTML for a navigation operation, the server can
derive a well-formed result from the valid-reference inventory.

## Search Greek and Latin text

`search_perseus` searches the Scaife library:

```text
search_perseus("μῆνιν", language="greek")
```

Greek can also be entered as Beta Code:

```text
search_perseus("mh=nin", language="greek", query_format="betacode")
```

Useful options:

- `search_kind="lemma"` searches lemmas instead of surface forms;
- `author="Homer"` scopes by a resolved author;
- `text_group=...` or `work=...` scopes directly by URN;
- `page_num=2` requests another results page;
- `result_format="passages"` groups results by passage;
- `preserve_operators=True` preserves quotes and operators such as `-`, `|`,
  `*`, and `~`.

For ambiguous ASCII input, set `query_format="betacode"` to convert it or
`query_format="unicode"` to preserve it.

## Tool groups

The server currently provides 23 text-returning tools.

### Passage and navigation

- `get_passage`
- `get_passage_plus`
- `get_passage_plaintext`
- `get_valid_references`
- `get_valid_references_json`
- `count_valid_references`
- `get_label`
- `get_first_urn`
- `get_prev_next_urn`

### Discovery

- `get_capabilities`
- `list_text_groups`
- `find_author_names`
- `get_author_resources`
- `get_work_resources`

### Search

- `search_perseus`
- `search_within_text`
- `get_passage_highlights`

### Scaife retrieval

- `get_scaife_library_metadata`
- `get_scaife_passage_json`
- `get_scaife_passage_text`

### Cache management

- `get_cache_status`
- `refresh_metadata_cache`
- `clear_metadata_cache`

Raw CTS tools return XML text. Search tools return Scaife JSON text. Discovery
tools return locally shaped JSON text. `get_passage_plaintext` returns readable
text.

## Metadata cache

The server caches stable CTS capabilities, valid references, and Scaife library
metadata to reduce repeat requests.

| Setting | Purpose |
| --- | --- |
| `PERSEUS_MCP_DISABLE_CACHE=1` | Disable memory and disk caching |
| `PERSEUS_MCP_CACHE_DIR` | Choose an absolute disk-cache directory |
| `PERSEUS_MCP_CACHE_TTL_SECONDS` | Change the expiry time |

By default, the cache is stored at `.cache/perseus-mcp` relative to the
process's working directory. Use one absolute `PERSEUS_MCP_CACHE_DIR` if an MCP
client and notebook should share the same disk cache.

On Windows, OneDrive can temporarily lock or mark cache directories read-only.
Close the process holding the directory and retry `clear_metadata_cache()`.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Server does not appear | Validate the JSON, use an absolute project path, and restart the client completely |
| Client cannot find `uv` | Use the full executable path returned by `where uv` or `which uv` |
| Server fails to start | Run `uv --directory /full/path/to/Perseus-mcp run perseus-mcp` in a terminal |
| No tools are listed | Confirm the server is connected and ask the client to refresh or list MCP tools |
| Model ignores tools | Explicitly ask it to use the `perseus` MCP tools or enable tools in the client UI |
| HTTP 404 or 5xx | Check the URN and consider whether Perseus or Scaife is temporarily unavailable |
| HTTP 429 | Stop concurrent requests, wait, and retry more slowly |
| Unexpected edition URN | Discover a Perseus CTS edition before retrieving the passage |
| Search mismatch | Check language, `query_format`, `search_kind`, and operator preservation |
| Cache cannot be cleared | Close processes using it; OneDrive may temporarily lock the directory |

Claude Desktop logs:

- Windows: `%APPDATA%\Claude\logs`
- macOS: `~/Library/Logs/Claude`

## Next steps

- Browse the [example notebooks](https://tonyjurg.github.io/Perseus-mcp/notebooks/)
  for guided workflows.
- See the [architecture guide](https://tonyjurg.github.io/Perseus-mcp/architecture/)
  for implementation details.
- Report reproducible problems through the
  [GitHub issue tracker](https://github.com/tonyjurg/Perseus-mcp/issues).
