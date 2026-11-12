"""Run regression checks against an isolated local Git ref, without publishing."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import tomllib


def main():
    """Resolve a ref, create a disposable environment, and fail on any failed check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ref", default="main", help="Local branch, tag, or commit (default: main)"
    )
    parser.add_argument(
        "--focused",
        action="store_true",
        help="Run a focused subset instead of the full suite",
    )
    parser.add_argument(
        "--live", action="store_true", help="Also check live Perseus passage retrieval"
    )
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required")
    REPO = next(
        (
            p
            for p in [
                Path(__file__).resolve().parent,
                *Path(__file__).resolve().parents,
            ]
            if (p / "pyproject.toml").is_file() and (p / ".git").exists()
        ),
        None,
    )
    assert REPO is not None, "Run this script inside the Perseus-mcp checkout."

    def capture(args, cwd=REPO):
        return subprocess.check_output(
            args, cwd=cwd, text=True, encoding="utf-8", timeout=60
        ).strip()

    COMMIT = capture(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{args.ref}^{{commit}}"]
    )
    print(f"Ref: {args.ref}\nCommit: {COMMIT}\nSource repository: {REPO}", flush=True)
    with tempfile.TemporaryDirectory(prefix="perseus-regression-") as temporary:
        ROOT = Path(temporary)
        CHECKOUT = ROOT / "source"
        subprocess.run(
            [
                "git",
                "clone",
                "--local",
                "--quiet",
                "--no-hardlinks",
                "--no-checkout",
                str(REPO),
                str(CHECKOUT),
            ],
            check=True,
            timeout=120,
        )
        subprocess.run(
            ["git", "checkout", "--quiet", "--detach", COMMIT],
            cwd=CHECKOUT,
            check=True,
            timeout=60,
        )
        assert capture(["git", "rev-parse", "HEAD"], CHECKOUT) == COMMIT
        assert not capture(["git", "status", "--porcelain"], CHECKOUT)
        metadata = tomllib.loads(
            (CHECKOUT / "pyproject.toml").read_text(encoding="utf-8")
        )
        print("Package version:", metadata["project"]["version"])
        print("Isolated source:", CHECKOUT, flush=True)
        print("Creating isolated Python environment...", flush=True)

        VENV = ROOT / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV)], check=True, timeout=180
        )
        PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        ENV = os.environ.copy()
        for key in list(ENV):
            if key.startswith("PERSEUS_MCP_") or key in {"PYTHONPATH", "PYTHONHOME"}:
                ENV.pop(key)
        ENV["PERSEUS_MCP_CACHE_DIR"] = str(ROOT / "cache")
        ENV["PYTHONIOENCODING"] = "utf-8"
        ENV["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

        def run_python(args, timeout=180):
            print(
                "Running:",
                "inline MCP check" if args[0] == "-c" else " ".join(args[:2]),
                flush=True,
            )
            result = subprocess.run(
                [str(PYTHON), *args],
                cwd=CHECKOUT,
                env=ENV,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
            print(result.stdout, flush=True)
            result.check_returncode()
            return result

        run_python(
            [
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-e",
                str(CHECKOUT) + "[dev]",
            ],
            timeout=600,
        )
        print("PASS: tagged package installed into its own environment")

        SMOKE = r"""
        import asyncio
        import importlib.metadata
        import json
        from pathlib import Path
        from fastmcp import Client
        import perseus_mcp
        from perseus_mcp import server

        expected = Path.cwd() / "src" / "perseus_mcp"
        assert Path(perseus_mcp.__file__).resolve().is_relative_to(expected.resolve())
        print("Imported:", perseus_mcp.__file__)
        print("Installed version:", importlib.metadata.version("perseus-mcp"))

        async def check():
            async with Client(server.mcp) as client:
                tools = await client.list_tools()
                expected_tools = json.loads(Path("tests/fixtures/server_api.json").read_text())
                assert {t.name for t in tools} == set(expected_tools)
                result = await client.call_tool("get_cache_status", {})
                assert not result.is_error
                text = "".join(item.text for item in result.content if hasattr(item, "text"))
                assert isinstance(json.loads(text), dict)
                print(f"PASS: {len(tools)} MCP tools and cache-status round trip")
            await server.aclose_http_client()

        asyncio.run(check())
        """
        run_python(["-c", textwrap.dedent(SMOKE)])

        focused = [
            "tests/test_module_compatibility.py",
            "tests/test_greek_query_normalization.py",
            "tests/test_cts_live_fixtures.py",  # Recorded fixtures, not live HTTP calls.
            "tests/test_packaging.py",
        ]
        run_python(
            ["-m", "pytest", "-q", *(["tests"] if not args.focused else focused)],
            timeout=600,
        )
        print("PASS: offline regression checks")

        if args.live:
            LIVE = r"""
        import asyncio
        from fastmcp import Client
        from perseus_mcp import server

        async def check():
            try:
                async with Client(server.mcp) as client:
                    result = await client.call_tool("get_passage_plaintext", {
                        "urn": "urn:cts:greekLit:tlg0012.tlg001:1.1"
                    })
                    assert not result.is_error
                    text = "".join(item.text for item in result.content if hasattr(item, "text"))
                    assert text.strip(), "Empty passage response"
                    assert "μῆνιν" in text.casefold(), f"Unexpected passage: {text[:300]}"
                    print(text[:500])
                    print("PASS: live Iliad passage")
            finally:
                await server.aclose_http_client()

        asyncio.run(check())
        """
            run_python(["-c", textwrap.dedent(LIVE)], timeout=240)
        else:
            print("SKIPPED: live retrieval (args.live=False)")
    print(f"PASS: regression checks for {args.ref} ({COMMIT})")


if __name__ == "__main__":
    main()
