"""
Unit Tests: Schedule
---------------------
Tests for Schedule domain entity.
"""
from datetime import date

from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule


def _make_period():
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 10))],
    )


def test_schedule_stores_period():
    period = _make_period()
    schedule = Schedule(period=period)
    assert schedule.period is period


def test_schedule_assignments_empty_by_default():
    schedule = Schedule(period=_make_period())
    assert schedule.assignments == {}


def test_schedule_assignments_map_course_id_to_date():
    schedule = Schedule(
        period=_make_period(),
        assignments={"11111": date(2026, 1, 5)},
    )
    assert schedule.assignments["11111"] == date(2026, 1, 5)


def test_schedule_stores_multiple_assignments():
    assignments = {
        "11111": date(2026, 1, 5),
        "22222": date(2026, 1, 6),
        "33333": date(2026, 1, 7),
    }
    schedule = Schedule(period=_make_period(), assignments=assignments)
    assert len(schedule.assignments) == 3
    assert schedule.assignments["22222"] == date(2026, 1, 6)


def test_schedule_assignments_use_string_course_ids():
    schedule = Schedule(
        period=_make_period(),
        assignments={"11111": date(2026, 1, 5)},
    )
    assert all(isinstance(k, str) for k in schedule.assignments.keys())


def test_two_schedules_with_same_data_are_equal():
    period = _make_period()
    s1 = Schedule(period=period, assignments={"11111": date(2026, 1, 5)})
    s2 = Schedule(period=period, assignments={"11111": date(2026, 1, 5)})
    assert s1 == s2
