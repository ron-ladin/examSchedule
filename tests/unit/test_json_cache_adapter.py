from __future__ import annotations

# Tests for JsonCacheAdapter (SCRUM-64)
# Each test checks one specific behaviour of the cache adapter.

import json
import os
from pathlib import Path

import pytest

from src.api.adapters.json_cache_adapter import JsonCacheAdapter


# --- Fixtures (shared setup used by multiple tests) ---

@pytest.fixture()
def cache_path(tmp_path: Path) -> Path:
    # A temporary file path that is deleted automatically after each test
    return tmp_path / "test_cache.json"


@pytest.fixture()
def adapter(cache_path: Path) -> JsonCacheAdapter:
    # A fresh adapter pointing at the temporary file
    return JsonCacheAdapter(path=cache_path)


# --- Tests ---

def test_save_writes_valid_json(adapter: JsonCacheAdapter, cache_path: Path) -> None:
    # After save(), the file on disk must contain valid JSON with the right data
    adapter.save(["course1"], ["period1"])
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert data["courses"] == ["course1"]
    assert data["periods"] == ["period1"]


def test_load_returns_saved_data(adapter: JsonCacheAdapter) -> None:
    # load() should return the same data that was passed to save()
    adapter.save(["c1", "c2"], ["p1"])
    result = adapter.load()
    assert result["courses"] == ["c1", "c2"]
    assert result["periods"] == ["p1"]


def test_load_does_not_reread_when_mtime_unchanged(
    adapter: JsonCacheAdapter, cache_path: Path
) -> None:
    # If the file has not changed (same mtime), load() must return the cached copy
    # and NOT read the new file content from disk
    adapter.save(["c1"], ["p1"])
    adapter.load()  # primes the in-memory cache

    # Change the file content but restore the original mtime to fake "no change"
    mtime = cache_path.stat().st_mtime
    cache_path.write_text(json.dumps({"courses": ["CHANGED"], "periods": []}), encoding="utf-8")
    os.utime(cache_path, (mtime, mtime))

    result = adapter.load()
    # Should still return the old cached data, not "CHANGED"
    assert result["courses"] == ["c1"]


def test_load_rereads_when_file_modified(adapter: JsonCacheAdapter, cache_path: Path) -> None:
    # When the file really changes (new mtime), load() must pick up the new data
    adapter.save(["c1"], ["p1"])
    adapter.load()  # primes cache

    adapter.save(["c2"], ["p2"])  # new save → mtime changes
    result = adapter.load()
    assert result["courses"] == ["c2"]


def test_load_missing_file_returns_empty(cache_path: Path) -> None:
    # If the cache file doesn't exist yet, load() returns {} instead of crashing
    adapter = JsonCacheAdapter(path=cache_path)
    result = adapter.load()
    assert result == {}


def test_load_corrupt_json_returns_empty(adapter: JsonCacheAdapter, cache_path: Path) -> None:
    # If the file contains broken JSON, load() returns {} instead of crashing
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("NOT_VALID_JSON{{{{", encoding="utf-8")
    result = adapter.load()
    assert result == {}


def test_save_creates_parent_directory(tmp_path: Path) -> None:
    # save() must create any missing parent folders automatically
    nested = tmp_path / "deep" / "nested" / "cache.json"
    adapter = JsonCacheAdapter(path=nested)
    adapter.save([], [])
    assert nested.exists()
