import asyncio
import os
from pathlib import Path

import pytest

from perseus_mcp import server
from perseus_mcp.server import (
    MetadataCacheWarning,
    _cached_text,
    _disk_cache_get,
    _disk_cache_set,
)


def test_disk_cache_set_writes_readable_content(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("PERSEUS_MCP_DISABLE_CACHE", raising=False)
    path = tmp_path / "capabilities" / "abc123.xml"

    _disk_cache_set(path, "<TextInventory/>")

    assert path.read_text(encoding="utf-8") == "<TextInventory/>"
    assert _disk_cache_get(path) == "<TextInventory/>"


def test_disk_cache_set_leaves_no_leftover_temp_files(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("PERSEUS_MCP_DISABLE_CACHE", raising=False)
    path = tmp_path / "capabilities" / "abc123.xml"

    _disk_cache_set(path, "first")
    _disk_cache_set(path, "second")

    entries = list(path.parent.iterdir())
    assert entries == [path]
    assert path.read_text(encoding="utf-8") == "second"


def test_disk_cache_set_cleans_up_temp_file_on_write_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("PERSEUS_MCP_DISABLE_CACHE", raising=False)
    path = tmp_path / "capabilities" / "abc123.xml"
    path.parent.mkdir(parents=True)

    original_write_text = type(path).write_text

    def failing_write_text(self, *args, **kwargs):
        if self.name.startswith("abc123.xml.tmp-"):
            raise OSError("simulated disk failure")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(type(path), "write_text", failing_write_text)

    with pytest.raises(OSError):
        _disk_cache_set(path, "value")

    assert not path.exists()
    assert list(path.parent.iterdir()) == []


def test_disk_cache_set_preserves_original_error_when_cleanup_fails(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "capabilities" / "abc123.xml"
    path.parent.mkdir(parents=True)

    def failing_replace(source, target) -> None:
        raise OSError("replace failed")

    def failing_unlink(self, missing_ok=False) -> None:
        raise OSError("cleanup failed")

    monkeypatch.setattr(server.os, "replace", failing_replace)
    monkeypatch.setattr(Path, "unlink", failing_unlink)

    with pytest.raises(OSError, match="replace failed"):
        _disk_cache_set(path, "value")


def test_cached_text_returns_upstream_value_when_disk_cache_write_fails(
    monkeypatch,
) -> None:
    async def fetch() -> str:
        return "upstream value"

    monkeypatch.setattr(server, "_memory_cache_get", lambda name: None)
    monkeypatch.setattr(server, "_disk_cache_get", lambda path: None)

    def failing_cache_set(path, value) -> None:
        raise PermissionError("read-only cache")

    monkeypatch.setattr(server, "_disk_cache_set", failing_cache_set)

    with pytest.warns(MetadataCacheWarning, match="read-only cache"):
        result = asyncio.run(_cached_text("capabilities", {"request": "test"}, fetch))

    assert result == "upstream value"


def test_disk_cache_set_is_noop_when_cache_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PERSEUS_MCP_DISABLE_CACHE", "1")
    path = tmp_path / "capabilities" / "abc123.xml"

    _disk_cache_set(path, "value")

    assert not path.parent.exists()


def test_disk_cache_set_temp_filename_includes_pid_for_concurrent_writers(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("PERSEUS_MCP_DISABLE_CACHE", raising=False)
    path = tmp_path / "capabilities" / "abc123.xml"
    path.parent.mkdir(parents=True)

    seen_names: list[str] = []
    original_write_text = type(path).write_text

    def recording_write_text(self, *args, **kwargs):
        seen_names.append(self.name)
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(type(path), "write_text", recording_write_text)

    _disk_cache_set(path, "value")

    assert len(seen_names) == 1
    assert seen_names[0] == f"abc123.xml.tmp-{os.getpid()}-{seen_names[0].rsplit('-', 1)[-1]}"


def test_disk_cache_get_treats_concurrent_removal_as_cache_miss(monkeypatch) -> None:
    monkeypatch.delenv("PERSEUS_MCP_DISABLE_CACHE", raising=False)

    class VanishingCachePath:
        def exists(self):
            return True

        def stat(self):
            raise FileNotFoundError("removed concurrently")

    assert _disk_cache_get(VanishingCachePath()) is None


def test_disk_cache_get_treats_invalid_text_as_cache_miss(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("PERSEUS_MCP_DISABLE_CACHE", raising=False)
    path = tmp_path / "capabilities" / "abc123.xml"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff")

    assert _disk_cache_get(path) is None
