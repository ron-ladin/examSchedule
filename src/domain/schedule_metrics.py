"""
Domain Helpers: schedule_metrics
----------------------------------
Shared computation helpers used by both ThresholdFilter and SortingEngine.
Extracted from the duplicate implementations in those modules to satisfy DRY.

All functions are module-level (stateless) and operate on domain objects only.
"""

from datetime import date

from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.semester import normalize_semester


def relevant_offerings(course: Course, prog_set: set, semester: str) -> list:
    """Return offerings relevant to selected programs and the schedule semester.

    Empty prog_set accepts all programs, but offerings from other semesters
    are still filtered because Feature 3 metrics are period-specific.
    """
    target_semester = normalize_semester(semester)
    return [
        offering
        for offering in course.offerings
        if (not prog_set or offering.program_id in prog_set)
        and normalize_semester(offering.semester) == target_semester
    ]


def mandatory_dates_by_group(
    schedule: Schedule, courses: list[Course], prog_set: set
) -> dict[tuple[str, int], list[date]]:
    """Map (program_id, year) → list of mandatory exam dates."""
    groups: dict[tuple[str, int], list[date]] = {}
    for course in courses:
        if course.id not in schedule.assignments:
            continue
        exam_date = schedule.assignments[course.id]
        for offering in relevant_offerings(course, prog_set, schedule.period.semester):
            if offering.requirement.strip().lower() != "obligatory":
                continue
            key = (offering.program_id, offering.year)
            groups.setdefault(key, []).append(exam_date)
    return groups


def all_dates_by_group(
    schedule: Schedule, courses: list[Course], prog_set: set
) -> dict[tuple[str, int], list[date]]:
    """Map (program_id, year) → list of ALL exam dates."""
    groups: dict[tuple[str, int], list[date]] = {}
    for course in courses:
        if course.id not in schedule.assignments:
            continue
        exam_date = schedule.assignments[course.id]
        for offering in relevant_offerings(course, prog_set, schedule.period.semester):
            key = (offering.program_id, offering.year)
            groups.setdefault(key, []).append(exam_date)
    return groups


def elective_dates_by_program(
    schedule: Schedule, courses: list[Course], prog_set: set
) -> dict[str, list[date]]:
    """Map program_id → list of elective exam dates."""
    groups: dict[str, list[date]] = {}
    for course in courses:
        if course.id not in schedule.assignments:
            continue
        exam_date = schedule.assignments[course.id]
        for offering in relevant_offerings(course, prog_set, schedule.period.semester):
            if offering.requirement.strip().lower() != "elective":
                continue
            groups.setdefault(offering.program_id, []).append(exam_date)
    return groups
