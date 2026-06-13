"""
Domain Service: ThresholdFilter
---------------------------------
Validates a Schedule against a ThresholdSettings configuration.
Implements spec sections 2.1–2.5 (sprint3_source_of_truth.md).

Public API:
    ThresholdFilter.is_valid(schedule, courses, settings) -> bool

Returns True only if every *enabled* criterion is satisfied.
"""

from collections import Counter
from datetime import date
from itertools import combinations
from typing import Dict, List, Tuple

from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.threshold import Criterion, ThresholdSettings


class ThresholdFilter:

    @staticmethod
    def is_valid(
        schedule: Schedule,
        courses: List[Course],
        settings: ThresholdSettings,
    ) -> bool:
        for entry in settings.entries:
            if not entry.enabled:
                continue
            if not _CHECKERS[entry.criterion](schedule, courses, entry.k):
                return False
        return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _mandatory_dates_by_group(
    schedule: Schedule, courses: List[Course]
) -> Dict[Tuple[str, int], List[date]]:
    """Map (program_id, year) → list of mandatory exam dates."""
    groups: Dict[Tuple[str, int], List[date]] = {}
    for course in courses:
        if course.id not in schedule.assignments:
            continue
        exam_date = schedule.assignments[course.id]
        for offering in course.offerings:
            if offering.requirement.strip().lower() != "obligatory":
                continue
            key = (offering.program_id, offering.year)
            groups.setdefault(key, []).append(exam_date)
    return groups


def _all_dates_by_group(
    schedule: Schedule, courses: List[Course]
) -> Dict[Tuple[str, int], List[date]]:
    """Map (program_id, year) → list of ALL exam dates."""
    groups: Dict[Tuple[str, int], List[date]] = {}
    for course in courses:
        if course.id not in schedule.assignments:
            continue
        exam_date = schedule.assignments[course.id]
        for offering in course.offerings:
            key = (offering.program_id, offering.year)
            groups.setdefault(key, []).append(exam_date)
    return groups


def _elective_dates_by_program(
    schedule: Schedule, courses: List[Course]
) -> Dict[str, List[date]]:
    """Map program_id → list of elective exam dates."""
    groups: Dict[str, List[date]] = {}
    for course in courses:
        if course.id not in schedule.assignments:
            continue
        exam_date = schedule.assignments[course.id]
        for offering in course.offerings:
            if offering.requirement.strip().lower() != "elective":
                continue
            groups.setdefault(offering.program_id, []).append(exam_date)
    return groups


def _min_gap(dates: List[date]) -> int:
    return min(abs((b - a).days) for a, b in combinations(dates, 2))


def _count_same_day_pairs(dates: List[date]) -> int:
    count = 0
    for a, b in combinations(dates, 2):
        if a == b:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Criterion checkers — (schedule, courses, k) -> bool
# ---------------------------------------------------------------------------

def _check_2_1(schedule: Schedule, courses: List[Course], k: int) -> bool:
    """Min days between mandatory exams (same program, same year) >= k."""
    for dates in _mandatory_dates_by_group(schedule, courses).values():
        if len(dates) >= 2 and _min_gap(dates) < k:
            return False
    return True


def _check_2_2(schedule: Schedule, courses: List[Course], k: int) -> bool:
    """Min days between ANY two exams (same program, same year) >= k."""
    for dates in _all_dates_by_group(schedule, courses).values():
        if len(dates) >= 2 and _min_gap(dates) < k:
            return False
    return True


def _check_2_3(schedule: Schedule, courses: List[Course], k: int) -> bool:
    """Elective-elective same-day collisions (same program) <= k."""
    for dates in _elective_dates_by_program(schedule, courses).values():
        if _count_same_day_pairs(dates) > k:
            return False
    return True


def _check_2_4(schedule: Schedule, courses: List[Course], k: int) -> bool:
    """Spread (last - first mandatory, same program/year) >= k."""
    for dates in _mandatory_dates_by_group(schedule, courses).values():
        spread = (max(dates) - min(dates)).days
        if spread < k:
            return False
    return True


def _check_2_5(schedule: Schedule, courses: List[Course], k: int) -> bool:
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
