"""
Interface: IScheduleGenerator
-------------------------------
Contract for generating conflict-free exam schedules for a given exam period.

Abstract methods:
    - generate_schedules(courses: List[Course], exam_period: ExamPeriod) -> Iterator[Schedule]

        Yields every valid conflict-free Schedule for the given courses and period.
        Must yield lazily — do NOT collect results into a list before returning.

Notes:
    - Use ABC and @abstractmethod from the abc module.
    - The engine depends only on this interface, never on ScheduleGenerator directly.
    - Implementations live in engine/ — NOT here.
"""

from abc import ABC, abstractmethod
from typing import Iterator, List

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule


class IScheduleGenerator(ABC):

    @abstractmethod
    def generate_schedules(
        self,
        courses: List[Course],
        exam_period: ExamPeriod,
    ) -> Iterator[Schedule]:
        """Yield every conflict-free schedule for the given courses and exam period."""
