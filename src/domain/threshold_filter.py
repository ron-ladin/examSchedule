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
from typing import Dict, List, Tuple

from src.domain.course import Course
from src.domain.interfaces import IThresholdFilter
from src.domain.schedule import Schedule
from src.domain.semester import normalize_semester
from src.domain.threshold import Criterion, ThresholdSettings


class ThresholdFilter(IThresholdFilter):

    @staticmethod
    def is_valid(
        schedule: Schedule,
        courses: List[Course],
        settings: ThresholdSettings,
        selected_programs: List[str] | None = None,
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

def _relevant_offerings(course: Course, prog_set: set, semester: str) -> list:
    """Return offerings relevant to selected programs and the schedule semester.

    Empty prog_set keeps the previous direct-unit-test behavior of accepting
    all programs, but offerings from other semesters are still ignored because
    Feature 3 metrics are period-specific.
    """
    target_semester = normalize_semester(semester)
    return [
        offering
        for offering in course.offerings
        if (not prog_set or offering.program_id in prog_set)
        and normalize_semester(offering.semester) == target_semester
    ]


def _mandatory_dates_by_group(
    schedule: Schedule, courses: List[Course], prog_set: set
) -> Dict[Tuple[str, int], List[date]]:
    """Map (program_id, year) → list of mandatory exam dates."""
    groups: Dict[Tuple[str, int], List[date]] = {}
    for course in courses:
        if course.id not in schedule.assignments:
            continue
        exam_date = schedule.assignments[course.id]
        for offering in _relevant_offerings(course, prog_set, schedule.period.semester):
            if offering.requirement.strip().lower() != "obligatory":
                continue
            key = (offering.program_id, offering.year)
            groups.setdefault(key, []).append(exam_date)
    return groups


def _all_dates_by_group(
    schedule: Schedule, courses: List[Course], prog_set: set
) -> Dict[Tuple[str, int], List[date]]:
    """Map (program_id, year) → list of ALL exam dates."""
    groups: Dict[Tuple[str, int], List[date]] = {}
    for course in courses:
        if course.id not in schedule.assignments:
            continue
        exam_date = schedule.assignments[course.id]
        for offering in _relevant_offerings(course, prog_set, schedule.period.semester):
            key = (offering.program_id, offering.year)
            groups.setdefault(key, []).append(exam_date)
    return groups


def _elective_dates_by_program(
    schedule: Schedule, courses: List[Course], prog_set: set
) -> Dict[str, List[date]]:
    """Map program_id → list of elective exam dates."""
    groups: Dict[str, List[date]] = {}
    for course in courses:
        if course.id not in schedule.assignments:
            continue
        exam_date = schedule.assignments[course.id]
        for offering in _relevant_offerings(course, prog_set, schedule.period.semester):
            if offering.requirement.strip().lower() != "elective":
                continue
            groups.setdefault(offering.program_id, []).append(exam_date)
    return groups


def _min_gap(dates: List[date]) -> int:
    if len(dates) < 2:
        return 0
    return min(abs((b - a).days) for a, b in combinations(dates, 2))


def _count_same_day_pairs(dates: List[date]) -> int:
    return sum(1 for a, b in combinations(dates, 2) if a == b)


# ---------------------------------------------------------------------------
# Criterion checkers — (schedule, courses, k, prog_set) -> bool
# ---------------------------------------------------------------------------

def _check_2_1(schedule: Schedule, courses: List[Course], k: int, prog_set: set) -> bool:
    """Min days between mandatory exams (same program, same year) >= k."""
    for dates in _mandatory_dates_by_group(schedule, courses, prog_set).values():
        if len(dates) >= 2 and _min_gap(dates) < k:
            return False
    return True


def _check_2_2(schedule: Schedule, courses: List[Course], k: int, prog_set: set) -> bool:
    """Min days between ANY two exams (same program, same year) >= k."""
    for dates in _all_dates_by_group(schedule, courses, prog_set).values():
        if len(dates) >= 2 and _min_gap(dates) < k:
            return False
    return True


def _check_2_3(schedule: Schedule, courses: List[Course], k: int, prog_set: set) -> bool:
    """Elective-elective same-day collisions (same program) <= k."""
    for dates in _elective_dates_by_program(schedule, courses, prog_set).values():
        if _count_same_day_pairs(dates) > k:
            return False
    return True


def _check_2_4(schedule: Schedule, courses: List[Course], k: int, prog_set: set) -> bool:
    """Spread (last - first mandatory, same program/year) >= k."""
    for dates in _mandatory_dates_by_group(schedule, courses, prog_set).values():
        spread = (max(dates) - min(dates)).days
        if spread < k:
            return False
    return True


def _check_2_5(schedule: Schedule, courses: List[Course], k: int, prog_set: set) -> bool:
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
