from datetime import date

import pytest

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.domain.course import Course
from src.domain.course_offering import CourseOffering


def _course(course_id: str, offering: CourseOffering) -> Course:
    return Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Dr. Test",
        evaluation_type="Exam",
        offerings=[offering],
    )


@pytest.mark.parametrize(
    ("offering1", "offering2", "expected"),
    [
        (
            CourseOffering("83101", 1, "FALL", "Obligatory"),
            CourseOffering("83101", 1, "FALL", "Obligatory"),
            True,
        ),
        (
            CourseOffering("83101", 1, "FALL", "Obligatory"),
            CourseOffering("83101", 1, "FALL", "Elective"),
            True,
        ),
        (
            CourseOffering("83101", 1, "FALL", "Elective"),
            CourseOffering("83101", 1, "FALL", "Elective"),
            False,
        ),
        (
            CourseOffering("83101", 1, "FALL", "Obligatory"),
            CourseOffering("83102", 1, "FALL", "Obligatory"),
            False,
        ),
        (
            CourseOffering("83101", 1, "FALL", "Obligatory"),
            CourseOffering("83101", 2, "FALL", "Obligatory"),
            False,
        ),
    ],
)
def test_conflict_rule_for_selected_programs(offering1, offering2, expected):
    strategy = ExactConflictStrategy(selected_programs=["83101"])
    course1 = _course("11111", offering1)
    course2 = _course("22222", offering2)

    assert strategy.is_conflict(course1, course2, date(2026, 1, 1)) is expected


def test_ignores_programs_that_were_not_selected():
    strategy = ExactConflictStrategy(selected_programs=["83101"])
    course1 = _course("11111", CourseOffering("83102", 1, "FALL", "Obligatory"))
    course2 = _course("22222", CourseOffering("83102", 1, "FALL", "Obligatory"))

    assert strategy.is_conflict(course1, course2, date(2026, 1, 1)) is False
