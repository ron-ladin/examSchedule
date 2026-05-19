"""
Unit Tests: ExactConflictStrategy
-----------------------------------
Tests for the conflict detection logic in ExactConflictStrategy.
"""
import pytest

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.domain.course import Course
from src.domain.course_offering import CourseOffering


def _course(course_id: str, program_id: str, year: int, semester: str, requirement: str) -> Course:
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


@pytest.mark.parametrize(
    "left,right,expected",
    [
        (_course("11111", "83101", 1, "FALL", "Obligatory"), _course("22222", "83101", 1, "FALL", "Obligatory"), True),
        (_course("11111", "83101", 1, "FALL", "Obligatory"), _course("22222", "83101", 1, "FALL", "Elective"),   True),
        (_course("11111", "83101", 1, "FALL", "Elective"),   _course("22222", "83101", 1, "FALL", "Elective"),   False),
        (_course("11111", "83101", 1, "FALL", "Obligatory"), _course("22222", "83102", 1, "FALL", "Obligatory"), False),
        (_course("11111", "83101", 1, "FALL", "Obligatory"), _course("22222", "83101", 2, "FALL", "Obligatory"), False),
        (_course("11111", "83101", 1, "FALL", "Obligatory"), _course("22222", "83101", 1, "SPRI", "Obligatory"), False),
    ],
)
def test_exact_conflict_strategy(left, right, expected):
    strategy = ExactConflictStrategy(selected_programs=["83101", "83102"])
    assert strategy.is_conflict(left, right) is expected


def test_ignores_programs_that_were_not_selected():
    left = _course("11111", "99999", 1, "FALL", "Obligatory")
    right = _course("22222", "99999", 1, "FALL", "Obligatory")
    assert ExactConflictStrategy(["83101"]).is_conflict(left, right) is False


def test_no_conflict_when_course_has_no_offerings():
    left = Course(id="11111", name="Empty", instructor="x", evaluation_type="Exam")
    right = _course("22222", "83101", 1, "FALL", "Obligatory")
    strategy = ExactConflictStrategy(["83101"])
    assert strategy.is_conflict(left, right) is False
    assert strategy.is_conflict(right, left) is False


def test_conflict_detected_across_multi_program_offerings():
    left = Course(id="11111", name="A", instructor="x", evaluation_type="Exam")
    left.add_offering(CourseOffering("83101", 1, "FALL", "Obligatory"))
    left.add_offering(CourseOffering("99999", 1, "FALL", "Obligatory"))  # not selected

    right = Course(id="22222", name="B", instructor="x", evaluation_type="Exam")
    right.add_offering(CourseOffering("83101", 1, "FALL", "Obligatory"))
    right.add_offering(CourseOffering("88888", 1, "FALL", "Obligatory"))  # not selected

    assert ExactConflictStrategy(["83101"]).is_conflict(left, right) is True


def test_empty_selected_programs_yields_no_conflicts():
    left = _course("11111", "83101", 1, "FALL", "Obligatory")
    right = _course("22222", "83101", 1, "FALL", "Obligatory")
    assert ExactConflictStrategy([]).is_conflict(left, right) is False


def test_conflict_with_semester_aliases():
    left = _course("11111", "83101", 1, "SPRING", "Obligatory")
    right = _course("22222", "83101", 1, "SPRI",   "Obligatory")
    assert ExactConflictStrategy(["83101"]).is_conflict(left, right) is True


# A course offered in year 1 AND year 2 must only conflict with courses in the matching year
def test_conflict_only_for_matching_year_in_multi_year_offering():
    multi_year = Course(id="11111", name="Multi", instructor="x", evaluation_type="Exam")
    multi_year.add_offering(CourseOffering("83101", 1, "FALL", "Obligatory"))
    multi_year.add_offering(CourseOffering("83101", 2, "FALL", "Obligatory"))

    year2 = _course("22222", "83101", 2, "FALL", "Obligatory")
    year3 = _course("33333", "83101", 3, "FALL", "Obligatory")

    strategy = ExactConflictStrategy(["83101"])
    assert strategy.is_conflict(multi_year, year2) is True
    assert strategy.is_conflict(multi_year, year3) is False
