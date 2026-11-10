"""Build the current API and every tagged source revision for GitHub Pages."""

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    """Read repository metadata without invoking a shell."""
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def tag_directory(tag: str) -> str:
    """Map arbitrary tag names to stable, collision-resistant URL path segments."""
    if re.fullmatch(r"v?\d+(?:\.\d+)+(?:[-.][A-Za-z0-9.-]+)?", tag):
        return tag
    return "tag-" + hashlib.sha256(tag.encode()).hexdigest()[:16]


def module_reference(source: Path) -> str:
    """Document only modules and definitions present in the selected revision."""
    sections = ["API modules\n===========\n"]
    for path in sorted((source / "src/perseus_mcp").rglob("*.py")):
        if path.name == "__main__.py":
            continue
        parts = path.relative_to(source / "src").with_suffix("").parts
        module = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        members = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        section = f"{module}\n{'-' * (len(module) + 4)}\n\n.. automodule:: {module}\n"
        if members:
            section += "   :members: " + ", ".join(members) + "\n"
            section += "   :private-members:\n   :undoc-members:\n"
        sections.append(section)
    return "\n".join(sections)


def build(
    source: Path, docs: Path, output: Path, python: Path, label: str, entries: list
) -> None:
    """Render one revision with version links relative to its static directory."""
    versions = [
        {
            "label": entry["label"],
            "relative_url": Path(
                os.path.relpath(entry["output"] / "index.html", output / "_static")
            ).as_posix(),
        }
        for entry in entries
    ]
    env = {
        **os.environ,
        "PERSEUS_DOCS_SOURCE": str(source),
        "PERSEUS_DOCS_VERSION": label,
        "PERSEUS_DOCS_VERSIONS": json.dumps(versions),
    }
    subprocess.run(
        [
            str(python),
            "-m",
            "sphinx",
            "-E",
            "-W",
            "--keep-going",
            "-b",
            "html",
            str(docs),
            str(output),
        ],
        env=env,
        check=True,
    )


def main() -> None:
    """Build each tag in its own environment, then verify all published targets."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".cache/pages-site/api"))
    parser.add_argument(
        "--current-only",
        action="store_true",
        help="Build a quick preview without release tags.",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    tags = (
        []
        if args.current_only
        else git("tag", "--list", "--sort=-version:refname").splitlines()
    )
    entries = [
        {
            "label": "Current (main)",
            "output": output,
            "revision": git("rev-parse", "HEAD"),
        }
    ]
    entries += [
        {
            "label": tag,
            "output": output / "versions" / tag_directory(tag),
            "revision": git("rev-parse", f"refs/tags/{tag}^{{commit}}"),
        }
        for tag in tags
    ]
    build(
        ROOT,
        ROOT / "docs/api",
        output,
        Path(sys.executable),
        entries[0]["label"],
        entries,
    )
    for entry in entries[1:]:
        with tempfile.TemporaryDirectory(prefix="perseus-docs-") as temporary:
            workspace = Path(temporary)
            source = workspace / "source"
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--quiet",
                    "--no-hardlinks",
                    "--no-checkout",
                    str(ROOT),
                    str(source),
                ],
                check=True,
            )
            subprocess.run(
                ["git", "checkout", "--quiet", "--detach", entry["revision"]],
                cwd=source,
                check=True,
            )
            docs = workspace / "docs"
            shutil.copytree(ROOT / "docs/api", docs)
            # Older releases predate Sphinx and the modular architecture. Their
            # reference must come from their own definitions, not current prose.
            for page in docs.glob("*.rst"):
                page.unlink()
            (docs / "modules.rst").write_text(
                module_reference(source), encoding="utf-8"
            )
            (docs / "index.rst").write_text(
                "Perseus MCP API reference\n=========================\n\n"
                "Reference for **|docs_version|**, package version |release|.\n\n"
                "This reference describes the source at the selected tag.\n\n"
                ".. toctree::\n   :maxdepth: 2\n\n   modules\n\n"
                "* :ref:`genindex`\n* :ref:`modindex`\n",
                encoding="utf-8",
            )
            environment = workspace / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            python = environment / (
                "Scripts/python.exe" if os.name == "nt" else "bin/python"
            )
            subprocess.run(
                [str(python), "-m", "pip", "install", str(source), "sphinx>=8.2,<9"],
                check=True,
            )
            build(source, docs, entry["output"], python, entry["label"], entries)
    for entry in entries:
        if not (entry["output"] / "index.html").is_file():
            raise RuntimeError(f"Missing documentation for {entry['label']}")
    (output / "versions.json").write_text(
        json.dumps(
            [
                {
                    "label": entry["label"],
                    "path": entry["output"].relative_to(output).as_posix(),
                    "revision": entry["revision"],
                }
                for entry in entries
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
