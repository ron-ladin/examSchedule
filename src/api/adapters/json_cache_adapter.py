from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

# Default location of the cache file on disk
CACHE_PATH: Path = Path("data/.cache.json")


class JsonCacheAdapter:
    """Save and load session data (courses + periods) to a JSON file on disk.

    Why we need this: if the server restarts, the user's uploaded data would
    normally be lost. This adapter backs it up to disk so it survives a restart.

    How the cache works: instead of reading the file on every request, we remember
    the file's last-modified time (mtime). We only re-read the file when that time
    changes — this avoids slow disk reads on every status poll.

    Important limitations (v1.0):
    - save() and load() are blocking — callers in async routes must use asyncio.to_thread().
    - Dates are saved as strings (default=str). load() returns raw dicts, not typed objects.
      The cache is used only as a freshness check, not to restore full domain objects.
    """

    def __init__(self, path: Path = CACHE_PATH) -> None:
        self._path = path
        # Lock so only one thread reads or writes at a time
        self._lock = threading.Lock()
        # The mtime of the file the last time we read it (None = never read)
        self._mtime: float | None = None
        # The last data we read from disk, kept in memory to avoid re-reading
        self._data: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        """Return the cached data. Only reads from disk when the file has changed."""
        with self._lock:
            current = self._file_mtime()
            # If the file hasn't changed since last read, return what we have in memory
            if current is not None and current == self._mtime:
                return self._data
            # File changed (or first load) — read from disk
            return self._read_disk()

    def save(self, courses: list[Any], periods: list[Any]) -> None:
        """Write courses and periods to disk as JSON, then update the in-memory cache."""
        with self._lock:
            payload: dict[str, Any] = {"courses": courses, "periods": periods}
            # Create the parent folder if it doesn't exist yet
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Write to disk (default=str converts dates and other types to strings)
            self._path.write_text(json.dumps(payload, default=str), encoding="utf-8")
            # Update our in-memory snapshot so the next load() doesn't re-read disk
            self._mtime = self._file_mtime()
            self._data = payload

    def _read_disk(self) -> dict[str, Any]:
        """Read and parse the JSON file. Returns {} if the file is missing or broken."""
        try:
            raw = self._path.read_text(encoding="utf-8")
            self._data = json.loads(raw)
            self._mtime = self._file_mtime()
            return self._data
        except (json.JSONDecodeError, FileNotFoundError, OSError):
            # Corrupt or missing cache — return empty, do not crash the server
            self._data = {}
            self._mtime = None
            return {}

    def _file_mtime(self) -> float | None:
        """Return the file's last-modified timestamp, or None if the file doesn't exist."""
        try:
            return os.path.getmtime(self._path)
        except FileNotFoundError:
            return None
