"""
Unit Tests: CourseOffering
---------------------------
Tests for CourseOffering domain entity logic.
"""
from src.domain.course_offering import CourseOffering


def _make_offering(program_id="83101", year=1, semester="FALL", requirement="Obligatory"):
    return CourseOffering(
        program_id=program_id,
        year=year,
        semester=semester,
        requirement=requirement,
    )


def test_is_relevant_true_when_program_and_semester_match():
    offering = _make_offering(program_id="83101", semester="FALL")
    assert offering.is_relevant(["83101"], "FALL") is True


def test_is_relevant_false_when_program_not_selected():
    offering = _make_offering(program_id="83101", semester="FALL")
    assert offering.is_relevant(["83102"], "FALL") is False


def test_is_relevant_false_when_semester_does_not_match():
    offering = _make_offering(program_id="83101", semester="SPRI")
    assert offering.is_relevant(["83101"], "FALL") is False


def test_is_relevant_normalizes_semester_variants():
    offering = _make_offering(program_id="83101", semester="SPRING")
    assert offering.is_relevant(["83101"], "SPRI") is True


def test_same_program_year_semester_true_for_identical_offering():
    o1 = _make_offering(program_id="83101", year=1, semester="FALL")
    o2 = _make_offering(program_id="83101", year=1, semester="FALL")
    assert o1.same_program_year_semester(o2) is True


def test_same_program_year_semester_false_for_different_program():
    o1 = _make_offering(program_id="83101", year=1, semester="FALL")
    o2 = _make_offering(program_id="83102", year=1, semester="FALL")
    assert o1.same_program_year_semester(o2) is False


def test_same_program_year_semester_false_for_different_year():
    o1 = _make_offering(program_id="83101", year=1, semester="FALL")
    o2 = _make_offering(program_id="83101", year=2, semester="FALL")
    assert o1.same_program_year_semester(o2) is False


def test_same_program_year_semester_false_for_different_semester():
    o1 = _make_offering(program_id="83101", year=1, semester="FALL")
    o2 = _make_offering(program_id="83101", year=1, semester="SPRI")
    assert o1.same_program_year_semester(o2) is False


def test_is_elective_true_for_elective():
    offering = _make_offering(requirement="Elective")
    assert offering.is_elective() is True


def test_is_elective_false_for_obligatory():
    offering = _make_offering(requirement="Obligatory")
    assert offering.is_elective() is False


def test_student_count_valid_zero():
    o = CourseOffering("83101", 1, "FALL", "Obligatory", student_count=0)
    assert o.student_count == 0


def test_student_count_rejects_negative():
    import pytest
    with pytest.raises(ValueError, match="non-negative"):
        CourseOffering("83101", 1, "FALL", "Obligatory", student_count=-1)


def test_student_count_rejects_bool():
    import pytest
    with pytest.raises(ValueError, match="non-negative"):
        CourseOffering("83101", 1, "FALL", "Obligatory", student_count=True)
