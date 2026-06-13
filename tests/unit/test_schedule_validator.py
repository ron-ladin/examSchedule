"""
Unit Tests: schedule_validator (engine layer)
----------------------------------------------
Proves the engine-level threshold wiring actually drops schedules that
violate an *enabled* threshold criterion, and passes everything through
untouched when no criterion is enabled (spec 2.1-2.5).
"""

from datetime import date

from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.threshold import Criterion, ThresholdEntry, ThresholdSettings
from src.engine.schedule_validator import filter_schedules


def _period() -> ExamPeriod:
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 9))],
    )


def _two_mandatory_courses() -> list[Course]:
    """Two obligatory courses in the same program (83101) and year (1)."""
    c1 = Course(id="11111", name="Calculus", instructor="X", evaluation_type="Exam")
    c1.add_offering(CourseOffering("83101", 1, "FALL", "Obligatory"))
    c2 = Course(id="22222", name="Algebra", instructor="Y", evaluation_type="Exam")
    c2.add_offering(CourseOffering("83101", 1, "FALL", "Obligatory"))
    return [c1, c2]


def _schedule(gap_days: int) -> Schedule:
    """Schedule with the two mandatory exams `gap_days` apart."""
    return Schedule(
        period=_period(),
        assignments={
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 5 + gap_days),
        },
    )


def test_filter_drops_schedule_violating_enabled_threshold():
    # Arrange — require >= 2 days between mandatory exams (spec 2.1).
    courses = _two_mandatory_courses()
    valid = _schedule(gap_days=2)
    invalid = _schedule(gap_days=1)
    settings = ThresholdSettings(
        entries=(
            ThresholdEntry(Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS, enabled=True, k=2),
        )
    )

    # Act
    result = filter_schedules([valid, invalid], courses, settings)

    # Assert — only the conforming schedule survives.
    assert result == [valid]


def test_filter_keeps_all_when_criterion_disabled():
    courses = _two_mandatory_courses()
    valid = _schedule(gap_days=2)
    invalid = _schedule(gap_days=1)
    settings = ThresholdSettings(
        entries=(
            ThresholdEntry(Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS, enabled=False, k=2),
        )
    )

    result = filter_schedules([valid, invalid], courses, settings)

    assert result == [valid, invalid]


def test_filter_keeps_all_when_no_thresholds_configured():
    courses = _two_mandatory_courses()
    schedules = [_schedule(gap_days=2), _schedule(gap_days=1)]

    result = filter_schedules(schedules, courses, ThresholdSettings())

    assert result == schedules


def test_filter_returns_new_list_without_mutating_input():
    courses = _two_mandatory_courses()
    schedules = [_schedule(gap_days=1)]
    settings = ThresholdSettings(
        entries=(
            ThresholdEntry(Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS, enabled=True, k=2),
        )
    )

    result = filter_schedules(schedules, courses, settings)

    assert result == []
    assert len(schedules) == 1  # input untouched
