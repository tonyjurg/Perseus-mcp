"""Compare live CTS envelopes with the captured manifest; never update fixtures."""

import argparse
import asyncio
import hashlib
import html
import json
import math
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
FORMAT_FAILURES = {"ROOT_OR_NAMESPACE_CHANGED", "INVALID_PAYLOAD"}


async def check_sources(manifest: dict, *, interval: float = 0) -> list[dict]:
    results = []
    for index, source in enumerate(manifest["responses"] + manifest.get("probes", [])):
        if index and interval:
            await asyncio.sleep(interval)
        result = {
            "operation": source["operation"],
            "url": source["url"],
            "expected_root": source.get("root"),
            "expected_local_root": source.get("local_root"),
            "observed_root": None,
            "ok": False,
        }
        try:
            # Use the bounded transport, bypassing metadata caches. A total
            # deadline also bounds endpoints that send a slow trickle of data.
            # Inspect HTML here too: the default plaintext validator rejects it
            # before we can identify the previously captured broken probe page.
            # The transport still enforces challenges, HTTP errors and limits.
            body = await asyncio.wait_for(
                server._get(source["url"], validator=server.reject_challenge),
                timeout=60,
            )
            if "root" not in source and source.get("known_invalid_sha256"):
                # Ignore only this reviewed payload on probes without a valid
                # baseline. New invalid payloads and captured responses fail.
                digest = hashlib.sha256(
                    body.replace("\r\n", "\n").strip().encode("utf-8")
                ).hexdigest()
                if digest == source["known_invalid_sha256"]:
                    raise UpstreamFailure(
                        "KNOWN_UPSTREAM_INVALID_PAYLOAD",
                        "The upstream probe returned its recorded malformed page; "
                        "no usable CTS format was observed.",
                    )
            root = fromstring(body)
            result["observed_root"] = root.tag
            validate_cts(body, source["operation"])
            # Expanded XML names compare both local root and namespace URI;
            # merely changing the prefix does not count as drift.
            if "root" in source:
                result["ok"] = root.tag == source["root"]
            else:
                # Additional probes have no captured successful envelope yet.
                # Require their operation root without inventing a namespace.
                result["ok"] = root.tag.rsplit("}", 1)[-1] == source["local_root"]
            if not result["ok"]:
                result["error"] = "ROOT_OR_NAMESPACE_CHANGED"
        except UpstreamFailure as exc:
            result["error"] = exc.code
            result["upstream_http_status"] = exc.status
        except (ET.ParseError, DefusedXmlException):
            result["error"] = "INVALID_PAYLOAD"
        except TimeoutError:
            result["error"] = "UPSTREAM_TIMEOUT"
        result["outcome"] = (
            "ok"
            if result["ok"]
            else "failed"
            if result["error"] in FORMAT_FAILURES
            else "inconclusive"
        )
        results.append(result)
    return results


async def run(manifest: dict, *, interval: float = 0) -> list[dict]:
    try:
        return await check_sources(manifest, interval=interval)
    finally:
        await server.aclose_http_client()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--interval",
        type=float,
        default=1,
        help="Seconds between endpoint probes (default: 1; 0 disables pacing).",
    )
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval < 0:
        parser.error("--interval must be a nonnegative finite number")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    results = asyncio.run(run(manifest, interval=args.interval))
    failures = sum(result["outcome"] == "failed" for result in results)
    inconclusive = sum(result["outcome"] == "inconclusive" for result in results)
    outcome = "failed" if failures else "inconclusive" if inconclusive else "ok"
    report = json.dumps(
        {
            "checked_at": datetime.now(UTC).isoformat(),
            "baseline_captured": manifest["captured"],
            "outcome": outcome,
            "failed": failures,
            "inconclusive": inconclusive,
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
                f"## Live CTS format check: {outcome.upper()}\n\n<pre>"
                + html.escape(report)
                + "</pre>\n"
            )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
