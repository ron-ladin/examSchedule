from typing import List

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.interfaces.i_data_provider import IDataProvider


class InMemoryDataProvider(IDataProvider):

    def __init__(self, courses: List[Course], periods: List[ExamPeriod]) -> None:
        self._courses = courses
        self._periods = periods

    def get_courses(self) -> List[Course]:
        return self._courses

    def get_exam_periods(self) -> List[ExamPeriod]:
        return self._periods

    def get_selected_programs(self) -> List[str]:
        return []
