"""Guard security floors, reproducible artifacts, and upstream advisory coverage."""

import ast
import json
import sys
import tomllib
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest
from packaging.requirements import Requirement

from scripts import check_fastmcp_advisories as audit

ROOT = Path(__file__).resolve().parents[1]


def schema_rce_advisory():
    return {
        "ghsa_id": "GHSA-gpgx-58w2-xwwf",
        "cve_id": None,
        "severity": "critical",
        "html_url": "https://github.com/PrefectHQ/fastmcp/security/advisories/GHSA-gpgx-58w2-xwwf",
        "vulnerabilities": [
            {
                "package": {"name": "fastmcp", "ecosystem": "pip"},
                "vulnerable_version_range": ">=2.10.0,<3.4.8",
            },
            {
                "package": {"name": "fastmcp", "ecosystem": "pip"},
                "vulnerable_version_range": ">=4.0.0a1,<4.0.11",
            },
        ],
    }


@pytest.mark.parametrize(
    "version,vulnerable",
    [
        ("3.4.2", True),
        ("3.4.8", False),
        ("4.0.0a1", True),
        ("4.0.10", True),
        ("4.0.11", False),
        ("4.2.3", False),
    ],
)
def test_cveless_advisory_catches_both_affected_release_lines(version, vulnerable):
    matches = audit.matching_advisories([schema_rce_advisory()], {("fastmcp", version)})
    assert bool(matches) is vulnerable
    if matches:
        assert matches[0]["advisory"] == "GHSA-gpgx-58w2-xwwf"


def test_withdrawn_advisory_is_not_a_current_finding():
    advisory = schema_rce_advisory() | {"withdrawn_at": "2026-11-20"}
    assert audit.matching_advisories([advisory], {("fastmcp", "3.4.2")}) == []


def test_installed_versions_cannot_hide_behind_a_safe_lock(monkeypatch, tmp_path):
    lock = tmp_path / "uv.lock"
    lock.write_text(
        '[[package]]\nname="fastmcp"\nversion="4.2.3"\n[[package]]\nname="fastmcp-slim"\nversion="4.2.3"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(audit.importlib.metadata, "version", lambda name: "3.4.2")
    versions = audit.checked_versions(lock)
    assert ("fastmcp", "3.4.2") in versions
    assert ("fastmcp", "4.2.3") in versions
    assert audit.matching_advisories([schema_rce_advisory()], versions)


def test_upstream_feed_pagination_and_authorization(monkeypatch):
    pages = [[schema_rce_advisory()] * 100, [schema_rce_advisory()]]
    requests = []

    def response(request, timeout):
        requests.append(request)
        assert timeout == 30
        return BytesIO(json.dumps(pages[len(requests) - 1]).encode())

    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setattr(audit, "urlopen", response)
    assert len(audit.published_advisories()) == 101
    assert requests[1].full_url.endswith("page=2")
    assert requests[0].get_header("Authorization") == "Bearer test-token"


@pytest.mark.parametrize("body", [[], {"message": "unavailable"}])
def test_empty_or_invalid_upstream_feed_cannot_pass(monkeypatch, body):
    monkeypatch.setattr(
        audit, "urlopen", lambda *args, **kwargs: BytesIO(json.dumps(body).encode())
    )
    with pytest.raises((ValueError, TypeError)):
        audit.published_advisories()


def test_incomplete_advisory_check_returns_failure(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["check_fastmcp_advisories.py"])
    monkeypatch.setattr(audit, "checked_versions", lambda path: {("fastmcp", "4.2.3")})

    def unavailable():
        raise HTTPError(audit.API, 403, "rate limited", {}, None)

    monkeypatch.setattr(audit, "published_advisories", unavailable)
    assert audit.main() == 2
    assert "could not complete" in capsys.readouterr().err


@pytest.mark.parametrize(
    "package,bad,good",
    [
        ("fastmcp", "3.4.2", "4.2.3"),
        ("fastmcp", "4.0.11", "4.2.3"),
        ("anyio", "4.14.0", "4.14.2"),
        ("certifi", "2026.6.17", "2026.10.19"),
        ("cryptography", "49.0.0", "50.0.0"),
        ("dnspython", "2.9.0", "2.9.2"),
        ("pydantic-settings", "2.14.1", "2.14.2"),
        ("pyjwt", "2.13.0", "2.15.0"),
    ],
)
def test_published_requirements_reject_known_vulnerable_versions(package, bad, good):
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = {
        Requirement(line).name.lower(): Requirement(line)
        for line in project["project"]["dependencies"]
    }
    assert bad not in requirements[package].specifier
    assert good in requirements[package].specifier
    if package == "fastmcp":
        assert "5.0.0" not in requirements[package].specifier


def test_portable_lock_has_reviewable_public_artifacts_and_hashes():
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    for package in lock["package"]:
        if package["name"] == "perseus-mcp":
            assert package["source"] == {"editable": "."}
            continue
        assert package["source"] == {"registry": "https://pypi.org/simple"}
        artifacts = package.get("wheels", []) + (
            [package["sdist"]] if "sdist" in package else []
        )
        assert artifacts, package["name"]
        assert all(artifact["hash"].startswith("sha256:") for artifact in artifacts)


def test_server_does_not_import_model_provider_sdks_or_enable_their_extras():
    for path in (ROOT / "src/perseus_mcp").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                assert all(
                    alias.name.split(".")[0] not in {"openai", "anthropic"}
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in {"openai", "anthropic"}
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for dependency in project["project"]["dependencies"]:
        requirement = Requirement(dependency)
        assert requirement.name.lower() not in {"openai", "anthropic"}
        if requirement.name.lower() == "fastmcp":
            assert not requirement.extras
