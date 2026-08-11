from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import re
import tomllib
from pathlib import Path

import perseus_mcp
from perseus_mcp import server as package_server


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
DEPENDABOT_CONFIG = REPO_ROOT / ".github" / "dependabot.yml"
CODEQL_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "codeql.yml"
DEPENDENCY_REVIEW_WORKFLOW = (
    REPO_ROOT / ".github" / "workflows" / "dependency-review.yml"
)
ENDUSER_GUIDE = REPO_ROOT / "docs" / "enduser.md"
PUBLISH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish.yml"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
MCP_NOTEBOOKS = sorted((REPO_ROOT / "examples").glob("0[3-9]_*.ipynb")) + sorted(
    (REPO_ROOT / "examples").glob("10_*.ipynb")
)


def test_package_metadata_and_console_entry_point() -> None:
    metadata = importlib.metadata.metadata("perseus-mcp")
    entry_points = {
        entry_point.name: entry_point.value
        for entry_point in importlib.metadata.entry_points(group="console_scripts")
    }

    assert metadata["Name"] == "perseus-mcp"
    assert metadata["Version"] == perseus_mcp.__version__
    assert entry_points["perseus-mcp"] == "perseus_mcp.server:main"


def test_pyproject_uses_src_layout_and_declares_build_tools() -> None:
    configuration = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    assert configuration["project"]["name"] == "perseus-mcp"
    assert configuration["project"]["scripts"]["perseus-mcp"] == (
        "perseus_mcp.server:main"
    )
    assert configuration["tool"]["setuptools"]["package-dir"] == {"": "src"}
    assert configuration["tool"]["setuptools"]["packages"]["find"]["where"] == [
        "src"
    ]
    assert {"build>=1.2", "twine>=6.0"} <= set(
        configuration["project"]["optional-dependencies"]["dev"]
    )


def test_core_dependencies_are_actually_used_by_the_package() -> None:
    configuration = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    dependency_names = {
        dependency.split(">=")[0].split("==")[0].strip()
        for dependency in configuration["project"]["dependencies"]
    }

    # Everything the package imports at runtime must be declared...
    assert {"fastmcp", "httpx"} <= dependency_names
    # ...and python-dotenv must not reappear as a core dependency: it is not
    # imported anywhere under src/perseus_mcp, only used by example
    # notebooks, which already install it themselves via their own
    # `%pip install` cell.
    assert "python-dotenv" not in dependency_names


def test_main_runs_registered_mcp_server(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(package_server.mcp, "run", lambda: calls.append("run"))

    package_server.main()

    assert calls == ["run"]


def test_package_module_entry_point_exists() -> None:
    specification = importlib.util.find_spec("perseus_mcp.__main__")

    assert specification is not None
    assert specification.origin is not None
    assert specification.origin.endswith("__main__.py")


def test_no_legacy_root_server_launcher_exists() -> None:
    assert not (REPO_ROOT / "server.py").exists()


def test_mcp_notebooks_import_the_packaged_server() -> None:
    assert len(MCP_NOTEBOOKS) == 8

    for notebook_path in MCP_NOTEBOOKS:
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        code = "\n".join(
            "".join(cell.get("source", []))
            for cell in notebook["cells"]
            if cell.get("cell_type") == "code"
        )

        assert 'candidate / "src" / "perseus_mcp" / "server.py"' in code
        assert "from perseus_mcp import server" in code
        assert "\nimport server\n" not in f"\n{code}\n"


def test_installation_notebook_documents_supported_launch_methods() -> None:
    notebook_path = (
        REPO_ROOT / "examples" / "00_install_and_run_perseus_mcp.ipynb"
    )
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    content = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )

    assert notebook["nbformat"] == 4
    assert "python -m pip install perseus-mcp" in content
    assert "uv tool install perseus-mcp" in content
    assert "uv --directory /full/path/to/Perseus-mcp run perseus-mcp" in content
    assert '"args": ["-m", "perseus_mcp"]' in content
    assert "npx @modelcontextprotocol/inspector perseus-mcp" in content


