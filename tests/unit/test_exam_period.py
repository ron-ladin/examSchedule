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

# Import date so we can create real date objects for the test.
from datetime import date

# Import the ExamPeriod domain entity that we want to test.
from src.domain.exam_period import ExamPeriod


def test_exam_period_can_be_created_with_excluded_dates():
    """
    Checks that an ExamPeriod object can be created with excluded_dates.

    This test is important because ExamPeriod contains mutable fields:
    - date_ranges is a list
    - excluded_dates is a set

    The purpose of this test is to make sure that creating an ExamPeriod
    with excluded dates works correctly and does not crash.
    """

    # Create an ExamPeriod for FALL semester, Moed Aleph.
    # The exam period has one valid date range:
    # from 29-01-2026 until 11-03-2026.
    # One date, 31-01-2026, is excluded and cannot be used for exams.
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 29), date(2026, 3, 11))],
        excluded_dates={date(2026, 1, 31)}
    )

    # Verify that the semester was saved correctly.
    assert period.semester == "FALL"

    # Verify that the moed was saved correctly.
    assert period.moed == "Aleph"

    # Verify that the date range was saved correctly.
    assert period.date_ranges == [(date(2026, 1, 29), date(2026, 3, 11))]

    # Verify that the excluded date was saved correctly.
    assert period.excluded_dates == {date(2026, 1, 31)}