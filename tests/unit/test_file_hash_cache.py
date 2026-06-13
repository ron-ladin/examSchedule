"""
Unit Tests: FileHashCache
--------------------------
Covers: cache miss on first run, cache hit, stale hash invalidation,
        unwritable directory soft-fail, and invalidate().
"""
import pytest
from src.adapters.file_hash_cache import FileHashCache


@pytest.mark.unit
def test_load_returns_none_on_first_run(tmp_path):
    cache_dir = tmp_path / ".cache"
    watched = [tmp_path / "input.csv"]
    watched[0].write_text("data", encoding="utf-8")
    cache = FileHashCache(cache_dir, watched)
    assert cache.load() is None


@pytest.mark.unit
def test_save_then_load_returns_data(tmp_path):
    cache_dir = tmp_path / ".cache"
    watched = [tmp_path / "input.csv"]
    watched[0].write_text("data", encoding="utf-8")
    cache = FileHashCache(cache_dir, watched)
    payload = {"courses": ["A", "B"]}
    cache.save(payload)
    assert cache.load() == payload


@pytest.mark.unit
def test_load_returns_none_after_watched_file_changes(tmp_path):
    cache_dir = tmp_path / ".cache"
    watched = [tmp_path / "input.csv"]
    watched[0].write_text("original", encoding="utf-8")
    cache = FileHashCache(cache_dir, watched)
    cache.save({"key": "value"})
    watched[0].write_text("changed", encoding="utf-8")
    assert cache.load() is None


@pytest.mark.unit
def test_save_is_silent_when_cache_dir_unwritable(tmp_path):
    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir()
    cache_dir.chmod(0o444)
    watched = [tmp_path / "input.csv"]
    watched[0].write_text("data", encoding="utf-8")
    cache = FileHashCache(cache_dir, watched)
    try:
        cache.save({"x": 1})  # must not raise
    finally:
        cache_dir.chmod(0o755)


@pytest.mark.unit
def test_invalidate_causes_next_load_to_miss(tmp_path):
    cache_dir = tmp_path / ".cache"
    watched = [tmp_path / "input.csv"]
    watched[0].write_text("data", encoding="utf-8")
    cache = FileHashCache(cache_dir, watched)
    cache.save({"key": "value"})
    cache.invalidate()
    assert cache.load() is None


@pytest.mark.unit
def test_load_returns_none_on_corrupt_manifest(tmp_path):
    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir()
    (cache_dir / "manifest.json").write_text("not json", encoding="utf-8")
    watched = [tmp_path / "input.csv"]
    watched[0].write_text("data", encoding="utf-8")
    cache = FileHashCache(cache_dir, watched)
    assert cache.load() is None
