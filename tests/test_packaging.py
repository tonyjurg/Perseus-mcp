from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import sys
import tomllib
from pathlib import Path

import perseus_mcp
from perseus_mcp import server as package_server


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
DEPENDABOT_CONFIG = REPO_ROOT / ".github" / "dependabot.yml"
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


def test_repository_launcher_aliases_packaged_server_module() -> None:
    sys.modules.pop("server", None)
    root_server = importlib.import_module("server")

    assert root_server is package_server
    assert root_server.mcp is package_server.mcp


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
