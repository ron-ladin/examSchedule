"""
Unit Tests: AppController
-------------------------
Pure unit tests for the core AppController orchestration layer.

These tests verify that AppController wires the pipeline correctly:
data provider -> generator -> exporter.

No PyQt imports.
No QApplication.
No real file I/O.
"""

from collections.abc import Iterator
from datetime import date

import pytest

from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.engine.app_controller import AppController


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


def test_run_connects_provider_generator_and_exporter():
    """
    AppController.run should load data from the provider, pass relevant courses
    to the generator, and pass generated schedules to the exporter.
    """
    relevant_exam = _course(
        course_id="11111",
        name="Calculus",
        semester="FALL",
        evaluation_type="Exam",
    )
    project_course = _course(
        course_id="22222",
        name="Project Lab",
        semester="FALL",
        evaluation_type="Project",
    )
    spring_course = _course(
        course_id="33333",
        name="Spring Course",
        semester="SPRI",
        evaluation_type="Exam",
    )
    fall_period = _period("FALL", "Aleph")

    provider = FakeDataProvider(
        courses=[relevant_exam, project_course, spring_course],
        exam_periods=[fall_period],
    )
    generator = FakeGenerator()
    exporter = FakeExporter()

    controller = AppController(
        data_provider=provider,
        exporter=exporter,
        generator=generator,
        selected_programs=["83101"],
    )

    controller.run()

    assert provider.get_courses_called is True
    assert provider.get_exam_periods_called is True

    assert len(generator.calls) == 1
    generated_courses, generated_period = generator.calls[0]

    assert generated_period == fall_period
    assert generated_courses == [relevant_exam]

    assert exporter.called is True
    assert exporter.courses_by_id == {
        "11111": relevant_exam,
        "22222": project_course,
        "33333": spring_course,
    }
    assert list(exporter.materialized_schedules.keys()) == ["FALL - Aleph"]
    assert len(exporter.materialized_schedules["FALL - Aleph"]) == 1


def test_run_passes_lazy_iterators_to_exporter():
    """
    AppController should pass generator iterators directly to the exporter.

    It should not convert them to lists inside the controller.
    """
    course = _course(course_id="11111", semester="FALL")
    period = _period("FALL", "Aleph")

    provider = FakeDataProvider(courses=[course], exam_periods=[period])
    generator = FakeGenerator()
    exporter = FakeExporter()

    controller = AppController(
        data_provider=provider,
        exporter=exporter,
        generator=generator,
        selected_programs=["83101"],
    )

    controller.run()

    assert exporter.schedules_by_period is not None
    assert "FALL - Aleph" in exporter.schedules_by_period
    assert isinstance(exporter.schedules_by_period["FALL - Aleph"], Iterator)


def test_run_raises_when_selected_program_does_not_exist_in_courses():
    """
    If selected_programs contains a programme id that does not appear in course
    offerings, AppController should reject the run before exporting.
    """
    course = _course(course_id="11111", program_id="83101")
    period = _period("FALL", "Aleph")

    provider = FakeDataProvider(courses=[course], exam_periods=[period])
    generator = FakeGenerator()
    exporter = FakeExporter()

    controller = AppController(
        data_provider=provider,
        exporter=exporter,
        generator=generator,
        selected_programs=["99999"],
    )

    with pytest.raises(ValueError, match="Selected program ids do not exist"):
        controller.run()

    assert generator.calls == []
    assert exporter.called is False


def test_run_raises_on_duplicate_exam_period_key():
    """
    Two exam periods with the same semester/moed key should be rejected.
    """
    course = _course(course_id="11111", semester="FALL")
    first_period = _period("FALL", "Aleph", date(2026, 1, 5), date(2026, 1, 6))
    second_period = _period("FALL", "Aleph", date(2026, 1, 7), date(2026, 1, 8))

    provider = FakeDataProvider(
        courses=[course],
        exam_periods=[first_period, second_period],
    )
    generator = FakeGenerator()
    exporter = FakeExporter()

    controller = AppController(
        data_provider=provider,
        exporter=exporter,
        generator=generator,
        selected_programs=["83101"],
    )

    with pytest.raises(ValueError, match="Duplicate exam period found"):
        controller.run()

    assert exporter.called is False


def test_run_sorts_exam_periods_before_generation_and_export():
    """
    AppController should sort exam periods by semester/moed before generating
    schedules and before passing them to the exporter.
    """
    course = Course(
        id="11111",
        name="Multi Semester Course",
        instructor="Dr. Test",
        evaluation_type="Exam",
    )
    course.add_offering(CourseOffering("83101", 1, "FALL", "Obligatory"))
    course.add_offering(CourseOffering("83101", 1, "SPRI", "Obligatory"))
    course.add_offering(CourseOffering("83101", 1, "SUMM", "Obligatory"))

    spri_period = _period("SPRI", "Aleph", date(2026, 3, 1), date(2026, 3, 2))
    fall_bet_period = _period("FALL", "Bet", date(2026, 2, 1), date(2026, 2, 2))
    fall_aleph_period = _period("FALL", "Aleph", date(2026, 1, 5), date(2026, 1, 6))
    summ_period = _period("SUMM", "Aleph", date(2026, 7, 1), date(2026, 7, 2))

    provider = FakeDataProvider(
        courses=[course],
        exam_periods=[
            summ_period,
            spri_period,
            fall_bet_period,
            fall_aleph_period,
        ],
    )
    generator = FakeGenerator()
    exporter = FakeExporter()

    controller = AppController(
        data_provider=provider,
        exporter=exporter,
        generator=generator,
        selected_programs=["83101"],
    )

    controller.run()

    generated_period_keys = [
        period.get_key()
        for _courses, period in generator.calls
    ]

    assert generated_period_keys == [
        "FALL - Aleph",
        "FALL - Bet",
        "SPRI - Aleph",
        "SUMM - Aleph",
    ]

    assert list(exporter.materialized_schedules.keys()) == [
        "FALL - Aleph",
        "FALL - Bet",
        "SPRI - Aleph",
        "SUMM - Aleph",
    ]


def test_run_skips_periods_with_no_relevant_exam_courses_but_still_exports():
    """
    If a period has no relevant exam courses, AppController should skip calling
    the generator for that period and still call the exporter with the remaining
    generated schedules.
    """
    fall_course = _course(course_id="11111", semester="FALL")
    fall_period = _period("FALL", "Aleph")
    spring_period = _period("SPRI", "Aleph", date(2026, 3, 1), date(2026, 3, 2))

    provider = FakeDataProvider(
        courses=[fall_course],
        exam_periods=[fall_period, spring_period],
    )
    generator = FakeGenerator()
    exporter = FakeExporter()

    controller = AppController(
        data_provider=provider,
        exporter=exporter,
        generator=generator,
        selected_programs=["83101"],
    )

    controller.run()

    assert len(generator.calls) == 1
    assert generator.calls[0][1].get_key() == "FALL - Aleph"

    assert exporter.called is True
    assert list(exporter.materialized_schedules.keys()) == ["FALL - Aleph"]
