---
title: Contributing and Reporting Issues
description: How to report bugs, request changes, and contribute to Perseus MCP.
permalink: /contributing/
---

# Contributing and Reporting Issues

Contributions, bug reports, documentation fixes, and reproducible examples are
welcome. This project is intentionally small, so the most useful contributions
are focused changes that improve reliability, documentation clarity, tool
behavior, or test coverage.

## Report Bugs or Errors

Please report problems through the repository issue tracker:
[github.com/tonyjurg/Perseus-mcp/issues](https://github.com/tonyjurg/Perseus-mcp/issues).
Use the issue template that best matches the problem:

- bug or error report;
- feature request;
- documentation issue;
- upstream data or service issue.

When reporting an error, include as much of the following as possible:

- the command you ran;
- your Python version;
- whether you used `uv`, `pip`, an MCP client, or MCP Inspector;
- the tool name and arguments, if the problem happened during a tool call;
- the full error message or traceback;
- a short example that reproduces the problem;
- whether the problem appears to come from the local server or from an upstream
  Perseus/Scaife response.

For Greek search or CTS passage issues, include the query text or URN you used.
If the response looks wrong, include the relevant returned XML, JSON, or plain
text excerpt.

## Request Features

Feature requests are easiest to evaluate when they describe the research or
client workflow they would support. Please include:

- the task you are trying to complete;
- the current workaround, if any;
- the expected tool behavior or output shape;
- links to upstream Perseus, Scaife, CTS, or MCP documentation when relevant.

## Contribute Code

Before opening a pull request, install the development dependencies and run the
test suite:

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
```

With `uv`:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check src tests
```

Keep pull requests narrowly scoped. A good pull request usually contains:

- a clear description of the change;
- tests for changed behavior;
- documentation updates when the user-facing tool surface changes;
- notes about any upstream Perseus or Scaife behavior that influenced the
  implementation.


## Release artifacts and PyPI publishing

Pushing a `v*` tag runs the release artifact workflow, which builds distributions
and attaches them to a GitHub release. Neither tag pushes nor GitHub release
publication publishes the package to PyPI.

PyPI publishing is a separate, manual action. After reviewing the release,
dispatch `Publish to PyPI` against the intended tag, for example:

```bash
gh workflow run publish.yml --ref v1.1.0
```

Both workflows require the tag to match `v` followed by the package version in
`pyproject.toml` exactly (for example, `v1.1.0` for version `1.1.0`). A tag such
as `v1_1_0` is a source marker and fails this release validation.

These safeguards apply to commits containing the updated workflows. Tags on
older commits retain those commits' workflow definitions; do not push an older
tag expecting the new manual-only publishing behavior.

## Security and Credentials

Do not commit API keys, local `.env` files, notebook secrets, or private client
configuration. The `.env.example` file documents expected environment variables
without storing real credentials.

CI blocks pull requests and direct pushes to `main` or `development` that
contain an OpenRouter key-like token matching
`sk-or-v1-[A-Za-z0-9_-]{20,}` in tracked files. Feature branches run the same
checks through their pull request without duplicating the workflow on push.

## API documentation

Module, class, and function docstrings live beside the implementation. Build the
Sphinx reference locally with:

```bash
python -m pip install -e ".[docs]"
python -m sphinx -W --keep-going -b html docs/api .cache/api-docs
```

Open `.cache/api-docs/index.html`. Use Google-style `Args`, `Returns`, and `Raises`
sections for contracts that need more than a summary. Tool docstrings also become
MCP descriptions, so preserve them when performing structural refactors.

GitHub Actions builds and publishes the current codebase and every Git tag.
The selector in the API reference switches between Current (main) and tagged
releases. Tags without Sphinx sources get a reference generated from their own
Python modules and docstrings; current architecture prose is not copied into
historical references. Each tag is built in an isolated Python environment.

The Pages workflow rebuilds on relevant main changes, tag pushes, published
releases, and manual dispatch. Pull requests validate the same build without
deploying. The complete set is published under `/api/`, with tagged references
under `/api/versions/`. No local build or manual upload is required.

For a local preview of the complete set, use
`python scripts/build_api_docs.py --output .cache/api-docs` after fetching tags.
Add `--current-only` for a faster preview. The build writes a `versions.json`
manifest recording the exact source commit for each version.

The documentation uses [Sphinx autodoc](https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html)
and its bundled Napoleon extension to render Python docstrings.
