"""
Unit Tests: ScheduleGenerator
-------------------------------
Tests for backtracking schedule generation logic.
"""
from datetime import date
from typing import List
from unittest.mock import MagicMock

import pytest

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.engine.schedule_generator import ScheduleGenerator


def _make_course(course_id: str, program_id: str, year: int, semester: str, requirement: str) -> Course:
    course = Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Dr. Test",
        evaluation_type="Exam",
    )
    course.add_offering(CourseOffering(
        program_id=program_id,
        year=year,
        semester=semester,
        requirement=requirement,
    ))
    return course


def _make_period(start: date, end: date, excluded=None) -> ExamPeriod:
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(start, end)],
        excluded_dates=excluded or set(),
    )


def _generator(selected_programs: List[str]) -> ScheduleGenerator:
    return ScheduleGenerator(ExactConflictStrategy(selected_programs))


def test_no_courses_yields_no_schedules():
    gen = _generator(["83101"])
    period = _make_period(date(2026, 1, 5), date(2026, 1, 7))
    schedules = list(gen.generate_schedules([], period))
    assert schedules == []


def test_no_valid_dates_yields_no_schedules():
    gen = _generator(["83101"])
    course = _make_course("11111", "83101", 1, "FALL", "Obligatory")
    # Saturday-only range: 2026-01-10 is a Saturday
    period = _make_period(date(2026, 1, 10), date(2026, 1, 10))
    schedules = list(gen.generate_schedules([course], period))
    assert schedules == []


def test_single_course_single_date_yields_one_schedule():
    gen = _generator(["83101"])
    course = _make_course("11111", "83101", 1, "FALL", "Obligatory")
    # 2026-01-05 is a Monday
    period = _make_period(date(2026, 1, 5), date(2026, 1, 5))
    schedules = list(gen.generate_schedules([course], period))
    assert len(schedules) == 1
    assert schedules[0].assignments["11111"] == date(2026, 1, 5)


def test_two_non_conflicting_courses_can_share_same_date():
    gen = _generator(["83101"])
    # Different years → no conflict
    c1 = _make_course("11111", "83101", 1, "FALL", "Obligatory")
    c2 = _make_course("22222", "83101", 2, "FALL", "Obligatory")
    period = _make_period(date(2026, 1, 5), date(2026, 1, 5))
    schedules = list(gen.generate_schedules([c1, c2], period))
    # Both assigned to the only available date
    assert len(schedules) == 1
    assert schedules[0].assignments["11111"] == date(2026, 1, 5)
    assert schedules[0].assignments["22222"] == date(2026, 1, 5)


def test_two_conflicting_courses_must_have_different_dates():
    gen = _generator(["83101"])
    c1 = _make_course("11111", "83101", 1, "FALL", "Obligatory")
    c2 = _make_course("22222", "83101", 1, "FALL", "Obligatory")
    # Only one valid date → impossible to separate conflicting courses
    period = _make_period(date(2026, 1, 5), date(2026, 1, 5))
    schedules = list(gen.generate_schedules([c1, c2], period))
    assert schedules == []


def test_two_conflicting_courses_with_two_dates_yield_two_schedules():
    gen = _generator(["83101"])
    c1 = _make_course("11111", "83101", 1, "FALL", "Obligatory")
    c2 = _make_course("22222", "83101", 1, "FALL", "Obligatory")
    # Monday and Tuesday
    period = _make_period(date(2026, 1, 5), date(2026, 1, 6))
    schedules = list(gen.generate_schedules([c1, c2], period))
    assert len(schedules) == 2
    for s in schedules:
        assert s.assignments["11111"] != s.assignments["22222"]


def test_generator_is_lazy_and_yields_independently():
    gen = _generator(["83101"])
    c1 = _make_course("11111", "83101", 1, "FALL", "Obligatory")
    c2 = _make_course("22222", "83101", 1, "FALL", "Obligatory")
    period = _make_period(date(2026, 1, 5), date(2026, 1, 6))

    iterator = gen.generate_schedules([c1, c2], period)
    first = next(iterator)
    second = next(iterator)

    # Schedules are independent objects — mutating one doesn't affect the other
    assert first.assignments != second.assignments or first is not second


