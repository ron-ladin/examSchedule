from datetime import date

from src.domain.exam_period import ExamPeriod


def test_get_valid_dates_includes_dates_inside_range():
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 29), date(2026, 1, 31))],
    )

    assert period.get_valid_dates() == [
        date(2026, 1, 29),
        date(2026, 1, 30),
        date(2026, 1, 31),
    ]


def test_get_valid_dates_excludes_dates_in_excluded_dates():
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 29), date(2026, 2, 2))],
        excluded_dates={date(2026, 1, 31), date(2026, 2, 1)},
    )

    assert period.get_valid_dates() == [
        date(2026, 1, 29),
        date(2026, 1, 30),
        date(2026, 2, 2),
    ]


def test_dates_outside_date_ranges_are_not_included():
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 29), date(2026, 1, 31))],
    )

    valid_dates = period.get_valid_dates()

    assert date(2026, 1, 28) not in valid_dates
    assert date(2026, 2, 1) not in valid_dates


def test_multiple_date_ranges_are_combined():
    period = ExamPeriod(
        semester="FALL",
        moed="Bet",
        date_ranges=[
            (date(2026, 1, 29), date(2026, 1, 30)),
            (date(2026, 2, 3), date(2026, 2, 4)),
        ],
    )

    assert period.get_valid_dates() == [
        date(2026, 1, 29),
        date(2026, 1, 30),
        date(2026, 2, 3),
        date(2026, 2, 4),
    ]


def test_empty_date_ranges_returns_empty_list():
    period = ExamPeriod(semester="SPRI", moed="Aleph", date_ranges=[])

    assert period.get_valid_dates() == []


def test_get_key_normalizes_semester():
    period = ExamPeriod(semester="SPRING", moed="Bet", date_ranges=[])

    assert period.get_key() == "SPRI - Bet"


