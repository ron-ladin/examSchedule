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