"""Backward-compatible launcher for repository checkouts.

Installed users should run the ``perseus-mcp`` command or
``python -m perseus_mcp``.
"""

from __future__ import annotations

import sys

from perseus_mcp import server as _implementation


if __name__ == "__main__":
    _implementation.main()
else:
    # Preserve existing imports and monkeypatch behavior used by the notebooks
    # and tests while the implementation lives in the installable package.
    sys.modules[__name__] = _implementation
