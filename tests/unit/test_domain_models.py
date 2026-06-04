"""
Unit Tests: Domain Models
-------------------------
Additional domain-model tests for immutability, default factories,
semester normalization, and ExamPeriod boundary behavior.

These tests are pure unit tests:
- no PyQt imports
- no QApplication
- no file I/O
"""

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.semester import display_semester, normalize_semester


# ── CourseOffering immutability ─────────────────────────────────────

def test_course_offering_is_immutable():
    """
    CourseOffering is declared with frozen=True, so changing fields after
    construction should be blocked.
    """
    offering = CourseOffering(
        program_id="83101",
        year=1,
        semester="FALL",
        requirement="Obligatory",
    )

    with pytest.raises(FrozenInstanceError):
        offering.program_id = "99999"


def test_course_offering_hashable_when_frozen():
    """
    Frozen dataclasses should be usable in sets/dicts when their fields are
    hashable.
    """
    offering = CourseOffering(
        program_id="83101",
        year=1,
        semester="FALL",
        requirement="Obligatory",
    )

    assert offering in {offering}


# ── Semester normalization/display ──────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("FALL", "FALL"),
        ("fall", "FALL"),
        (" Fall ", "FALL"),
        ("SPRI", "SPRI"),
        ("spring", "SPRI"),
        (" SPRING ", "SPRI"),
        ("SUMM", "SUMM"),
        ("summer", "SUMM"),
        (" SUMMER ", "SUMM"),
    ],
)
def test_normalize_semester_accepts_supported_aliases(raw, expected):
    assert normalize_semester(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("FALL", "FALL"),
        ("SPRI", "SPRING"),
        ("SPRING", "SPRING"),
        ("SUMM", "SUMMER"),
        ("SUMMER", "SUMMER"),
    ],
)
def test_display_semester_returns_user_facing_name(raw, expected):
    assert display_semester(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "WINTER",
        "A",
        "2026",
    ],
)
def test_normalize_semester_rejects_invalid_values(raw):
    with pytest.raises(ValueError, match="Invalid semester"):
        normalize_semester(raw)


# ── Default factories do not share mutable state ────────────────────

def test_course_offerings_default_factory_does_not_share_list():
    """
    Course.offerings uses default_factory=list, so two Course instances should
    not share the same offerings list.
    """
    first = Course(
        id="11111",
        name="Calculus",
        instructor="Dr. Cohen",
        evaluation_type="Exam",
    )
    second = Course(
        id="22222",
        name="Algorithms",
        instructor="Dr. Levi",
        evaluation_type="Exam",
    )

    first.add_offering(
        CourseOffering(
            program_id="83101",
            year=1,
            semester="FALL",
            requirement="Obligatory",
        )
    )

    assert len(first.offerings) == 1
    assert second.offerings == []


def test_exam_period_excluded_dates_default_factory_does_not_share_set():
    """
    ExamPeriod.excluded_dates uses default_factory=set, so excluded dates added
    to one period should not appear in another period.
    """
    first = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 6))],
    )
    second = ExamPeriod(
        semester="FALL",
        moed="Bet",
        date_ranges=[(date(2026, 1, 7), date(2026, 1, 8))],
    )

    first.excluded_dates.add(date(2026, 1, 5))

    assert date(2026, 1, 5) in first.excluded_dates
    assert second.excluded_dates == set()


def test_schedule_assignments_default_factory_does_not_share_dict():
    """
    Schedule.assignments uses default_factory=dict, so assignments added to one
    schedule should not appear in another schedule.
    """
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 6))],
    )

    first = Schedule(period=period)
    second = Schedule(period=period)

    first.assignments["11111"] = date(2026, 1, 5)

    assert first.assignments == {"11111": date(2026, 1, 5)}
    assert second.assignments == {}


# ── ExamPeriod boundaries ───────────────────────────────────────────

def test_exam_period_overall_boundaries_for_single_range():
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 9))],
    )

    assert period.get_overall_date_boundaries() == (
        date(2026, 1, 5),
        date(2026, 1, 9),
    )


def test_exam_period_overall_boundaries_for_multiple_ranges():
    """
    Boundaries should use the earliest start and latest end across all ranges,
    even if the ranges are not ordered.
    """
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[
            (date(2026, 1, 20), date(2026, 1, 25)),
            (date(2026, 1, 5), date(2026, 1, 9)),
            (date(2026, 1, 12), date(2026, 1, 15)),
        ],
    )

    assert period.get_overall_date_boundaries() == (
        date(2026, 1, 5),
        date(2026, 1, 25),
    )


def test_exam_period_overall_boundaries_rejects_empty_ranges():
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[],
    )

    with pytest.raises(ValueError, match="ExamPeriod has no date ranges"):
        period.get_overall_date_boundaries()
