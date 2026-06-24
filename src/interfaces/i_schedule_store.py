"""
Schedule Store Interface
------------------------
Storage boundary for generated schedule results.

The UI should not have to know whether schedules are kept in RAM or in a
SQLite-backed temporary cache.  Implementations expose page-based access so very
large result sets can be browsed without materialising every Schedule object in
memory at once.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.sorting import SortingConfig


class IScheduleStore(ABC):
    """Persistence boundary for generated schedules."""

    @abstractmethod
    def append_many(
        self,
        period_key: str,
        schedules: Sequence[Schedule],
        courses: Sequence[Course] | None = None,
        selected_programs: Sequence[str] | None = None,
    ) -> int:
        """Append schedules to one period and return how many were stored."""

    @abstractmethod
    def replace_period(
        self,
        period_key: str,
        schedules: Sequence[Schedule],
        courses: Sequence[Course] | None = None,
        selected_programs: Sequence[str] | None = None,
    ) -> int:
        """Replace all schedules for one period and return how many were stored."""

    @abstractmethod
    def get(self, period_key: str, index: int, sorting: SortingConfig | None = None) -> Schedule:
        """Return one schedule by logical index."""

    @abstractmethod
    def get_page(
        self,
        period_key: str,
        offset: int,
        limit: int,
        sorting: SortingConfig | None = None,
    ) -> list[Schedule]:
        """Return a bounded page of schedules."""

    @abstractmethod
    def count(self, period_key: str) -> int:
        """Return the number of schedules stored for one period."""

    @abstractmethod
    def clear_period(self, period_key: str) -> None:
        """Remove all schedules for one period."""

    @abstractmethod
    def clear(self) -> None:
        """Remove all schedules from the store."""
