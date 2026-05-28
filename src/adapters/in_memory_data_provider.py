"""
Infrastructure Adapter: InMemoryDataProvider
---------------------------------------------
Implements IDataProvider using in-memory lists — no file I/O.

Used by the desktop UI layer: the UI loads data from files, stores it
in the DesktopController, then passes it here for the engine to consume.

Constructor args:
    - courses           (List[Course])     : pre-loaded course objects
    - exam_periods      (List[ExamPeriod]) : pre-loaded exam period objects
    - selected_programs (List[str])        : selected 5-digit programme IDs
      (defaults to [] for backward compatibility)
"""

from typing import List

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.interfaces.i_data_provider import IDataProvider


class InMemoryDataProvider(IDataProvider):

    def __init__(
        self,
        courses: List[Course],
        exam_periods: List[ExamPeriod],
        selected_programs: List[str] = None,
    ) -> None:
        self._courses = list(courses)
        self._exam_periods = list(exam_periods)
        self._selected_programs = list(selected_programs) if selected_programs else []

    def get_courses(self) -> List[Course]:
        return self._courses

    def get_exam_periods(self) -> List[ExamPeriod]:
        return self._exam_periods

    def get_selected_programs(self) -> List[str]:
        return self._selected_programs
