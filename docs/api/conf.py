"""Build the API reference from this checkout and its declared package version."""

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

project = "Perseus MCP"
author = "Tony Jurg"
release = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
    "project"
]["version"]
version = release
extensions = ["sphinx.ext.autodoc", "sphinx.ext.napoleon", "sphinx.ext.viewcode"]
autodoc_member_order = "bysource"
autodoc_typehints = "description"
html_theme = "alabaster"
html_title = f"{project} {release} API"
exclude_patterns = ["_build"]
