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
- pip for a standard install, or [uv](https://docs.astral.sh/uv/) 0.13.9+ for a repeatable checkout install;
- an MCP-capable client.

Choose either option. Both install the same Perseus tools and enforce the
package's security minimums.

**Standard install from PyPI** is the easiest option if you just want to use
the server. You do not need to download the repository:

```bash
python -m pip install perseus-mcp
perseus-mcp
```

Pip chooses compatible dependency versions when installing. It does not force
the exact versions used in our tests. To update an existing installation and
its dependencies, use `python -m pip install --upgrade --upgrade-strategy=eager perseus-mcp`.

**Repeatable install from a repository checkout** uses the exact dependency
versions recorded in the project's `uv.lock` file. Choose this if you want to
match the tested environment. From the project directory:

```bash
uv sync --locked
uv run --locked perseus-mcp
```

The lockfile is only needed for the repeatable option. Standard PyPI users
remain free to install compatible updates above the security minimums. Both
options require Python 3.11+; keep your Python security patches current.

If the launch command starts without an error, stop it with `Ctrl+C`, then
configure your MCP client.

## Connect your MCP client

For a standard PyPI install, use `perseus-mcp` as the client command with no
arguments. If it is not on the client's PATH, use the full path to the installed
executable in your Python environment.

For a repository checkout, the application launches this command. The JSON
examples below show this checkout option:

```bash
uv --directory /full/path/to/Perseus-mcp run --locked perseus-mcp
```

Replace `/full/path/to/Perseus-mcp` with the absolute path to this repository.

<details markdown="1">
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
        "--locked",
        "perseus-mcp"
      ]
    }
  }
}
```

Restart Cursor and confirm that the `perseus` server appears in its MCP tools.

</details>

<details markdown="1">
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
        "--locked",
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

<details markdown="1">
<summary><strong>Other local MCP clients</strong></summary>

### Other local MCP clients

Use these values when a client asks for separate fields:

| Field | Value |
| --- | --- |
| Server name | `perseus` |
| Command | `uv` |
| Arguments | `--directory`, absolute project path, `run`, `--locked`, `perseus-mcp` |
| Transport | Local process / stdio |
| Environment | Usually empty |

Clients may call the configuration section `mcpServers`, `servers`, or
something similar. Consult the client documentation for its exact file
location and JSON shape.

</details>

<details markdown="1">
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

<details markdown="1">
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
npx @modelcontextprotocol/inspector uv run --locked perseus-mcp
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

`get_label` returns upstream `GetLabel` XML when available. If that operation
returns malformed content or a CTS service error, it derives `groupname`,
`title`, `label`, `description`, and `versionInfo` from the request metadata of
`GetPassage`. For work or edition URNs, it first selects an advertised passage
using `GetValidReff`. The generated `GetLabel` XML marks its reply with
`source="GetPassage request metadata"`; only available, nonempty fields are
included. Access challenges and invalid URNs remain errors, and no label is
invented if references or request metadata are missing.

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

The default cache is shared across working directories for the same OS user:

| Platform | Default directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\perseus-mcp\Cache` |
| macOS | `~/Library/Caches/perseus-mcp` |
| Linux | `$XDG_CACHE_HOME/perseus-mcp`, normally `~/.cache/perseus-mcp` |

Use `get_cache_status` to see the resolved path. Explicit absolute overrides
choose another shared directory; explicit relative overrides resolve against
the working directory. Earlier project-local `.cache/perseus-mcp` directories
are not migrated or deleted. Set an absolute override to reuse an old cache.
Only metadata is cached, never passage bodies or search results.

`clear_metadata_cache` deletes generated hash-named XML/JSON entries and their
temporary files in `capabilities`, `valid_reff`, and `scaife_library`. It skips
symlinks and Windows reparse points, preserves unrelated files and nested
directories, and removes directories only when empty. Its JSON summary includes
`disk_files_removed`; `disk_cache_removed` indicates whether the root directory
was removed. Status counts only these managed files.

