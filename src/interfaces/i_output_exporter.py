"""
Interface: IOutputExporter
---------------------------
Contract for writing generated schedules to an output destination.

Abstract methods to implement:
    - export_schedules(schedules: Iterator[Schedule]) -> None
        Consumes the schedule generator and writes output.
        Must group results by Semester → Moed → Schedule number.
        Output format:
            === SEMESTER: FALL ===
            --- Moed: Aleph ---
            Schedule #1:
              - <Course Name> | Date: DD-MM-YYYY | Instructor: <Name>
        Schedules within each moed must be sorted chronologically by exam date.
        "SPRI" must appear as "SPRING" in output.

Notes:
    - Use ABC and @abstractmethod from the abc module.
    - Accepts an Iterator (generator) — must NOT convert to list.
    - Implementations live in adapters/ — NOT here.
"""

from abc import ABC, abstractmethod


class IOutputExporter(ABC):
    pass
