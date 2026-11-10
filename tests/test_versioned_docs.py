"""Check historical API discovery and version-selector destinations."""

import json
from pathlib import Path

from scripts import build_api_docs as docs


def test_tag_directories_are_safe_and_distinct():
    """Ordinary release URLs stay readable; unusual tags cannot traverse paths."""
    assert docs.tag_directory("v1.0.2") == "v1.0.2"
    unusual = ["../release", "release/candidate", "release-candidate", "CURRENT"]
    paths = [docs.tag_directory(tag) for tag in unusual]
    assert len(set(paths)) == len(paths)
    assert all("/" not in path and ".." not in path for path in paths)


def test_historical_reference_uses_only_that_revisions_definitions(tmp_path):
    """A monolithic tag must not acquire today's modules or imported API members."""
    package = tmp_path / "src/perseus_mcp"
    package.mkdir(parents=True)
    (package / "server.py").write_text(
        'from fastmcp import FastMCP\n\nasync def old_tool(urn):\n    """Old API."""\n',
        encoding="utf-8",
    )
    reference = docs.module_reference(tmp_path)
    assert ".. automodule:: perseus_mcp.server" in reference
    assert ":members: old_tool" in reference
    assert "FastMCP" not in reference
    assert "perseus_mcp.tools" not in reference


def test_selector_links_resolve_from_current_and_tagged_static_directories(
    tmp_path, monkeypatch
):
    """Switching versions works from nested pages and on a local file preview."""
    current = tmp_path / "api"
    tagged = current / "versions/v1.0.2"
    entries = [
        {"label": "Current (main)", "output": current},
        {"label": "v1.0.2", "output": tagged},
    ]
    calls = []
    monkeypatch.setattr(
        docs.subprocess, "run", lambda *args, **kwargs: calls.append(kwargs)
    )
    for output in (current, tagged):
        docs.build(
            tmp_path, tmp_path / "docs", output, Path("python"), "selected", entries
        )
        env = calls[-1]["env"]
        assert env["PERSEUS_DOCS_SOURCE"] == str(tmp_path)
        assert env["PERSEUS_DOCS_VERSION"] == "selected"
        choices = json.loads(env["PERSEUS_DOCS_VERSIONS"])
        for choice, entry in zip(choices, entries, strict=True):
            assert choice["label"] == entry["label"]
            assert (output / "_static" / choice["relative_url"]).resolve() == (
                entry["output"] / "index.html"
            ).resolve()