On Windows, OneDrive can temporarily lock or mark cache directories read-only.
Close the process holding the directory and retry `clear_metadata_cache()`.

## MCP permissions and source trust

The server itself does not use OpenAI, Anthropic, OpenRouter, or another model
provider. It fetches Perseus/Scaife data for the MCP client, which can independently
use the user's chosen model. FastMCP OpenAPI providers and OAuth integrations
are not configured by the shipped stdio server. Optional notebooks 06 and 09
call OpenRouter explicitly and require a separate key.

Research tools read public scholarly sources and can populate the local metadata
cache. `refresh_metadata_cache` writes that cache and `clear_metadata_cache`
removes its generated entries. Their MCP annotations advertise these side
effects: cache-producing research tools and refresh are non-destructive writes,
clear is destructive, and cache inspection
and clearing have no external-service access. Annotations are advisory; use
your client's permissions to decide which calls require approval.

No tool accepts an arbitrary filesystem path, executes shell commands, or reads
credentials. The server process nevertheless inherits the user's OS permissions;
it is not an operating-system sandbox. Cache paths and runtime configuration
come from the launching environment, not tool arguments.

Treat returned text as untrusted research data, not instructions for the LLM.
Queries and URNs are transmitted to the public Perseus/Scaife services.

## Troubleshooting

