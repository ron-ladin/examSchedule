"""
Interface: IOutputExporter
---------------------------
Contract for writing generated schedules to an output destination.

Abstract methods to implement:
    - export_schedules(
          schedules_by_period: Dict[str, Iterable[Schedule]],
          courses_by_id: Dict[str, Course]
      ) -> None

        Writes all generated schedules to an output destination.

        The schedules are received as Iterable[Schedule] so the exporter can
        consume generated schedules one by one, without requiring all schedules
        to be loaded into memory at once.

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
"""

from abc import ABC, abstractmethod
from typing import Dict, Iterable

from src.domain.course import Course
from src.domain.schedule import Schedule


class IOutputExporter(ABC):

    @abstractmethod
    def export_schedules(
        self,
        schedules_by_period: Dict[str, Iterable[Schedule]],
        courses_by_id: Dict[str, Course],
    ) -> None:
        pass