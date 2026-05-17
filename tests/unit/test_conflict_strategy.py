"""
Unit Tests: ExactConflictStrategy
-----------------------------------
Tests for the conflict detection logic in ExactConflictStrategy.

Test cases to implement (use @pytest.mark.parametrize):
    1. Same date, same program, same year, both Obligatory       → conflict (True)
    2. Same date, same program, same year, one Elective          → conflict (True)
    3. Same date, same program, same year, both Elective         → no conflict (False)
    4. Same date, different program, same year                   → no conflict (False)
    5. Same date, same program, different year                   → no conflict (False)

Notes:
    - Use pytest fixtures to build Course and CourseOffering objects.
    - Do NOT test file parsing here — only the conflict logic.
    - Import ExactConflictStrategy from src.adapters.exact_conflict_strategy.
"""
import pytest

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.domain.course import Course
from src.domain.course_offering import CourseOffering


def _course(
    course_id: str,
    program_id: str,
    year: int,
    semester: str,
    requirement: str,
) -> Course:
    #  This is a helper function to quickly create a Course object 
    # and automatically add its offering details (program, year, semester, requirement type).
    course = Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Dr. Test",
        evaluation_type="Exam",
    )
    course.add_offering(
        CourseOffering(
            program_id=program_id,
            year=year,
            semester=semester,
            requirement=requirement,
        )
    )
    return course


@pytest.mark.parametrize(
    "left,right,expected",
    [
        # Case 1: Same program (83101), same year (1), same semester (FALL), both are Obligatory.
        # This MUST cause a conflict (True) because students have to take both exams.
        (
            _course("11111", "83101", 1, "FALL", "Obligatory"),
            _course("22222", "83101", 1, "FALL", "Obligatory"),
            True,
        ),
        # Case 2: Same program, same year, same semester, but one is Obligatory and one is Elective.
        # This STILL causes a conflict (True) because an elective course can still block a mandatory course.
        (
            _course("11111", "83101", 1, "FALL", "Obligatory"),
            _course("22222", "83101", 1, "FALL", "Elective"),
            True,
        ),
        # Case 3: Same program, same year, same semester, but BOTH are Elective courses.
        # This does NOT cause a conflict (False) because students are not required to take both electives.
        
        (
            _course("11111", "83101", 1, "FALL", "Elective"),
            _course("22222", "83101", 1, "FALL", "Elective"),
            False,
        ),
        # Case 4: Different programs (83101 vs 83102), same year, same semester.
        # This does NOT cause a conflict (False) because these are two completely different student groups.
        (
            _course("11111", "83101", 1, "FALL", "Obligatory"),
            _course("22222", "83102", 1, "FALL", "Obligatory"),
            False,
        ),
        # Case 5: Same program, but different academic years (Year 1 vs Year 2).
        # This does NOT cause a conflict (False) because first-year and second-year students take different exams.
        (
            _course("11111", "83101", 1, "FALL", "Obligatory"),
            _course("22222", "83101", 2, "FALL", "Obligatory"),
            False,
        ),
        # Case 6: Same program, same year, but different semesters (FALL vs SPRI).
        # This does NOT cause a conflict (False) because exams in different semesters never happen at the same time.
        (
            _course("11111", "83101", 1, "FALL", "Obligatory"),
            _course("22222", "83101", 1, "SPRI", "Obligatory"),
            False,
        ),
    ],
)
# Explanation: This main test runs all the cases above through the strategy engine
    # using the two active programs ("83101" and "83102") to make sure the outputs match.
def test_exact_conflict_strategy(left, right, expected):
    strategy = ExactConflictStrategy(selected_programs=["83101", "83102"])

    assert strategy.is_conflict(left, right) is expected

# Explanation: This tests the filter logic. If a program (99999) is NOT in the 
    # 'selected_programs' list, the system must ignore it and return False (no conflict).
def test_ignores_programs_that_were_not_selected():
    left = _course("11111", "99999", 1, "FALL", "Obligatory")
    right = _course("22222", "99999", 1, "FALL", "Obligatory")
    strategy = ExactConflictStrategy(selected_programs=["83101"])

    assert strategy.is_conflict(left, right) is False


# Course with no offerings can never conflict — defensive against empty data
def test_no_conflict_when_course_has_no_offerings():
    left = Course(id="11111", name="Empty Course", instructor="Dr. None", evaluation_type="Exam")
    right = _course("22222", "83101", 1, "FALL", "Obligatory")
    strategy = ExactConflictStrategy(selected_programs=["83101"])

    assert strategy.is_conflict(left, right) is False
    assert strategy.is_conflict(right, left) is False


# Multi-program offerings: courses share program 83101 but each ALSO offers a non-selected
# program. The unselected program should not be checked, but 83101 should still trigger.
def test_conflict_detected_across_multi_program_offerings():
    left = Course(id="11111", name="A", instructor="x", evaluation_type="Exam")
    left.add_offering(CourseOffering("83101", 1, "FALL", "Obligatory"))
    left.add_offering(CourseOffering("99999", 1, "FALL", "Obligatory"))  # not selected

    right = Course(id="22222", name="B", instructor="x", evaluation_type="Exam")
    right.add_offering(CourseOffering("83101", 1, "FALL", "Obligatory"))
    right.add_offering(CourseOffering("88888", 1, "FALL", "Obligatory"))  # not selected

    strategy = ExactConflictStrategy(selected_programs=["83101"])
    assert strategy.is_conflict(left, right) is True


# Selected list is empty → no conflicts can be detected (every offering is filtered out)
def test_empty_selected_programs_yields_no_conflicts():
    left = _course("11111", "83101", 1, "FALL", "Obligatory")
    right = _course("22222", "83101", 1, "FALL", "Obligatory")
    strategy = ExactConflictStrategy(selected_programs=[])

    assert strategy.is_conflict(left, right) is False


# Conflict relation should be symmetric: is_conflict(a,b) == is_conflict(b,a)
def test_conflict_is_symmetric():
    left = _course("11111", "83101", 1, "FALL", "Obligatory")
    right = _course("22222", "83101", 1, "FALL", "Elective")
    strategy = ExactConflictStrategy(selected_programs=["83101"])

    assert strategy.is_conflict(left, right) == strategy.is_conflict(right, left)


# Conflict triggered through normalized semester aliases (SPRING vs SPRI must still match)
def test_conflict_with_semester_aliases():
    left = _course("11111", "83101", 1, "SPRING", "Obligatory")
    right = _course("22222", "83101", 1, "SPRI", "Obligatory")
    strategy = ExactConflictStrategy(selected_programs=["83101"])

    assert strategy.is_conflict(left, right) is True