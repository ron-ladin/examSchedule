"""
Domain Service: SortingEngine
-------------------------------
Sorts a list of valid Schedules by a SortingConfig (spec sections 3.1–3.5).
All criteria sort in DESCENDING order (higher score = ranked first).

Public API:
    SortingEngine.sort(schedules, courses, config, selected_programs=None) -> list[Schedule]

Returns a new list; the input is not mutated.
"""

from collections import Counter
from datetime import date
from itertools import combinations
from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.schedule_metrics import (
    all_dates_by_group,
    elective_dates_by_program,
    mandatory_dates_by_group,
)
from src.domain.sorting import SortCriterion, SortingConfig


class SortingEngine:

    @staticmethod
    def sort(
        schedules: list[Schedule],
        courses: list[Course],
        config: SortingConfig,
        selected_programs: list[str] | None = None,
    ) -> list[Schedule]:
        criteria = config.criteria_in_order()
        if not criteria:
            return list(schedules)

        prog_set: set = set(selected_programs) if selected_programs else set()

        def sort_key(schedule: Schedule) -> tuple:
            # Negate each score so sorted() produces descending order.
            return tuple(-_SCORERS[c](schedule, courses, prog_set) for c in criteria)

        return sorted(schedules, key=sort_key)


# ---------------------------------------------------------------------------
# Internal helpers (sorting-specific — not shared with ThresholdFilter)
# ---------------------------------------------------------------------------

def _min_gap(dates: list[date]) -> int:
    if len(dates) < 2:
        return 0
    return min(abs((b - a).days) for a, b in combinations(dates, 2))


def _avg_gap(dates: list[date]) -> float:
    if len(dates) < 2:
        return 0.0
    pairs = list(combinations(dates, 2))
    return sum(abs((b - a).days) for a, b in pairs) / len(pairs)


def _count_same_day_pairs(dates: list[date]) -> int:
    return sum(1 for a, b in combinations(dates, 2) if a == b)


# ---------------------------------------------------------------------------
# Criterion scorers — (schedule, courses, prog_set) -> float (higher = ranked first)
# ---------------------------------------------------------------------------

def _score_3_1(schedule: Schedule, courses: list[Course], prog_set: set) -> float:
    """3.1 — min days between mandatory exams (same program, year)."""
    groups = mandatory_dates_by_group(schedule, courses, prog_set)
    if not groups:
        return 0.0
    return float(min(_min_gap(dates) for dates in groups.values()))


def _score_3_2(schedule: Schedule, courses: list[Course], prog_set: set) -> float:
    """3.2 — average days between any two exams (same program, year)."""
    groups = all_dates_by_group(schedule, courses, prog_set)
    avgs = [_avg_gap(dates) for dates in groups.values() if len(dates) >= 2]
    return sum(avgs) / len(avgs) if avgs else 0.0


def _score_3_3(schedule: Schedule, courses: list[Course], prog_set: set) -> float:
    """3.3 — total elective-elective same-day collision pairs (same program)."""
    groups = elective_dates_by_program(schedule, courses, prog_set)
    return float(sum(_count_same_day_pairs(dates) for dates in groups.values()))


def _score_3_4(schedule: Schedule, courses: list[Course], prog_set: set) -> float:
    """3.4 — spread (last - first mandatory date, same program/year)."""
    groups = mandatory_dates_by_group(schedule, courses, prog_set)
    if not groups:
        return 0.0
    return float(min((max(d) - min(d)).days for d in groups.values()))


def _score_3_5(schedule: Schedule, courses: list[Course], prog_set: set) -> float:
    """3.5 — max exams on the same day (global)."""
    if not schedule.assignments:
        return 0.0
    return float(max(Counter(schedule.assignments.values()).values()))


_SCORERS = {
    SortCriterion.SORT_MIN_DAYS_MANDATORY: _score_3_1,
    SortCriterion.SORT_AVG_DAYS_ANY: _score_3_2,
    SortCriterion.SORT_ELECTIVE_COLLISIONS: _score_3_3,
    SortCriterion.SORT_EXAM_PERIOD_SPREAD: _score_3_4,
    SortCriterion.SORT_MAX_EXAMS_PER_DAY: _score_3_5,
}
