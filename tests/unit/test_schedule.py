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


def test_schedule_stores_multiple_assignments():
    assignments = {
        "11111": date(2026, 1, 5),
        "22222": date(2026, 1, 6),
        "33333": date(2026, 1, 7),
    }
    schedule = Schedule(period=_make_period(), assignments=assignments)
    assert len(schedule.assignments) == 3
    assert schedule.assignments["22222"] == date(2026, 1, 6)


def test_two_schedules_with_same_data_are_equal():
    period = _make_period()
    s1 = Schedule(period=period, assignments={"11111": date(2026, 1, 5)})
    s2 = Schedule(period=period, assignments={"11111": date(2026, 1, 5)})
    assert s1 == s2
