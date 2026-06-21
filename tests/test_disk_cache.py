import os

import pytest

from perseus_mcp.server import _disk_cache_get, _disk_cache_set


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
