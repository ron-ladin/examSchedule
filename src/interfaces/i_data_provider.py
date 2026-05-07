"""
Interface: IDataProvider
-------------------------
Contract for reading all input data needed by the scheduling engine.

Abstract methods to implement:
    - get_courses() -> List[Course]
        Returns all courses parsed from the data source.
        Only courses with evaluation_type == "Exam" need to be scheduled,
        but filtering can happen here or in the engine.

    - get_exam_periods() -> List[ExamPeriod]
        Returns all exam periods (semester + moed + date ranges + exclusions).

    - get_selected_programs() -> List[str]
        Returns the list of selected 5-digit program IDs (up to 5).
        Must validate that each entry is exactly a 5-digit string.

Notes:
    - Use ABC and @abstractmethod from the abc module.
    - Implementations live in adapters/ — NOT here.
    - The engine/application layer depends on this interface, not on a concrete adapter.
"""

from abc import ABC, abstractmethod
from typing import List

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod


class IDataProvider(ABC):

    @abstractmethod
    def get_courses(self) -> List[Course]:
        pass

    @abstractmethod
    def get_exam_periods(self) -> List[ExamPeriod]:
        pass

    @abstractmethod
    def get_selected_programs(self) -> List[str]:
        pass