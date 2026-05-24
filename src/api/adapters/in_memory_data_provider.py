from __future__ import annotations

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.interfaces.i_data_provider import IDataProvider


class InMemoryDataProvider(IDataProvider):
    """IDataProvider backed by pre-loaded in-memory domain objects.

    Used by the generate endpoint so AppController can run without touching disk.
    Data must already be parsed into proper domain objects before construction.
    """

    def __init__(
        self,
        courses: list[Course],
        periods: list[ExamPeriod],
        selected_programs: list[str] | None = None,
    ) -> None:
        self._courses = courses
        self._periods = periods
        self._selected_programs = selected_programs or []

    def get_courses(self) -> list[Course]:
        return self._courses

    def get_exam_periods(self) -> list[ExamPeriod]:
        return self._periods

    def get_selected_programs(self) -> list[str]:
        return self._selected_programs
