"""
Unit Tests: AppController — ThresholdFilter wiring (SCRUM-261).

Verifies the threshold filter drops/keeps schedules, is gated on both filter
and settings being present, and receives the correct per-period courses
(late-binding closure regression). No PyQt, no QApplication.
"""

from datetime import date

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


class _RejectAllFilter:
    """Stub that rejects every schedule."""

    @staticmethod
    def is_valid(schedule, courses, settings, selected_programs=None) -> bool:  # noqa: ARG002
        return False


class _AcceptAllFilter:
    """Stub that accepts every schedule."""

    @staticmethod
    def is_valid(schedule, courses, settings, selected_programs=None) -> bool:  # noqa: ARG002
        return True


def _threshold_settings_stub():
    from src.domain.threshold import ThresholdSettings
    return ThresholdSettings()


def test_threshold_filter_drops_invalid_schedules_from_iterator():
    """
    When a threshold_filter is wired, schedules that fail is_valid should be
    excluded from the lazy iterator before _MemoryExporter sees them.
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
        threshold_filter=_RejectAllFilter(),
        threshold_settings=_threshold_settings_stub(),
    )
    controller.run()

    assert exporter.materialized_schedules["FALL - Aleph"] == []


def test_threshold_filter_accept_all_passes_every_schedule_through():
    """
    An accept-all filter should leave the schedule list unchanged.
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
        threshold_filter=_AcceptAllFilter(),
        threshold_settings=_threshold_settings_stub(),
    )
    controller.run()

    assert len(exporter.materialized_schedules["FALL - Aleph"]) == 1


def test_no_threshold_filter_passes_all_schedules_unchanged():
    """
    When threshold_filter=None, the lazy iterator is passed through as-is.
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

    assert len(exporter.materialized_schedules["FALL - Aleph"]) == 1


def test_threshold_filter_applied_to_correct_courses_per_period():
    """
    Regression for the late-binding closure bug:

    When multiple exam periods exist, each period's filter must receive *that
    period's* relevant_courses — not the last iteration's courses.

    Setup: two periods, each with one course in a *different* program.
      FALL Aleph → course 11111 (program 83101)
      SPRI Aleph → course 22222 (program 83102)

    A spy filter records every courses list it receives.  With the bug present
    both entries would be the SPRI courses (last iteration wins).  With the fix
    the first entry is the FALL course and the second is the SPRI course.
    """
    fall_course = Course(
        id="11111",
        name="Calculus",
        instructor="Dr. Cohen",
        evaluation_type="Exam",
    )
    fall_course.add_offering(
        CourseOffering(program_id="83101", year=1, semester="FALL", requirement="Obligatory")
    )

    spri_course = Course(
        id="22222",
        name="Algebra",
        instructor="Dr. Levi",
        evaluation_type="Exam",
    )
    spri_course.add_offering(
        CourseOffering(program_id="83102", year=1, semester="SPRI", requirement="Obligatory")
    )

    fall_period = _period("FALL", "Aleph", date(2026, 1, 5), date(2026, 1, 6))
    spri_period = _period("SPRI", "Aleph", date(2026, 3, 2), date(2026, 3, 3))

    provider = FakeDataProvider(
        courses=[fall_course, spri_course],
        exam_periods=[fall_period, spri_period],
    )
    generator = FakeGenerator()
    exporter = FakeExporter()

    class _SpyCourseFilter:
        def __init__(self):
            self.courses_per_call: list[list] = []

        def is_valid(self, schedule, courses, settings, selected_programs=None):  # noqa: ARG002
            self.courses_per_call.append(list(courses))
            return True

    from src.domain.threshold import ThresholdSettings as _TS

    spy = _SpyCourseFilter()
    controller = AppController(
        data_provider=provider,
        exporter=exporter,
        generator=generator,
        selected_programs=["83101", "83102"],
        threshold_filter=spy,
        threshold_settings=_TS(),
    )
    controller.run()

    # The spy must have been called once per period (one schedule each).
    assert len(spy.courses_per_call) == 2

    fall_call, spri_call = spy.courses_per_call
    assert fall_course in fall_call, "FALL period filter must receive FALL course"
    assert spri_course not in fall_call, "FALL period filter must NOT receive SPRI course"
    assert spri_course in spri_call, "SPRI period filter must receive SPRI course"
    assert fall_course not in spri_call, "SPRI period filter must NOT receive FALL course"


def test_threshold_filter_only_applied_when_both_filter_and_settings_provided():
    """
    When threshold_filter is provided but threshold_settings is None (or vice versa),
    the filter must NOT be applied — both must be present to activate filtering.
    """
    course = _course(course_id="11111", semester="FALL")
    period = _period("FALL", "Aleph")

    provider = FakeDataProvider(courses=[course], exam_periods=[period])
    generator = FakeGenerator()
    exporter = FakeExporter()

    # threshold_filter provided but threshold_settings=None → filter must be skipped.
    controller = AppController(
        data_provider=provider,
        exporter=exporter,
        generator=generator,
        selected_programs=["83101"],
        threshold_filter=_RejectAllFilter(),
        threshold_settings=None,
    )
    controller.run()

    assert len(exporter.materialized_schedules["FALL - Aleph"]) == 1
