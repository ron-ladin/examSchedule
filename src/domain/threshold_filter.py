"""
Domain Service: ThresholdFilter
---------------------------------
Validates a Schedule against a ThresholdSettings configuration.
Implements spec sections 2.1–2.5 (sprint3_source_of_truth.md).

Public API:
    ThresholdFilter.is_valid(schedule, courses, settings, selected_programs=None) -> bool

Returns True only if every *enabled* criterion is satisfied.
"""

from collections import Counter
from datetime import date
from itertools import combinations
from src.domain.course import Course
from src.domain.interfaces import IThresholdFilter
from src.domain.schedule import Schedule
from src.domain.schedule_metrics import (
    all_dates_by_group,
    elective_dates_by_program,
    mandatory_dates_by_group,
)
from src.domain.threshold import Criterion, ThresholdSettings


class ThresholdFilter(IThresholdFilter):

    @staticmethod
    def is_valid(
        schedule: Schedule,
        courses: list[Course],
        settings: ThresholdSettings,
        selected_programs: list[str] | None = None,
    ) -> bool:
        prog_set: set = set(selected_programs) if selected_programs else set()
        for entry in settings.entries:
            if not entry.enabled:
                continue
            if not _CHECKERS[entry.criterion](schedule, courses, entry.k, prog_set):
                return False
        return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _min_gap(dates: list[date]) -> int:
    if len(dates) < 2:
        return 0
    return min(abs((b - a).days) for a, b in combinations(dates, 2))


def _count_same_day_pairs(dates: list[date]) -> int:
    return sum(1 for a, b in combinations(dates, 2) if a == b)


# ---------------------------------------------------------------------------
# Criterion checkers — (schedule, courses, k, prog_set) -> bool
# ---------------------------------------------------------------------------

def _check_2_1(schedule: Schedule, courses: list[Course], k: int, prog_set: set) -> bool:
    """Min days between mandatory exams (same program, same year) >= k."""
    for dates in mandatory_dates_by_group(schedule, courses, prog_set).values():
        if len(dates) >= 2 and _min_gap(dates) < k:
            return False
    return True


def _check_2_2(schedule: Schedule, courses: list[Course], k: int, prog_set: set) -> bool:
    """Min days between ANY two exams (same program, same year) >= k."""
    for dates in all_dates_by_group(schedule, courses, prog_set).values():
        if len(dates) >= 2 and _min_gap(dates) < k:
            return False
    return True


def _check_2_3(schedule: Schedule, courses: list[Course], k: int, prog_set: set) -> bool:
    """Elective-elective same-day collisions (same program) <= k."""
    for dates in elective_dates_by_program(schedule, courses, prog_set).values():
        if _count_same_day_pairs(dates) > k:
            return False
    return True


def _check_2_4(schedule: Schedule, courses: list[Course], k: int, prog_set: set) -> bool:
    """Spread (last - first mandatory, same program/year) >= k."""
    for dates in mandatory_dates_by_group(schedule, courses, prog_set).values():
        spread = (max(dates) - min(dates)).days
        if spread < k:
            return False
    return True


def _check_2_5(schedule: Schedule, courses: list[Course], k: int, prog_set: set) -> bool:
    """Max exams on any single day (global) <= k."""
    if not schedule.assignments:
        return True
    day_counts = Counter(schedule.assignments.values())
    return max(day_counts.values()) <= k


_CHECKERS = {
    Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS: _check_2_1,
    Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS: _check_2_2,
    Criterion.MAX_ELECTIVE_COLLISIONS: _check_2_3,
    Criterion.MIN_DAYS_EXAM_PERIOD_SPREAD: _check_2_4,
    Criterion.MAX_EXAMS_PER_DAY: _check_2_5,
}
