"""Compare live CTS envelopes with the captured manifest; never update fixtures."""

import argparse
import asyncio
import html
import json
import os
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from perseus_mcp import server
from perseus_mcp.upstream import UpstreamFailure, validate_cts

DEFAULT_MANIFEST = (
    Path(__file__).resolve().parents[1] / "tests/fixtures/cts/sources.json"
)


async def check_sources(manifest: dict) -> list[dict]:
    results = []
    for source in manifest["responses"]:
        result = {
            "operation": source["operation"],
            "url": source["url"],
            "expected_root": source["root"],
            "observed_root": None,
            "ok": False,
        }
        try:
            # Use the bounded transport, bypassing metadata caches. A total
            # deadline also bounds endpoints that send a slow trickle of data.
            body = await asyncio.wait_for(server._get(source["url"]), timeout=60)
            root = fromstring(body)
            result["observed_root"] = root.tag
            validate_cts(body, source["operation"])
            # Expanded XML names compare both local root and namespace URI;
            # merely changing the prefix does not count as drift.
            result["ok"] = root.tag == source["root"]
            if not result["ok"]:
                result["error"] = "ROOT_OR_NAMESPACE_CHANGED"
        except UpstreamFailure as exc:
            result["error"] = exc.code
            result["upstream_http_status"] = exc.status
        except (ET.ParseError, DefusedXmlException):
            result["error"] = "INVALID_PAYLOAD"
        except TimeoutError:
            result["error"] = "UPSTREAM_TIMEOUT"
        results.append(result)
    return results


async def run(manifest: dict) -> list[dict]:
    try:
        return await check_sources(manifest)
    finally:
        await server.aclose_http_client()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    results = asyncio.run(run(manifest))
    report = json.dumps(
        {
            "checked_at": datetime.now(UTC).isoformat(),
            "baseline_captured": manifest["captured"],
            "results": results,
        },
        indent=2,
    )
    print(report)
    if args.report:
        args.report.write_text(report + "\n", encoding="utf-8")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(
                "## Live CTS format check\n\n<pre>" + html.escape(report) + "</pre>\n"
            )
    return 0 if all(result["ok"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
