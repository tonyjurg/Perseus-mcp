# Dependency and runtime security

The supported dependency baseline is FastMCP `>=4.2.3,<5`. The published
package also sets security floors for AnyIO, certifi, cryptography, dnspython,
pydantic-settings, and PyJWT. These constrain existing pip environments as well
as new installs; updating FastMCP alone can otherwise retain vulnerable packages.
Build and test tools have security floors too; these do not add test tools to
the end-user server installation.

Use current security patches for your Python minor version. CI uses
Python 3.11.18, 3.12.16, and 3.13.18; `.python-version` selects 3.13.18
for local development. Update OS/container certificate stores and existing
installers as well. In particular, use certifi 2026.10.19+ and pip 26.2.2+ after
the October 2026 eMudhra/emSign incident. Python package updates do not replace
OS trust-store maintenance. See the [Python security guidance](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576).

## Reproducible installs and updates

`uv.lock` records exact versions and artifact hashes across Python versions,
platforms, and the `dev`, `docs`, and `security` extras. Use uv 0.13.9 or later
(CI pins 0.13.9 for repeatability):

```sh
uv sync --locked --all-extras
uv run --locked --all-extras python -m pytest
```

For a server-only checkout installation, use `uv sync --locked` and
`uv run --locked perseus-mcp`. PyPI installations consume the dependency ranges
in package metadata; pip does not automatically apply this repository's lockfile.
An audited lockfile provides reproducibility, not a permanent security guarantee.

To review an update, run `uv lock --upgrade`, inspect the manifest and lock diff,
run the tests and audits, and submit a pull request. Dependabot proposes weekly
lock updates. CI also tests the lowest direct dependency versions and a fresh
highest-version resolution, separately from the locked Python/OS matrix.

## Full audits

```sh
uv sync --locked --all-extras
uv run --locked --all-extras python -c "from pathlib import Path; Path('.cache/audit').mkdir(parents=True, exist_ok=True)"
uv pip freeze --exclude-editable > .cache/audit/installed.txt
uv run --locked --all-extras python -m pip_audit -r .cache/audit/installed.txt --no-deps --disable-pip --strict --vulnerability-service osv
uv run --locked --all-extras python scripts/check_fastmcp_advisories.py
```

The `Full dependency audit` workflow additionally exports the entire lock as
`pylock.toml` and audits every locked package, including platform-specific
packages absent from its Linux environment. It runs on PRs, main/development
pushes, daily, and before release artifacts or PyPI publication. Publishing
remains a separate manual action. Audit-service errors fail the check.

The upstream check reads the maintained [FastMCP advisories](https://github.com/PrefectHQ/fastmcp/security/advisories)
directly, including GHSAs without CVE IDs or OSV records, and compares both
installed and locked versions. Set `GH_TOKEN` to a read-only GitHub token when
necessary for API rate limits; CI supplies its read-only job token. No findings
are ignored on the basis that a feature is unused. Empty/unavailable feeds fail
instead of producing a successful result.

## Caller input

URNs are limited to 1,024 Unicode characters; queries and author/title selectors
to 2,048. Raw lengths are checked before normalization, and normalized search
queries are checked again. CTS request/cache helpers and Scaife URL builders
validate URN structure before use; search/discovery tools check all supplied
selectors before loading inventories or making requests. Controls, invisible
formatting characters, and malformed CTS structure fail locally without
including the submitted value in validation messages. URL path encoding remains
an additional defense.

Validation preserves catalogue URNs with or without a trailing colon, citation
ranges, lettered labels, and Unicode substring references. It does not look up
existence or impose an allowlist of namespaces/works. It prevents malformed or
oversized URNs from creating cache keys, but is not a disk quota or a rate limit
for syntactically valid requests. Existing metadata can be removed with
`clear_metadata_cache`.

## Application scope and model providers

The shipped Perseus MCP server fetches scholarly data from Perseus CTS and
Scaife. It does not call OpenAI, Anthropic, OpenRouter, or another LLM provider,
and does not require their credentials or SDKs. The project does not enable
FastMCP's optional OpenAI/Anthropic integrations. An external MCP client may
independently use a model provider of the user's choice.

The standard entry point uses stdio, hand-written tools, and static tool schemas.
It does not configure FastMCP OpenAPI providers, OAuth proxies/providers,
component-authorization transforms, or SSE serving. Several historical FastMCP
advisories require these features; their presence in the framework dependency
does not mean the application enables them. The dependency baseline is patched
regardless of that reduced exposure. If these features are added, reassess their
configuration-specific protections, such as OAuth issuer binding.

Example notebooks 06 and 09 deliberately demonstrate optional OpenRouter calls.
Those notebooks transmit their selected prompts/context to OpenRouter and use a
separately supplied key; model selection may include third-party providers.
They are outside the server's default network behavior. They must not be
described as having no model-provider usage.

MCP clients control approval of tool calls. Tool annotations are advisory, and
the Python process inherits its user's OS permissions. Treat upstream text as
untrusted source material. Do not include credentials in public issue reports.
