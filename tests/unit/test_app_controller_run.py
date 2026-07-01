"""
Unit Tests: AppController — pipeline wiring and run() behaviour.

Verifies AppController loads from the provider, filters relevant courses,
sorts/dedupes periods, passes lazy iterators to the exporter, and rejects
invalid programme selections. No PyQt, no QApplication, no real file I/O.
"""

from collections.abc import Iterator
from datetime import date

import pytest

from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.engine.app_controller import AppController

from tests.unit._app_controller_helpers import (
    FakeDataProvider,
    FakeExporter,
    FakeGenerator,
    _course,
    _period,
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


def test_run_without_sorting_cap_1_generator_advances_only_once():
    """
    With cap=1 and no sorting, the generator should only be advanced enough
    to produce the capped page — not fully consumed.
    """
    advance_count = 0

    def counting_gen():
        nonlocal advance_count
        for i in range(100):
            advance_count += 1
            yield i

    class _CountingGenerator:
        def generate_schedules(self, courses, exam_period):
            return counting_gen()

    class _CapExporter:
        def export_schedules(self, schedules_by_period, courses_by_id):
            for _, it in schedules_by_period.items():
                next(it, None)  # consume only 1

    course = _course(course_id="11111", semester="FALL")
    period = _period("FALL", "Aleph")
    provider = FakeDataProvider(courses=[course], exam_periods=[period])

    AppController(
        data_provider=provider,
        exporter=_CapExporter(),
        generator=_CountingGenerator(),
        selected_programs=["83101"],
    ).run()

    assert advance_count == 1, (
        f"Generator advanced {advance_count} times; cap=1 should advance it only once"
    )


def test_run_does_not_consume_full_generator_with_capped_exporter():
    """
    With a capped exporter, AppController.run() must NOT materialise the full
    iterator. Sorting is the exporter's responsibility (the exporter sorts only
    the capped page), so AppController never calls list() on the lazy iterator.
    """
    advance_count = 0

    def counting_gen():
        nonlocal advance_count
        for i in range(100):
            advance_count += 1
            yield i

    class _CountingGenerator:
        def generate_schedules(self, courses, exam_period):
            return counting_gen()

    class _CapExporter:
        def export_schedules(self, schedules_by_period, courses_by_id):
            for _, it in schedules_by_period.items():
                next(it, None)  # consume only 1

    course = _course(course_id="11111", semester="FALL")
    period = _period("FALL", "Aleph")
    provider = FakeDataProvider(courses=[course], exam_periods=[period])

    AppController(
        data_provider=provider,
        exporter=_CapExporter(),
        generator=_CountingGenerator(),
        selected_programs=["83101"],
    ).run()

    assert advance_count < 100, (
        "AppController.run() fully consumed the generator despite a capped exporter; "
        "sorting must not call list() on the lazy iterator"
    )