Use a current Python security patch: the CI baselines are 3.11.18, 3.12.16, and
3.13.18. Checkout users should use uv 0.13.9 or later and `uv sync --locked`; the full
cross-platform dependency graph and artifact hashes are in `uv.lock`. PyPI users
receive security floors from package metadata, including FastMCP `>=4.2.3,<5`,
but pip does not automatically use the repository's lockfile. Upgrade the full
dependency environment, not FastMCP alone. Keep pip 26.2.2+, certifi 2026.10.19+,
and OS/container trust stores current. See the repository's
[security policy](https://github.com/tonyjurg/Perseus-mcp/blob/main/SECURITY.md)
for reproducible installs, audit commands, and update review.

Upstream access challenges return an MCP tool error with code `UPSTREAM_CHALLENGE`;
they are never search results and are not retried automatically. Invalid response
formats use `INVALID_PAYLOAD`, and recognised CTS errors use `INVALID_URN` or
`UPSTREAM_CTS_ERROR`. Invalid metadata cache entries are discarded before refetching.

HTTP failures use `UPSTREAM_HTTP_ERROR`; timeouts use `UPSTREAM_TIMEOUT`;
connection/read/write failures use `UPSTREAM_CONNECTION_ERROR`; other transport
failures (including redirect loops) use `UPSTREAM_TRANSPORT_ERROR`. Error JSON
includes `upstream_http_status` when response headers were received, or `null`
when no response status is available. Response bodies and raw transport details
are not included in these messages.

Redirects may stay within the original HTTPS origin (same scheme, hostname,
and port) only. Cross-host, HTTP downgrade, port-changing, and credential-bearing
redirects are closed unread and rejected before contacting the target, using
`UPSTREAM_REDIRECT_BLOCKED` with no automatic retry permission. If a service
moves to a different host, its configured base URL needs a reviewed update.

Responses are streamed with a default 16 MiB limit (16,777,216 bytes). Set
`PERSEUS_MCP_MAX_RESPONSE_BYTES` to a positive integer to change it. A declared
Content-Length above the limit is rejected before reading; decoded bytes are
also counted, including compressed responses and responses without a reliable
Content-Length. Oversized responses return `UPSTREAM_RESPONSE_TOO_LARGE` and
are not cached. Redirect bodies are closed unread. This bounds retained body
size; HTTPX still decodes individual compressed chunks before their size can
be checked.

Body reading also has a total 60-second deadline to accommodate large metadata
responses over slower connections. Set
`PERSEUS_MCP_BODY_TIMEOUT_SECONDS` to a positive finite number of seconds
(fractions are allowed) to change it. This deadline spans the entire body read
and does not reset when bytes arrive, so a slow trickle cannot keep it open
indefinitely. Expiry closes the stream, returns `UPSTREAM_TIMEOUT` with the
received HTTP status, and does not cache partial content. HTTPX's existing
per-operation timeouts still apply to connection, headers, and individual reads;
the body deadline starts after the final response headers, not before redirects.

`automatic_retry_allowed` is a policy hint for callers, not an automatic retry
performed by this server. Its defaults are `true` for `UPSTREAM_TIMEOUT`,
`UPSTREAM_CONNECTION_ERROR`, and `UPSTREAM_HTTP_ERROR` with status 429, 500, 502,
503, or 504.
Other HTTP statuses and all other codes above default to `false` (including
challenges, invalid payloads/URNs, CTS errors, and oversized bodies).

HTTP error JSON includes `retry_after_seconds`, a nonnegative integer parsed
from `Retry-After`, or `null` if the header is absent or invalid. Both integer
seconds and HTTP dates are supported; dates are converted to seconds using the
local UTC clock, rounded up, and clamped to zero if already past. Both numeric
and date-based delays are capped at 3,600 seconds (one hour), so unexpectedly
large upstream values cannot request an unbounded wait. Callers should use this
bounded delay when retrying. A `null` value supplies no delay advice;
it does not mean retry immediately. For example, a 429 with `Retry-After: 30`
returns `automatic_retry_allowed: true` and `retry_after_seconds: 30` by default.

After an actual 429 or 503 with a positive valid `Retry-After`, the server records
a per-origin cooldown using a monotonic clock. Further requests to that origin
fail immediately without network traffic, preserving the earlier status and
reporting the remaining rounded-up delay. Other origins remain available;
requests resume normally after expiry. This never schedules a retry or waits
inside a tool call. Missing, invalid, or zero delays do not start a cooldown.
Cooldowns are process-local and do not coordinate independent notebook kernels
or clients. Continue to limit concurrency and pace high-volume workflows.

Override individual defaults with the `PERSEUS_MCP_RETRY_POLICY` environment
variable, containing a JSON object. For example, in an MCP configuration's
`env` object:

```json
{
  "PERSEUS_MCP_MAX_RESPONSE_BYTES": "16777216",
  "PERSEUS_MCP_BODY_TIMEOUT_SECONDS": "60",
  "PERSEUS_MCP_RETRY_POLICY": "{\"UPSTREAM_TIMEOUT\": false, \"UPSTREAM_CONNECTION_ERROR\": false}"
}
```

Only known error codes and JSON boolean values are accepted. Omitted codes keep
their defaults. An explicit `UPSTREAM_HTTP_ERROR` override takes precedence over
the status-based defaults for every HTTP status; setting it to `false` disables
retry permission even for those retryable statuses while preserving `retry_after_seconds`.
No separate configuration file is needed. Changing this policy
does not enable server-side retries or navigation/label fallbacks for challenges.

The command-line server validates `PERSEUS_MCP_RETRY_POLICY`,
`PERSEUS_MCP_MAX_RESPONSE_BYTES`, and `PERSEUS_MCP_BODY_TIMEOUT_SECONDS` at startup,
before starting the MCP transport. Invalid settings stop startup with an error
naming the setting, rather than failing on the first tool call.

| Problem | What to check |
| --- | --- |
| Server does not appear | Validate the JSON, use an absolute project path, and restart the client completely |
| Client cannot find `uv` | Use the full executable path returned by `where uv` or `which uv` |
| Server fails to start | Run `uv --directory /full/path/to/Perseus-mcp run perseus-mcp` in a terminal |
| No tools are listed | Confirm the server is connected and ask the client to refresh or list MCP tools |
| Model ignores tools | Explicitly ask it to use the `perseus` MCP tools or enable tools in the client UI |
| HTTP 404 or 5xx | Check the URN and consider whether Perseus or Scaife is temporarily unavailable |
| HTTP 429 Too Many Requests | Perseus or Scaife is rate-limiting requests. The server issues an `UpstreamRateLimitWarning`, preserves the upstream HTTP error, and does not automatically retry. Stop concurrent requests, honor `Retry-After` when supplied, wait, and retry more slowly |
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
