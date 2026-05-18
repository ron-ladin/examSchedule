"""
Unit Tests: ExamPeriod
-----------------------
Tests for ExamPeriod.get_valid_dates() logic.

Test cases to implement:
    1. Dates within range and not excluded → included in result.
    2. Dates in excluded_dates set         → NOT included in result.
    3. Weekend dates (Friday/Saturday)     → NOT included in result.
    4. Dates outside date_ranges           → NOT included in result.
    5. Excluded date ranges (start, end)   → all dates in range excluded.
    6. Empty date_ranges                   → returns empty list.

Notes:
    - Build ExamPeriod objects directly — no file parsing.
    - Use datetime.date objects for all date comparisons.
    - Import ExamPeriod from src.domain.exam_period.
"""

from datetime import date
# We import the ExamPeriod class from the domain folder
from src.domain.exam_period import ExamPeriod

#  This tests a normal date range (like January 5th to January 7th).
    # It checks that the system builds a full list containing all 3 days: the 5th, 6th, and 7th.
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

#  This tests blocked dates. If we add a specific date to 'excluded_dates' (the 6th),
    # the function must skip it and only return the safe, allowed dates (the 5th and 7th).
def test_get_valid_dates_excludes_specific_dates():
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 7))],
        excluded_dates={date(2026, 1, 6)},
    )

    assert exam_period.get_valid_dates() == [
        date(2026, 1, 5),
        date(2026, 1, 7),
    ]

# This checks the automatic weekend filter. 
    # January 10th, 2026 is a Saturday, so we make sure ('not in') it is automatically deleted from the final list.
def test_get_valid_dates_excludes_saturdays():
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 9), date(2026, 1, 11))],
    )

    assert date(2026, 1, 10) not in exam_period.get_valid_dates()

#  This is an Edge Case test. It checks what happens if we give the system zero dates ([]).
    # We want to make sure the code does not crash, but safely returns an empty list instead.
def test_get_valid_dates_returns_empty_for_empty_ranges():
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[],
    )

    assert exam_period.get_valid_dates() == []

#  This tests the tracking key generator.
    # It checks that when we pass "SPRING" and "Bet", it formats them into the clean string: "SPRI - Bet".
def test_get_key_displays_normalized_semester():
    exam_period = ExamPeriod(
        semester="SPRING",
        moed="Bet",
        date_ranges=[(date(2026, 3, 1), date(2026, 3, 2))],
    )

    assert exam_period.get_key() == "SPRI - Bet"


# Excluding an entire range of dates: 10 days minus a 3-day excluded range = 7 days
# (minus any Saturdays in the range)
def test_get_valid_dates_excludes_range_of_dates():
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 12), date(2026, 1, 16))],  # Mon-Fri, no Sat
        excluded_dates={date(2026, 1, 13), date(2026, 1, 14), date(2026, 1, 15)},
    )

    assert exam_period.get_valid_dates() == [
        date(2026, 1, 12),
        date(2026, 1, 16),
    ]


# All dates in the range are excluded → list should come back empty
def test_get_valid_dates_returns_empty_when_all_excluded():
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 12), date(2026, 1, 14))],  # Mon, Tue, Wed
        excluded_dates={date(2026, 1, 12), date(2026, 1, 13), date(2026, 1, 14)},
    )

    assert exam_period.get_valid_dates() == []


# When the whole period falls on a Saturday → all auto-excluded
def test_get_valid_dates_returns_empty_when_only_saturdays():
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 10), date(2026, 1, 10))],  # 10-Jan-2026 is Saturday
    )

    assert exam_period.get_valid_dates() == []


# Two distinct date ranges → both should contribute valid dates
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


# get_key for FALL should display FALL (not transformed)
def test_get_key_for_fall_semester():
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 6))],
    )

    assert exam_period.get_key() == "FALL - Aleph"


# get_key for SUMMER should normalize to "SUMM"
def test_get_key_for_summer_semester():
    exam_period = ExamPeriod(
        semester="SUMMER",
        moed="Gimel",
        date_ranges=[(date(2026, 7, 1), date(2026, 7, 2))],
    )

    assert exam_period.get_key() == "SUMM - Gimel"