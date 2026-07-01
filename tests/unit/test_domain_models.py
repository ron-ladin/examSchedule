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

def test_course_offering_is_frozen_and_hashable():
    """CourseOffering is frozen=True: field assignment is blocked and instances
    are usable in sets/dicts."""
    offering = CourseOffering(
        program_id="83101",
        year=1,
        semester="FALL",
        requirement="Obligatory",
    )

    with pytest.raises(FrozenInstanceError):
        offering.program_id = "99999"
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

def test_default_factories_do_not_share_mutable_state():
    """Course.offerings (list), ExamPeriod.excluded_dates (set), and
    Schedule.assignments (dict) each use a default_factory, so mutating one
    instance must never leak into a sibling instance."""
    # Course.offerings
    course_a = Course(id="11111", name="Calculus", instructor="Dr. Cohen", evaluation_type="Exam")
    course_b = Course(id="22222", name="Algorithms", instructor="Dr. Levi", evaluation_type="Exam")
    course_a.add_offering(
        CourseOffering(program_id="83101", year=1, semester="FALL", requirement="Obligatory")
    )
    assert len(course_a.offerings) == 1
    assert course_b.offerings == []

    # ExamPeriod.excluded_dates
    period_a = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 6))])
    period_b = ExamPeriod("FALL", "Bet", [(date(2026, 1, 7), date(2026, 1, 8))])
    period_a.excluded_dates.add(date(2026, 1, 5))
    assert date(2026, 1, 5) in period_a.excluded_dates
    assert period_b.excluded_dates == set()

    # Schedule.assignments
    sched_a = Schedule(period=period_a)
    sched_b = Schedule(period=period_a)
    sched_a.assignments["11111"] = date(2026, 1, 5)
    assert sched_a.assignments == {"11111": date(2026, 1, 5)}
    assert sched_b.assignments == {}


# ── ExamPeriod boundaries ───────────────────────────────────────────

@pytest.mark.parametrize(
    "date_ranges,expected",
    [
        # Single range -> its own start/end.
        ([(date(2026, 1, 5), date(2026, 1, 9))], (date(2026, 1, 5), date(2026, 1, 9))),
        # Multiple unordered ranges -> earliest start, latest end.
        (
            [
                (date(2026, 1, 20), date(2026, 1, 25)),
                (date(2026, 1, 5), date(2026, 1, 9)),
                (date(2026, 1, 12), date(2026, 1, 15)),
            ],
            (date(2026, 1, 5), date(2026, 1, 25)),
        ),
    ],
    ids=["single_range", "multiple_unordered_ranges"],
)
def test_exam_period_overall_boundaries(date_ranges, expected):
    period = ExamPeriod(semester="FALL", moed="Aleph", date_ranges=date_ranges)
    assert period.get_overall_date_boundaries() == expected


def test_exam_period_overall_boundaries_rejects_empty_ranges():
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[],
    )

    with pytest.raises(ValueError, match="ExamPeriod has no date ranges"):
        period.get_overall_date_boundaries()
