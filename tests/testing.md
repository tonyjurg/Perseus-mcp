# Perseus MCP Test Strategy

This document describes how the test suite is structured, how tests are kept
deterministic, and how GitHub Actions automates verification. The repository
README provides the public overview; this file is the maintainer reference
stored alongside the tests themselves.

## Test Layers

Perseus MCP uses several complementary verification layers:

1. Pytest verifies server behavior and regressions.
2. Package tests inspect repository metadata, notebooks, documentation assets,
   and workflow expectations.
3. The package workflow builds and validates the actual wheel and source
   distribution.
4. The GitHub Actions matrix runs tests across supported Python versions and
   operating systems.
5. The secret scan blocks tracked OpenRouter credential patterns.
6. Release and publication workflows repeat package and version validation
   before publishing.

No single layer replaces the others. Unit tests can pass while an isolated
package build fails, and a package can build while a required repository asset
or security policy is missing.

## Pytest Configuration

Configuration is defined in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = [".", "src"]
testpaths = ["tests"]
```

The package source is available without installing a wheel, and discovery is
limited to this directory.

## Test Module Responsibilities

| Test module | Responsibility |
| --- | --- |
| `test_author_resources.py` | CTS author/work/resource parsing and merged-author behavior |
| `test_disk_cache.py` | Atomic cache writes, disabling, cleanup, and concurrent writers |
| `test_exploration_tools.py` | Discovery, navigation, cache tools, author scope, and structured responses |
| `test_greek_query_normalization.py` | Unicode Greek, Beta Code, search parameters, and operators |
| `test_limits_and_language.py` | Result limits, paging bounds, and language aliases |
| `test_packaging.py` | Metadata, dependencies, documentation assets, notebooks, and workflows |
| `test_scaife_urls.py` | Safe Scaife URLs and CTS URN percent encoding |
| `test_shared_http_client.py` | Connection reuse, event loops, shutdown, and HTTP errors |
| `test_xml_hardening.py` | Safe XML parsing and entity-attack rejection |

Place new tests in the module closest to the behavior under test. Create a new
module when a feature forms a distinct subsystem rather than extending an
existing concern.

## Regression Tests

A bug fix should include the smallest test that reproduces the original
failure. A useful regression test:

- fails before the fix;
- passes after the fix;
- asserts externally observable behavior where possible;
- covers the relevant boundary or failure condition;
- does not rely on timing or mutable upstream data.

## Upstream Isolation

Routine tests do not call live Perseus or Scaife endpoints. HTTP helpers are
monkeypatched with asynchronous test doubles, and representative XML or JSON is
embedded in fixtures.

This keeps the suite:

- deterministic when upstream catalogs change;
- independent of network availability;
- respectful of public scholarly infrastructure;
- able to test malformed, partial, and hostile responses safely.

Live read-only probes may be used during manual review for endpoint
compatibility or connection-lifecycle changes. They supplement the automated
suite and should not become required CI dependencies.

## Async Client Isolation

Tests frequently call asynchronous tools with `asyncio.run()`. Each invocation
creates a fresh event loop, while the server maintains a process-wide shared
`httpx.AsyncClient`.

The autouse fixture in `conftest.py` closes the shared client after every test:

```python
@pytest.fixture(autouse=True)
def _close_shared_http_client_after_test():
    yield
    if server._HTTP_CLIENT is not None:
        asyncio.run(server.aclose_http_client())
```

This prevents event-loop and connection state from leaking between tests and
avoids unclosed-resource warnings. Tests that directly replace or manipulate
the shared client must leave the global state reset.

## Running the Suite

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run all tests:

```bash
python -m pytest
```

Run one module or one test:

```bash
python -m pytest tests/test_disk_cache.py
python -m pytest tests/test_disk_cache.py::test_disk_cache_set_writes_readable_content
```

Show skipped tests, slow tests, and local variables:

```bash
python -m pytest -ra --durations=10 -l
```

With `uv`:

```bash
uv run --extra dev pytest
```

Run without metadata-cache reads and writes:

```bash
PERSEUS_MCP_DISABLE_CACHE=1 python -m pytest
```

PowerShell:

```powershell
$env:PERSEUS_MCP_DISABLE_CACHE = "1"
python -m pytest
```

## GitHub Actions Workflows

Workflow definitions under `.github/workflows/` are the executable source of
truth for CI triggers, matrices, permissions, and commands.

### Tests

`tests.yml` installs the editable project with development dependencies and
runs `python -m pytest` on:

- Ubuntu and Windows;
- Python 3.11, 3.12, and 3.13.

The matrix sets `fail-fast: false`, allowing every job to finish when one
combination fails. This exposes all affected platforms and versions in a single
run. Changes limited to `docs/**` do not trigger the Python test workflow.

### Package build

`package.yml` uses Python 3.12 to:

1. install `build` and `twine`;
2. run `python -m build`;
3. run `python -m twine check dist/*`;
4. upload `dist/` as the `python-package` artifact.

It is path-filtered to package-relevant files and supports manual dispatch.

Reproduce this locally with:

```bash
python -m build
python -m twine check dist/*
```

### Secret scan

`secret-scan.yml` checks tracked files for OpenRouter keys matching:

```text
sk-or-v1-[A-Za-z0-9_-]{20,}
```

The workflow reports affected filenames without printing the secret. Remove
and rotate any detected credential; do not bypass the check.

### Release build

`release.yml` runs for `v*` tags or manual dispatch. A tag run:

1. reads `project.version` from `pyproject.toml`;
2. requires the tag to equal `v<project.version>`;
3. builds and validates the wheel and source distribution;
4. attaches the artifacts to a generated GitHub release;
5. dispatches the PyPI workflow using the same tag.

### PyPI publication

`publish.yml` requires a tag reference, repeats the tag/version check, rebuilds
and revalidates the package, and publishes with PyPI trusted publishing.

The protected `pypi` environment uses OIDC through `id-token: write`; no
long-lived PyPI API token is stored. Rebuilding prevents publication from
trusting an unrelated workflow artifact.

### Documentation deployment

`pages.yml` builds `docs/` with Jekyll and deploys the generated artifact after
documentation changes reach `main` or `master`. GitHub Pages is intended
primarily for end users; developer test documentation remains in the repository
README and this file.

## Adding Tests

When changing behavior:

1. reproduce the failure or boundary condition;
2. prefer local XML/JSON fixtures over live services;
3. assert the public response, exception, request parameters, or state change;
4. cover both the successful and failing path when relevant;
5. run the affected module while developing;
6. run the complete suite before opening a pull request;
7. build the package when metadata, dependencies, manifests, README content, or
   distribution contents change.

For cross-platform code, avoid assumptions about path separators, temporary
directories, file permissions, read-only attributes, or event-loop behavior.

## Interpreting Failures

- Failure across all matrix jobs usually indicates a general regression.
- Failure on one Python version suggests version-specific syntax, dependency,
  or standard-library behavior.
- Windows-only failure commonly involves paths, permissions, read-only
  attributes, or event-loop lifecycle.
- Package failure with green pytest jobs usually concerns metadata, manifests,
  README rendering, or build isolation.
- Secret-scan failure requires credential removal and rotation.
- Release failure before publication commonly means the tag and
  `project.version` differ.

Understand the cause before rerunning a failed job. Preserve relevant tracebacks
or workflow logs in the pull request when the diagnosis is not obvious.
