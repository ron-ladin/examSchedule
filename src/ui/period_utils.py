"""
Shared period-display utilities used by config_screen, input_screen, and results_panel.

Centralises the standard period ordering and the display-period-list builder so
the three screens share one implementation and cannot drift.
"""

from src.controller import DesktopController
from src.domain.exam_period import ExamPeriod

STANDARD_PERIOD_ORDER: tuple[tuple[str, str], ...] = (
    ("FALL", "Aleph"),
    ("FALL", "Bet"),
    ("SPRI", "Aleph"),
    ("SPRI", "Bet"),
    ("SUMM", "Aleph"),
    ("SUMM", "Bet"),
)


def build_display_periods(controller: DesktopController) -> list[ExamPeriod]:
    """
    Return the full ordered list of periods to display as tabs.

    Real loaded periods keep their dates. Missing standard periods are
    represented as empty ExamPeriod objects (date_ranges=[]) so the UI can
    show a placeholder tab. They are never written to the controller until
    the user explicitly defines dates.

    Non-standard periods that exist in the controller (i.e. periods whose key
    is not in STANDARD_PERIOD_ORDER) are appended at the end.
    """
    existing_periods = list(controller.get_exam_periods())
    existing_by_key = {period.get_key(): period for period in existing_periods}

    display_periods: list[ExamPeriod] = []

    for semester, moed in STANDARD_PERIOD_ORDER:
        key = f"{semester} - {moed}"

        if key in existing_by_key:
            display_periods.append(existing_by_key[key])
        else:
            display_periods.append(
                ExamPeriod(
                    semester=semester,
                    moed=moed,
                    date_ranges=[],
                    excluded_dates=set(),
                )
            )

    display_keys = {period.get_key() for period in display_periods}

    for period in existing_periods:
        if period.get_key() not in display_keys:
            display_periods.append(period)

    return display_periods
