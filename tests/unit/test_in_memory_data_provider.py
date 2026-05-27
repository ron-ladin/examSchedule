"""
Unit Tests: InMemoryDataProvider
----------------------------------
Tests for the in-memory IDataProvider adapter used by the desktop UI.
"""
from datetime import date

import pytest

from src.adapters.in_memory_data_provider import InMemoryDataProvider
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_course(course_id: str = "11111") -> Course:
    c = Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Dr. Test",
        evaluation_type="Exam",
    )
    c.offerings = [
        CourseOffering(program_id="83101", year=1, semester="FALL", requirement="Obligatory")
    ]
    return c


def _make_period() -> ExamPeriod:
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 9))],
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_get_courses_returns_all_provided_courses():
    courses = [_make_course("11111"), _make_course("22222")]
    provider = InMemoryDataProvider(courses=courses, exam_periods=[], selected_programs=[])
    assert provider.get_courses() == courses


def test_get_exam_periods_returns_all_provided_periods():
    periods = [_make_period()]
    provider = InMemoryDataProvider(courses=[], exam_periods=periods, selected_programs=[])
    assert provider.get_exam_periods() == periods


def test_get_selected_programs_returns_provided_ids():
    provider = InMemoryDataProvider(
        courses=[], exam_periods=[], selected_programs=["83101", "83102"]
    )
    assert provider.get_selected_programs() == ["83101", "83102"]


def test_selected_programs_defaults_to_empty_list_when_none():
    """Passing selected_programs=None (or omitting it) must not raise and returns []."""
    provider = InMemoryDataProvider(courses=[], exam_periods=[])
    assert provider.get_selected_programs() == []


def test_constructor_copies_lists_not_references():
    """Mutating the original lists after construction must not affect the provider."""
    courses = [_make_course("11111")]
    periods = [_make_period()]
    programs = ["83101"]
    provider = InMemoryDataProvider(courses, periods, programs)

    courses.append(_make_course("99999"))
    periods.clear()
    programs.append("83102")

    assert len(provider.get_courses()) == 1
    assert len(provider.get_exam_periods()) == 1
    assert provider.get_selected_programs() == ["83101"]


def test_empty_provider_returns_empty_collections():
    provider = InMemoryDataProvider(courses=[], exam_periods=[], selected_programs=[])
    assert provider.get_courses() == []
    assert provider.get_exam_periods() == []
    assert provider.get_selected_programs() == []
