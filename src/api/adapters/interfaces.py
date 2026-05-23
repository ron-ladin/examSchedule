from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IOutputExporter(ABC):
    """The contract (interface) that every exporter must follow.

    Any class that wants to store and serve schedules must implement
    all four methods below. This keeps the rest of the code independent
    from how schedules are actually stored (memory, database, file, etc.).
    """

    @abstractmethod
    def add(self, item: Any) -> None:
        """Save one new schedule item to the store."""
        ...

    @abstractmethod
    def get_page(self, page: int, size: int) -> list[Any]:
        """Return one page of stored items. page=0 is first, page=1 is second, etc."""
        ...

    @abstractmethod
    def total(self) -> int:
        """Return the total number of items stored so far."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Delete all stored items and start fresh."""
        ...
