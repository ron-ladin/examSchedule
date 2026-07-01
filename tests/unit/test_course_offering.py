"""
Unit Tests: CourseOffering
---------------------------
Tests for CourseOffering domain entity logic.
"""
import pytest
from src.domain.course_offering import CourseOffering


def _make_offering(program_id="83101", year=1, semester="FALL", requirement="Obligatory"):
    return CourseOffering(
        program_id=program_id,
        year=year,
        semester=semester,
        requirement=requirement,
    )


@pytest.mark.unit
def test_is_relevant_true_when_program_and_semester_match():
    offering = _make_offering(program_id="83101", semester="FALL")
    assert offering.is_relevant(["83101"], "FALL") is True


@pytest.mark.unit
def test_is_relevant_false_when_program_not_selected():
    offering = _make_offering(program_id="83101", semester="FALL")
    assert offering.is_relevant(["83102"], "FALL") is False


@pytest.mark.unit
def test_is_relevant_false_when_semester_does_not_match():
    offering = _make_offering(program_id="83101", semester="SPRI")
    assert offering.is_relevant(["83101"], "FALL") is False


@pytest.mark.unit
def test_is_relevant_normalizes_semester_variants():
    offering = _make_offering(program_id="83101", semester="SPRING")
    assert offering.is_relevant(["83101"], "SPRI") is True


@pytest.mark.unit
def test_same_program_year_semester_true_for_identical_offering():
    o1 = _make_offering(program_id="83101", year=1, semester="FALL")
    o2 = _make_offering(program_id="83101", year=1, semester="FALL")
    assert o1.same_program_year_semester(o2) is True


@pytest.mark.unit
def test_same_program_year_semester_false_for_different_program():
    o1 = _make_offering(program_id="83101", year=1, semester="FALL")
    o2 = _make_offering(program_id="83102", year=1, semester="FALL")
    assert o1.same_program_year_semester(o2) is False


@pytest.mark.unit
def test_same_program_year_semester_false_for_different_year():
    o1 = _make_offering(program_id="83101", year=1, semester="FALL")
    o2 = _make_offering(program_id="83101", year=2, semester="FALL")
    assert o1.same_program_year_semester(o2) is False


@pytest.mark.unit
def test_same_program_year_semester_false_for_different_semester():
    o1 = _make_offering(program_id="83101", year=1, semester="FALL")
    o2 = _make_offering(program_id="83101", year=1, semester="SPRI")
    assert o1.same_program_year_semester(o2) is False


@pytest.mark.unit
def test_is_elective_true_for_elective():
    offering = _make_offering(requirement="Elective")
    assert offering.is_elective() is True


@pytest.mark.unit
def test_is_elective_false_for_obligatory():
    offering = _make_offering(requirement="Obligatory")
    assert offering.is_elective() is False


def test_student_count_bool_true_rejected():
    # bool is a subclass of int; True == 1 would silently pass without the guard
    import pytest
    with pytest.raises(ValueError):
        CourseOffering(
            program_id="83101",
            year=1,
            semester="FALL",
            requirement="Obligatory",
            student_count=True,
        )


def test_student_count_bool_false_rejected():
    import pytest
    with pytest.raises(ValueError):
        CourseOffering(
            program_id="83101",
            year=1,
            semester="FALL",
            requirement="Obligatory",
            student_count=False,
        )
