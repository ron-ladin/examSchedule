"""
Interface: IOutputExporter
---------------------------
Contract for writing generated schedules to an output destination.

Abstract methods to implement:
    - export_schedules(
          schedules_by_period: Dict[str, Iterator[Schedule]],
          courses_by_id: Dict[str, Course]
      ) -> None

        Writes all generated schedules to an output destination.

        The schedules are received as Iterator[Schedule] so the exporter can
        consume generated schedules one by one, without requiring all schedules
        to be loaded into memory at once.  Implementations MUST NOT call
        list() on the iterator — the generator's O(1) laziness must be
        preserved through to the exporter boundary.

        Must group results by Semester → Moed → Schedule number.
        Output format:
            === SEMESTER: FALL ===
            --- Moed: Aleph ---
            Schedule #1:
              - <Course Name> | Date: DD-MM-YYYY | Instructor: <Name>

        Schedules within each moed must be sorted chronologically by exam date.
        "SPRI" may appear as "SPRING" in output if the concrete exporter chooses
        to display user-friendly semester names.

Notes:
    - Use ABC and @abstractmethod from the abc module.
    - Implementations live in adapters/ — NOT here.
    - This interface defines only the contract, not the output formatting logic.
    - The Iterator[Schedule] type (not List) is intentional and load-bearing:
      it preserves the O(PAGE_SIZE) memory guarantee of PaginatedExporter and
      forbids any implementation from silently materialising the full result set.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator

from src.domain.course import Course
from src.domain.schedule import Schedule


class IOutputExporter(ABC):

    @abstractmethod
    def export_schedules(
        self,
        schedules_by_period: dict[str, Iterator[Schedule]],
        courses_by_id: dict[str, Course],
    ) -> None:
        pass
