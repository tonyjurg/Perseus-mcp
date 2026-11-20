"""Check installed and locked FastMCP versions against upstream's published advisories."""

import argparse
import importlib.metadata
import json
import os
import sys
import tomllib
from pathlib import Path
from urllib.request import Request, urlopen

from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

API = "https://api.github.com/repos/PrefectHQ/fastmcp/security-advisories"
PACKAGES = {"fastmcp", "fastmcp-slim"}
DEFAULT_LOCK = Path(__file__).resolve().parents[1] / "uv.lock"


def published_advisories() -> list[dict]:
    """Read every public advisory page; fail if the feed cannot be checked."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "perseus-dependency-audit",
    }
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    advisories = []
    for page in range(1, 11):
        request = Request(f"{API}?per_page=100&page={page}", headers=headers)
        with urlopen(request, timeout=30) as response:
            body = response.read(8 * 1024 * 1024 + 1)
        if len(body) > 8 * 1024 * 1024:
            raise ValueError("Upstream advisory page exceeds the size limit")
        batch = json.loads(body)
        if not isinstance(batch, list):
            raise TypeError("Unexpected upstream advisory response")
        advisories.extend(batch)
        if len(batch) < 100:
            if not advisories:
                raise ValueError(
                    "The upstream advisory feed is empty; review it manually"
                )
            return advisories
    raise ValueError("Upstream advisory pagination limit exceeded")


def checked_versions(lock_path: Path) -> set[tuple[str, str]]:
    """Include the actual environment and every FastMCP version in the portable lock."""
    versions = {(name, importlib.metadata.version(name)) for name in PACKAGES}
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    locked = {
        (canonicalize_name(package["name"]), package["version"])
        for package in lock["package"]
        if canonicalize_name(package["name"]) in PACKAGES
    }
    if {name for name, version in locked} != PACKAGES:
        raise ValueError("The lockfile must contain fastmcp and fastmcp-slim")
    return versions | locked


def matching_advisories(
    advisories: list[dict], versions: set[tuple[str, str]]
) -> list[dict]:
    """Match version ranges without depending on CVE assignment or OSV ingestion."""
    matches = []
    for advisory in advisories:
        if advisory.get("withdrawn_at"):
            continue
        for vulnerability in advisory["vulnerabilities"]:
            package = vulnerability["package"]
            name = canonicalize_name(package.get("name") or "fastmcp")
            if name not in PACKAGES or package.get("ecosystem", "").lower() not in {
                "pip",
                "pypi",
                "",
            }:
                continue
            affected = SpecifierSet(vulnerability["vulnerable_version_range"])
            for installed_name, version in sorted(versions):
                if installed_name == name and affected.contains(
                    version, prereleases=True
                ):
                    matches.append(
                        {
                            "package": name,
                            "version": version,
                            "advisory": advisory["ghsa_id"],
                            "severity": advisory["severity"],
                            "url": advisory["html_url"],
                        }
                    )
    return matches


def main() -> int:
    """Exit one for vulnerable versions and two when a complete check is unavailable."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    args = parser.parse_args()
    try:
        versions = checked_versions(args.lock)
        advisories = published_advisories()
        matches = matching_advisories(advisories, versions)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        importlib.metadata.PackageNotFoundError,
    ) as exc:
        print(f"FastMCP advisory check could not complete: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "checked_versions": sorted(versions),
                "upstream_advisories": len(advisories),
                "matches": matches,
            },
            indent=2,
        )
    )
    return int(bool(matches))


if __name__ == "__main__":
    raise SystemExit(main())
