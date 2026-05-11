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
from datetime import date
from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.domain.course import Course
from src.domain.course_offering import CourseOffering

def make_course(off):
    return Course(
        id="99999",
        name="Dummy",
        instructor="Dr Test",
        evaluation_type="Exam",
        offerings=[off]
    )

def test_is_conflict_various_scenarios():
    strategy = ExactConflictStrategy()
    test_date = date(2026, 5, 11)
    # 1. Same program, same year, same semester, both Obligatory -> conflict
    o1 = CourseOffering("12345", 1, "FALL", "Obligatory")
    o2 = CourseOffering("12345", 1, "FALL", "Obligatory")
    assert strategy.is_conflict(make_course(o1), make_course(o2), test_date)
    # 2. Same program/year/semester, one Elective -> conflict
    o1 = CourseOffering("12345", 1, "FALL", "Obligatory")
    o2 = CourseOffering("12345", 1, "FALL", "Elective")
    assert strategy.is_conflict(make_course(o1), make_course(o2), test_date)
    # 3. Same program/year/semester, both Elective -> no conflict
    o1 = CourseOffering("12345", 1, "FALL", "Elective")
    o2 = CourseOffering("12345", 1, "FALL", "Elective")
    assert not strategy.is_conflict(make_course(o1), make_course(o2), test_date)
    # 4. Different program -> no conflict
    o1 = CourseOffering("12345", 1, "FALL", "Obligatory")
    o2 = CourseOffering("54321", 1, "FALL", "Obligatory")
    assert not strategy.is_conflict(make_course(o1), make_course(o2), test_date)
    # 5. Same program + semester, different year -> no conflict
    o1 = CourseOffering("12345", 1, "FALL", "Obligatory")
    o2 = CourseOffering("12345", 2, "FALL", "Obligatory")
    assert not strategy.is_conflict(make_course(o1), make_course(o2), test_date)
    # 6. Same program + year, different semester -> no conflict
    o1 = CourseOffering("12345", 1, "FALL", "Obligatory")
    o2 = CourseOffering("12345", 1, "SPRI", "Obligatory")
    assert not strategy.is_conflict(make_course(o1), make_course(o2), test_date)