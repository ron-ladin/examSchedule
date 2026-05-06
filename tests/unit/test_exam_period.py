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
