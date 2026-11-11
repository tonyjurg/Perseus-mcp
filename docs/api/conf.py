"""Build the API reference from this checkout and its declared package version."""

import json
import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(os.environ.get("PERSEUS_DOCS_SOURCE", Path(__file__).resolve().parents[2]))
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
html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "collapse_navigation": False,
    "navigation_depth": 2,
    "sticky_navigation": True,
    "titles_only": True,
    "style_nav_header_background": "#20394b",
    "logo_only": True,
}
html_logo = "_static/perseus-logo.png"
html_favicon = "_static/perseus-logo.png"
docs_version = os.environ.get("PERSEUS_DOCS_VERSION", "Current (main)")
html_title = f"{project} — {docs_version}"
templates_path = ["_templates"]
html_static_path = ["_static"]
html_css_files = ["perseus.css"]
html_context = {
    "docs_version": docs_version,
    "docs_versions": json.loads(os.environ.get("PERSEUS_DOCS_VERSIONS", "[]")),
}
rst_prolog = f".. |docs_version| replace:: {docs_version}\n"
exclude_patterns = ["_build"]
