"""
Shared fakes/builders for AppController unit tests.

In-memory fakes for the data provider, generator, and exporter, plus small
Course/ExamPeriod builders. No PyQt, no QApplication, no real file I/O.
"""

from collections.abc import Iterator
from datetime import date

from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule


class FakeDataProvider:
    """Small in-memory fake for AppController unit tests."""

    def __init__(
        self,
        courses: list[Course],
        exam_periods: list[ExamPeriod],
    ) -> None:
        self._courses = courses
        self._exam_periods = exam_periods
        self.get_courses_called = False
        self.get_exam_periods_called = False

    def get_courses(self) -> list[Course]:
        self.get_courses_called = True
        return self._courses

    def get_exam_periods(self) -> list[ExamPeriod]:
        self.get_exam_periods_called = True
        return self._exam_periods

    def get_selected_programs(self) -> list[str]:
        return []


class FakeGenerator:
    """Fake generator that records calls and returns lazy iterators."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[Course], ExamPeriod]] = []

    def generate_schedules(
        self,
        courses: list[Course],
        exam_period: ExamPeriod,
    ) -> Iterator[Schedule]:
        self.calls.append((list(courses), exam_period))

        if not courses:
            return iter(())

        first_valid_date = exam_period.get_valid_dates()[0]
        schedule = Schedule(
            period=exam_period,
            assignments={courses[0].id: first_valid_date},
        )

        return iter([schedule])


class FakeExporter:
    """Fake exporter that records the output passed by AppController."""

    def __init__(self) -> None:
        self.called = False
        self.schedules_by_period = None
        self.courses_by_id = None
        self.materialized_schedules: dict[str, list[Schedule]] = {}

    def export_schedules(
        self,
        schedules_by_period,
        courses_by_id,
    ) -> None:
        self.called = True
        self.schedules_by_period = schedules_by_period
        self.courses_by_id = courses_by_id

        # Materialize only inside the fake exporter, because the real controller
        # should pass lazy iterators through without converting them to lists.
        self.materialized_schedules = {
            period_key: list(schedule_iter)
            for period_key, schedule_iter in schedules_by_period.items()
        }


def _course(
    course_id: str = "11111",
    name: str = "Course",
    semester: str = "FALL",
    evaluation_type: str = "Exam",
    program_id: str = "83101",
) -> Course:
    course = Course(
        id=course_id,
        name=name,
        instructor="Dr. Test",
        evaluation_type=evaluation_type,
    )
    course.add_offering(
        CourseOffering(
            program_id=program_id,
            year=1,
            semester=semester,
            requirement="Obligatory",
        )
    )
    return course


def _period(
    semester: str = "FALL",
    moed: str = "Aleph",
    start: date = date(2026, 1, 5),
    end: date = date(2026, 1, 6),
) -> ExamPeriod:
    return ExamPeriod(
        semester=semester,
        moed=moed,
        date_ranges=[(start, end)],
    )