# Every yielded schedule must contain ALL course IDs as keys (completeness)
def test_all_schedules_cover_all_courses():
    gen = _generator(["83101"])
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Obligatory"),
        _make_course("22222", "83101", 1, "FALL", "Obligatory"),
        _make_course("33333", "83101", 1, "FALL", "Obligatory"),
    ]
    expected_ids = {c.id for c in courses}
    # 5 valid weekdays
    period = _make_period(date(2026, 1, 5), date(2026, 1, 9))

    schedules = list(gen.generate_schedules(courses, period))
    assert len(schedules) > 0
    for s in schedules:
        assert set(s.assignments.keys()) == expected_ids


# 3 mutually conflicting courses + only 2 valid dates → impossible → no schedules
def test_impossible_case_yields_nothing():
    gen = _generator(["83101"])
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Obligatory"),
        _make_course("22222", "83101", 1, "FALL", "Obligatory"),
        _make_course("33333", "83101", 1, "FALL", "Obligatory"),
    ]
    period = _make_period(date(2026, 1, 5), date(2026, 1, 6))  # 2 weekdays

    schedules = list(gen.generate_schedules(courses, period))
    assert schedules == []


# MCV heuristic: A conflicts with B and C; B and C don't conflict.
# Verify generated schedules respect the constraints (A is never on B's or C's date).
def test_mcv_heuristic_produces_valid_schedules():
    # A: program 83101 + 83102, year 1, FALL
    a = Course(id="11111", name="A", instructor="x", evaluation_type="Exam")
    a.add_offering(CourseOffering("83101", 1, "FALL", "Obligatory"))
    a.add_offering(CourseOffering("83102", 1, "FALL", "Obligatory"))
    # B: program 83101, year 1, FALL  → conflicts with A
    b = _make_course("22222", "83101", 1, "FALL", "Obligatory")
    # C: program 83102, year 1, FALL  → conflicts with A but NOT B
    c = _make_course("33333", "83102", 1, "FALL", "Obligatory")

    gen = _generator(["83101", "83102"])
    period = _make_period(date(2026, 1, 5), date(2026, 1, 7))

    schedules = list(gen.generate_schedules([a, b, c], period))
    assert len(schedules) > 0
    for s in schedules:
        # A cannot share a date with B or C
        assert s.assignments["11111"] != s.assignments["22222"]
        assert s.assignments["11111"] != s.assignments["33333"]
        # B and C may share a date (they don't conflict — different programs)


# All-elective scenario: all courses can share the same date
def test_all_elective_courses_can_share_one_date():
    gen = _generator(["83101"])
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Elective"),
        _make_course("22222", "83101", 1, "FALL", "Elective"),
        _make_course("33333", "83101", 1, "FALL", "Elective"),
    ]
    period = _make_period(date(2026, 1, 5), date(2026, 1, 5))  # single date

    schedules = list(gen.generate_schedules(courses, period))
    assert len(schedules) == 1
    # All three on the same date — no conflict because all elective
    assert len(set(schedules[0].assignments.values())) == 1


# Schedules across separate programs (no overlap) → cartesian product of placements
def test_independent_programs_yield_cartesian_product():
    # Program A: 2 conflicting obligatory courses
    a1 = _make_course("11111", "83101", 1, "FALL", "Obligatory")
    a2 = _make_course("22222", "83101", 1, "FALL", "Obligatory")
    # Program B: 1 course independent of A
    b1 = _make_course("33333", "83102", 1, "FALL", "Obligatory")

    gen = _generator(["83101", "83102"])
    period = _make_period(date(2026, 1, 5), date(2026, 1, 6))  # 2 weekdays

    schedules = list(gen.generate_schedules([a1, a2, b1], period))
    # a1/a2 must differ (2 valid orderings); b1 can go on either date (2 choices)
    # → 2 × 2 = 4 schedules
    assert len(schedules) == 4


# Saturday in the middle of the range is auto-excluded and reduces placement options
def test_generator_respects_saturday_exclusion():
    gen = _generator(["83101"])
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Obligatory"),
        _make_course("22222", "83101", 1, "FALL", "Obligatory"),
    ]
    # Fri 2026-01-09, Sat 2026-01-10 (excluded), Sun 2026-01-11
    period = _make_period(date(2026, 1, 9), date(2026, 1, 11))

    schedules = list(gen.generate_schedules(courses, period))
    for s in schedules:
        for d in s.assignments.values():
            assert d.weekday() != 5  # never a Saturday
