"""
Unit Tests: Course
-------------------
Tests for Course domain entity logic.
"""
import pytest

from src.domain.course import Course
from src.domain.course_offering import CourseOffering


def _make_course(course_id="11111", evaluation_type="Exam"):
    return Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Dr. Test",
        evaluation_type=evaluation_type,
    )


def _make_offering(program_id="83101", year=1, semester="FALL", requirement="Obligatory"):
    return CourseOffering(
        program_id=program_id,
        year=year,
        semester=semester,
        requirement=requirement,
    )


def test_has_exam_returns_true_for_exam():
    course = _make_course(evaluation_type="Exam")
    assert course.has_exam() is True


def test_has_exam_returns_false_for_project():
    course = _make_course(evaluation_type="Project")
    assert course.has_exam() is False


def test_has_exam_is_case_insensitive():
    course = _make_course(evaluation_type="  exam  ")
    assert course.has_exam() is True


def test_equality_by_id_same_id_different_name():
    c1 = Course(id="11111", name="Calculus", instructor="Dr. A", evaluation_type="Exam")
    c2 = Course(id="11111", name="Different Name", instructor="Dr. B", evaluation_type="Project")
    assert c1 == c2


def test_inequality_different_ids():
    c1 = _make_course(course_id="11111")
    c2 = _make_course(course_id="22222")
    assert c1 != c2


def test_hash_consistent_with_id():
    c1 = Course(id="11111", name="Calculus", instructor="Dr. A", evaluation_type="Exam")
    c2 = Course(id="11111", name="Different Name", instructor="Dr. B", evaluation_type="Project")
    assert hash(c1) == hash(c2)


def test_course_usable_in_set():
    c1 = _make_course(course_id="11111")
    c2 = _make_course(course_id="11111")
    assert len({c1, c2}) == 1


def test_get_relevant_offerings_filters_by_program_and_semester():
    course = _make_course()
    o1 = _make_offering(program_id="83101", semester="FALL")
    o2 = _make_offering(program_id="83102", semester="FALL")
    o3 = _make_offering(program_id="83101", semester="SPRI")
    course.add_offering(o1)
    course.add_offering(o2)
    course.add_offering(o3)

    relevant = course.get_relevant_offerings(["83101"], "FALL")
    assert relevant == [o1]


def test_is_relevant_for_period_true_when_exam_and_offering_matches():
    course = _make_course()
    course.add_offering(_make_offering(program_id="83101", semester="FALL"))
    assert course.is_relevant_for_period(["83101"], "FALL") is True


def test_is_relevant_for_period_false_when_not_exam():
    course = _make_course(evaluation_type="Project")
    course.add_offering(_make_offering(program_id="83101", semester="FALL"))
    assert course.is_relevant_for_period(["83101"], "FALL") is False


def test_is_relevant_for_period_false_when_no_matching_offering():
    course = _make_course()
    course.add_offering(_make_offering(program_id="83101", semester="SPRI"))
    assert course.is_relevant_for_period(["83101"], "FALL") is False


def test_get_relevant_offerings_with_no_offerings_returns_empty():
    course = _make_course()
    assert course.get_relevant_offerings(["83101"], "FALL") == []