def test_dependabot_tracks_python_and_github_actions_dependencies() -> None:
    configuration = DEPENDABOT_CONFIG.read_text(encoding="utf-8")

    assert configuration.startswith("version: 2")
    assert 'package-ecosystem: "pip"' in configuration
    assert 'package-ecosystem: "github-actions"' in configuration
    assert configuration.count('interval: "weekly"') == 2
    assert configuration.count('directory: "/"') == 2
    # Dependabot creates its default labels when needed. Custom labels must
    # already exist, otherwise every update PR gets a configuration warning.
    assert "labels:" not in configuration


def test_codeql_scans_code_and_workflows_with_quality_queries() -> None:
    workflow = CODEQL_WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "schedule:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "language: actions" in workflow
    assert "language: python" in workflow
    assert "query_suite: security-and-quality" in workflow


def test_dependency_review_checks_every_pull_request() -> None:
    workflow = DEPENDENCY_REVIEW_WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "paths:" not in workflow
    assert re.search(
        r"^\s*-\s+uses:\s+actions/dependency-review-action@v[1-9]\d*\s*$",
        workflow,
        flags=re.MULTILINE,
    )
    assert "fail-on-severity: moderate" in workflow


def test_rate_limit_guidance_is_documented() -> None:
    guide = ENDUSER_GUIDE.read_text(encoding="utf-8").casefold()
    notebook = (
        REPO_ROOT / "examples" / "00_install_and_run_perseus_mcp.ipynb"
    ).read_text(encoding="utf-8").casefold()

    for content in (guide, notebook):
        assert "429" in content
        assert "rate limit" in content or "too many requests" in content
        assert "retry" in content


def test_openrouter_notebooks_use_free_models_router_by_default() -> None:
    for notebook_name in (
        "06_openrouter_llm_mcp_interaction.ipynb",
        "09_openrouter_philo_politeia_analysis.ipynb",
    ):
        notebook_path = (
            REPO_ROOT / "examples" / notebook_name
        )
        notebook_json = notebook_path.read_text(encoding="utf-8")
        notebook = json.loads(notebook_json)
        content = "\n".join(
            "".join(cell.get("source", [])) for cell in notebook["cells"]
        )

        assert "OPENROUTER_MODEL=openrouter/free" in content
        assert '"openrouter/free"' in content
        assert "resolved_model" in content
        assert "nvidia/nemotron" not in content

    tool_notebook = json.loads(
        (
            REPO_ROOT / "examples" / "06_openrouter_llm_mcp_interaction.ipynb"
        ).read_text(encoding="utf-8")
    )
    analysis_notebook = json.loads(
        (
            REPO_ROOT
            / "examples"
            / "09_openrouter_philo_politeia_analysis.ipynb"
        ).read_text(encoding="utf-8")
    )
    tool_content = "\n".join(
        "".join(cell.get("source", [])) for cell in tool_notebook["cells"]
    )
    analysis_content = "\n".join(
        "".join(cell.get("source", []))
        for cell in analysis_notebook["cells"]
    )

    assert '"supports_tools": True' in tool_content
    assert '"tools": tools' in tool_content
    assert '"response_format"' in analysis_content
    assert "different concrete models" in tool_content
    assert "exact model reproducibility" in analysis_content


def test_release_workflow_builds_assets_and_dispatches_publish() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert 'tags:\n      - "v*"' in workflow
    assert "python -m build" in workflow
    assert "python -m twine check dist/*" in workflow
    assert "softprops/action-gh-release@v3" in workflow
    assert "actions/workflows/publish.yml/dispatches" in workflow
    assert 'expected_tag = f"v{version}"' in workflow


def test_publish_workflow_uses_pypi_trusted_publishing() -> None:
    workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

    assert "environment: pypi" in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "python -m build" in workflow
    assert "python -m twine check dist/*" in workflow
    assert 'expected_tag = f"v{version}"' in workflow
    assert 'ref.startswith("refs/tags/v")' in workflow
    assert "password:" not in workflow
