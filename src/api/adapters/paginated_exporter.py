from __future__ import annotations

import threading
from typing import Any

from src.api.adapters.interfaces import IOutputExporter

# How many items fit on one page by default
PAGE_SIZE: int = 50

# Maximum schedules we keep in memory — stops the list from growing forever
MAX_SCHEDULES: int = 10_000


class PaginatedExporter(IOutputExporter):
    """Thread-safe in-memory store for generated schedules with pagination support.

    add() is called from asyncio.to_thread (generator thread).
    get_page() and total() are called from the async event loop.
    Both sides must hold self._lock.
    """

    def __init__(self) -> None:
        # The list that holds all saved schedules
        self._items: list[Any] = []
        # Lock so only one thread can read or write at a time
        self._lock = threading.Lock()

    def add(self, item: Any) -> None:
        """Save one schedule to the list. Called by the background generator thread."""
        with self._lock:
            # If we already hit the cap, stop adding (do not crash)
            if len(self._items) >= MAX_SCHEDULES:
                return
            self._items.append(item)

    def get_page(self, page: int, size: int = PAGE_SIZE) -> list[Any]:
        """Return one page of schedules. page=0 is the first page, page=1 is the second, etc."""
        with self._lock:
            # Calculate where this page starts and return only that slice
            start = page * size
            return self._items[start : start + size]

    def total(self) -> int:
        """Return how many schedules are stored right now."""
        with self._lock:
            return len(self._items)

    def reset(self) -> None:
        """Delete all stored schedules. Called before starting a new generation run."""
        with self._lock:
            self._items = []
