"""Perseus MCP package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("perseus-mcp")
except PackageNotFoundError:
    __version__ = "1.0.1"

__all__ = ["__version__"]
