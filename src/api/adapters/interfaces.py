from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterator
from typing import Any

from src.domain.course import Course
from src.domain.schedule import Schedule
from src.interfaces.i_output_exporter import IOutputExporter as _V1IOutputExporter


class IOutputExporter(_V1IOutputExporter):
    """Extends the v1.0 IOutputExporter with pagination methods for the API layer.

    Why we extend instead of replace:
    AppController.run() calls exporter.export_schedules(...) on whatever exporter
    it receives. By inheriting from the v1.0 IOutputExporter, any class that
    implements this interface is automatically compatible with AppController —
    no glue code needed.

    Concrete classes must implement all 5 methods:
      - export_schedules() — required by AppController (inherited from v1.0)
      - add()              — store one item (called inside export_schedules)
      - get_page()         — serve one page to the API
      - total()            — return total stored count
      - reset()            — clear everything before a new run
    """

    # Re-declared here to pin the Iterator type explicitly at the API layer
    @abstractmethod
    def export_schedules(
        self,
        schedules_by_period: dict[str, Iterator[Schedule]],
        courses_by_id: dict[str, Course],
    ) -> None: ...

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
