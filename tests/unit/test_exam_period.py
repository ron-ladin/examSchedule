"""
Unit Tests: ExamPeriod
-----------------------
Tests for ExamPeriod.get_valid_dates() and get_key() logic.
"""

from datetime import date

from src.domain.exam_period import ExamPeriod


def test_get_valid_dates_includes_dates_in_range():
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 7))],
    )
    assert exam_period.get_valid_dates() == [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
    ]


def test_get_valid_dates_excludes_specific_dates():
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 7))],
        excluded_dates={date(2026, 1, 6)},
    )
    assert exam_period.get_valid_dates() == [date(2026, 1, 5), date(2026, 1, 7)]


def test_get_valid_dates_excludes_saturdays():
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 9), date(2026, 1, 11))],
    )
    assert date(2026, 1, 10) not in exam_period.get_valid_dates()


def test_get_valid_dates_returns_empty_for_empty_ranges():
    exam_period = ExamPeriod(semester="FALL", moed="Aleph", date_ranges=[])
    assert exam_period.get_valid_dates() == []


def test_get_valid_dates_returns_empty_when_all_excluded():
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 12), date(2026, 1, 14))],  # Mon, Tue, Wed
        excluded_dates={date(2026, 1, 12), date(2026, 1, 13), date(2026, 1, 14)},
    )
    assert exam_period.get_valid_dates() == []


def test_get_valid_dates_handles_multiple_ranges():
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[
            (date(2026, 1, 5), date(2026, 1, 6)),
            (date(2026, 1, 12), date(2026, 1, 13)),
        ],
    )
    assert exam_period.get_valid_dates() == [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 12),
        date(2026, 1, 13),
    ]


# Boundary: excluded date is exactly the first day in the range
def test_excluded_date_equals_first_day_of_range():
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 7))],
        excluded_dates={date(2026, 1, 5)},
    )
    assert exam_period.get_valid_dates() == [date(2026, 1, 6), date(2026, 1, 7)]


def test_get_key_for_fall_semester():
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 6))],
    )
    assert exam_period.get_key() == "FALL - Aleph"


def test_get_key_displays_normalized_semester():
    exam_period = ExamPeriod(
        semester="SPRING",
        moed="Bet",
        date_ranges=[(date(2026, 3, 1), date(2026, 3, 2))],
    )
    assert exam_period.get_key() == "SPRI - Bet"
