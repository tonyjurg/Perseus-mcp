import asyncio
import json
import os
import subprocess
from pathlib import Path

import pytest

from perseus_mcp import cache, server
from platformdirs import user_cache_path
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


def test_disk_cache_set_cleans_up_temp_file_on_write_failure(
    tmp_path, monkeypatch
) -> None:
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
    assert (
        seen_names[0]
        == f"abc123.xml.tmp-{os.getpid()}-{seen_names[0].rsplit('-', 1)[-1]}"
    )


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


def test_default_cache_is_shared_across_working_directories(monkeypatch, tmp_path):
    monkeypatch.delenv("PERSEUS_MCP_CACHE_DIR")
    expected = user_cache_path("perseus-mcp", appauthor=False).absolute()
    monkeypatch.chdir(tmp_path)
    first = server._cache_dir()
    notebook_dir = tmp_path / "notebooks"
    notebook_dir.mkdir()
    monkeypatch.chdir(notebook_dir)
    assert first == server._cache_dir() == expected
    assert first.is_absolute()


def test_cache_override_preserves_spaces_and_resolves_relative_paths(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERSEUS_MCP_CACHE_DIR", " shared  cache ")
    assert server._cache_dir() == tmp_path / "shared  cache"


def test_relative_platform_cache_root_does_not_restore_cwd_dependence(monkeypatch):
    monkeypatch.delenv("PERSEUS_MCP_CACHE_DIR")
    monkeypatch.setattr(
        cache, "user_cache_path", lambda *args, **kwargs: Path("relative")
    )
    assert server._cache_dir() == Path.home() / ".cache" / "perseus-mcp"


def test_clear_cache_preserves_unrelated_files_and_counts_only_metadata(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("PERSEUS_MCP_CACHE_DIR", str(tmp_path))
    key = server._cache_key({"request": "test"})
    metadata = tmp_path / "capabilities" / f"{key}.xml"
    _disk_cache_set(metadata, "<TextInventory/>")
    unrelated = [tmp_path / "notes.txt", metadata.parent / "metadata.xml"]
    nested = metadata.parent / "keep" / f"{key}.xml"
    nested.parent.mkdir()
    unrelated.append(nested)
    for path in unrelated:
        path.write_text("keep me", encoding="utf-8")
    temporary = metadata.with_name(f"{metadata.name}.tmp-123-456")
    temporary.write_text("partial", encoding="utf-8")
    before = json.loads(server._cache_status())
    assert before["disk_files"] == 2
    result = json.loads(server._clear_cache())
    assert result["disk_files_removed"] == 2
    assert result["disk_cache_removed"] is False
    assert not metadata.exists() and not temporary.exists()
    assert all(path.read_text(encoding="utf-8") == "keep me" for path in unrelated)


@pytest.mark.parametrize("linked", ["root", "namespace", "entry"])
def test_cache_clear_does_not_follow_links(monkeypatch, tmp_path, linked):
    root = tmp_path / "cache"
    outside = tmp_path / "outside"
    outside.mkdir()
    key = server._cache_key({"request": "test"})
    if linked == "root":
        (outside / "capabilities").mkdir()
    target = (outside / "capabilities" if linked == "root" else outside) / f"{key}.xml"
    target.write_text("private", encoding="utf-8")
    try:
        if linked == "root":
            root.symlink_to(outside, target_is_directory=True)
        elif linked == "namespace":
            root.mkdir()
            (root / "capabilities").symlink_to(outside, target_is_directory=True)
        else:
            namespace = root / "capabilities"
            namespace.mkdir(parents=True)
            (namespace / f"{key}.xml").symlink_to(target)
    except OSError as exc:
        pytest.skip(f"Creating symlinks is unavailable: {exc}")
    monkeypatch.setenv("PERSEUS_MCP_CACHE_DIR", str(root))
    assert json.loads(server._cache_status())["disk_files"] == 0
    assert json.loads(server._clear_cache())["disk_files_removed"] == 0
    assert target.read_text(encoding="utf-8") == "private"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
@pytest.mark.parametrize("linked", ["root", "namespace"])
def test_cache_clear_skips_windows_junctions(monkeypatch, tmp_path, linked):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "cache"
    if linked == "root":
        directory = outside / "capabilities"
        directory.mkdir()
        link = root
    else:
        directory = outside
        root.mkdir()
        link = root / "capabilities"
    target = directory / f"{server._cache_key({'request': 'test'})}.xml"
    target.write_text("keep me", encoding="utf-8")
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    monkeypatch.setenv("PERSEUS_MCP_CACHE_DIR", str(root))
    assert json.loads(server._cache_status())["disk_files"] == 0
    assert json.loads(server._clear_cache())["disk_files_removed"] == 0
    assert target.read_text(encoding="utf-8") == "keep me"
