"""
Adapter: FileHashCache
-----------------------
Content-addressed cache for parsed input data.

Spec §6.1: If the courses/dates input files have not changed since the last
run, load domain objects from a local cache file instead of re-parsing the
raw CSV/text files. This avoids redundant I/O and parsing on every launch.

Strategy:
  1. Compute SHA-256 of each watched file (courses file + dates file).
  2. Compare combined hash against the hash stored in the cache manifest.
  3. On match  → deserialize and return the cached domain objects.
  4. On miss   → let the caller parse normally, then persist the new data.

Cache layout (under <cache_dir>/, default: .cache/):
    manifest.json   — {"hash": "<hex>", "created_at": "<iso8601>"}
    data.pkl        — pickled dict of domain objects keyed by type name

Notes:
  - Cache directory is created on first write; ignored if unwritable.
  - Pickle is used for speed; never unpickle data from untrusted sources.
  - Thread-safety: single-process desktop app — no locking needed.
"""

import hashlib
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


# TODO (SCRUM-§6.1): decide whether to use pickle or a structured format
#   (e.g. JSON + custom serialisers) for better forward-compatibility.
_MANIFEST_FILE = "manifest.json"
_DATA_FILE = "data.pkl"


class FileHashCache:
    """Read-through cache keyed on the combined SHA-256 of watched files."""

    def __init__(self, cache_dir: Path, watched_files: list[Path]) -> None:
        # cache_dir: where manifest.json and data.pkl are stored
        # watched_files: ordered list of paths whose content governs validity
        self._cache_dir = cache_dir
        self._watched = watched_files

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> Optional[Dict[str, Any]]:
        """Return cached domain objects if the watched files are unchanged.

        Returns None if the cache is absent, stale, or unreadable.
        """
        current_hash = self._compute_hash()
        stored_hash = self._read_manifest()

        if stored_hash != current_hash:
            return None

        return self._read_data()

    def save(self, data: Dict[str, Any]) -> None:
        """Persist domain objects and update the manifest hash.

        Silently skips if the cache directory is not writable.
        """
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._write_manifest(self._compute_hash())
            self._write_data(data)
        except OSError:
            # Non-fatal: cache is a performance hint, not a requirement.
            pass

    def invalidate(self) -> None:
        """Delete the cached manifest so the next load() returns None."""
        manifest = self._cache_dir / _MANIFEST_FILE
        if manifest.exists():
            manifest.unlink()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _compute_hash(self) -> str:
        """Return a hex SHA-256 of the concatenated content of watched files."""
        digest = hashlib.sha256()
        for path in self._watched:
            if path.exists():
                digest.update(path.read_bytes())
        return digest.hexdigest()

    def _read_manifest(self) -> Optional[str]:
        """Return the stored hash string, or None if absent/corrupt."""
        manifest = self._cache_dir / _MANIFEST_FILE
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            return payload.get("hash")
        except (OSError, json.JSONDecodeError, KeyError):
            return None

    def _write_manifest(self, hash_hex: str) -> None:
        manifest = self._cache_dir / _MANIFEST_FILE
        payload = {
            "hash": hash_hex,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _read_data(self) -> Optional[Dict[str, Any]]:
        data_file = self._cache_dir / _DATA_FILE
        try:
            return pickle.loads(data_file.read_bytes())  # noqa: S301
        except (OSError, pickle.UnpicklingError):
            return None

    def _write_data(self, data: Dict[str, Any]) -> None:
        data_file = self._cache_dir / _DATA_FILE
        data_file.write_bytes(pickle.dumps(data))
