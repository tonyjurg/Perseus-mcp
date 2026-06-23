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

## Build Release Artifacts

Build and validate the wheel and source distribution before publishing:

```bash
python -m build
python -m twine check dist/*
```

Test the wheel in a clean virtual environment. Upload to TestPyPI before the
production PyPI index. Every release needs a new version in `pyproject.toml`;
published files cannot be replaced under the same version.

## Automated Releases

Production releases use GitHub Actions and PyPI trusted publishing. Push a tag
that exactly matches the package version with a leading `v`, such as `v1.0.2`
for `project.version = "1.0.2"`.

The release workflow builds and validates the wheel and source archive, creates
a GitHub release containing those artifacts, and dispatches the separate
PyPI-publishing workflow. The publishing job runs in the GitHub environment
named `pypi` and authenticates to PyPI through OIDC rather than a stored API
token.

The PyPI trusted publisher must be configured for:

- owner: `tonyjurg`;
- repository: `Perseus-mcp`;
- workflow: `publish.yml`;
- environment: `pypi`.

Keep pull requests narrowly scoped. A good pull request usually contains:

- a clear description of the change;
- tests for changed behavior;
- documentation updates when the user-facing tool surface changes;
- notes about any upstream Perseus or Scaife behavior that influenced the
  implementation.

## Documentation Changes

Documentation-only changes under `docs/` publish to GitHub Pages without
running the Python test workflow. If a documentation change also updates code,
configuration, examples, or tests, the test workflow still runs.

## Security and Credentials

Do not commit API keys, local `.env` files, notebook secrets, or private client
configuration. The `.env.example` file documents expected environment variables
without storing real credentials.
CI blocks pull requests and direct pushes to `main` or `development` that
contain an OpenRouter key-like token matching
`sk-or-v1-[A-Za-z0-9_-]{20,}` in tracked files. Feature branches run the same
checks through their pull request without duplicating the workflow on push.
