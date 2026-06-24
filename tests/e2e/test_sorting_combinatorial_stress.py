"""
E2E Stress Test: SortingEngine combinatorial load  (Phase 2)
-------------------------------------------------------------
Reproduces the "UI freeze with all 5 criteria enabled" scenario and proves the
aggressive memoization layer in ``src.domain.sorting_engine`` keeps it fast.

Setup mimics an expanded Feature 4 in-memory cache: a large pool of candidate
schedules (10,000) over a shared course set, with exam dates drawn from a
bounded pool so that date patterns recur across schedules — exactly the
redundancy the lru_cache layer is designed to collapse.

For EACH of the 120 priority permutations of the 5 sort criteria we assert that
``SortingEngine.sort()`` ranks all 10,000 schedules in under 1.0 second.
"""

import random
import time
from datetime import date, timedelta
from itertools import permutations

import pytest

from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.sorting import SortCriterion, SortingConfig
from src.domain.sorting_engine import SortingEngine

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

SCHEDULE_COUNT = 10_000
TIME_BUDGET_SECONDS = 1.0
SEMESTER = "FALL"
PROGRAM_A = "83101"
PROGRAM_B = "83102"
SEED = 1234

BASE_PERIOD = ExamPeriod(
    semester=SEMESTER,
    moed="Aleph",
    date_ranges=[(date(2026, 1, 4), date(2026, 2, 28))],
)

# A bounded pool of valid (non-Saturday) candidate exam dates. Drawing from a
# small pool guarantees date patterns repeat across the 10k schedules and across
# the 120 permutations — the core assumption that makes memoization pay off.
_DATE_POOL = [
    d
    for d in (date(2026, 1, 4) + timedelta(days=i) for i in range(50))
    if d.weekday() != 5  # exclude Saturdays, matching ExamPeriod rules
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _offering(program: str, year: int, requirement: str) -> CourseOffering:
    return CourseOffering(
        program_id=program,
        year=year,
        semester=SEMESTER,
        requirement=requirement,
        student_count=120,
    )


def _course(course_id: str, program: str, year: int, requirement: str) -> Course:
    course = Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Prof. X",
        evaluation_type="Exam",
    )
    course.add_offering(_offering(program, year, requirement))
    return course


def _build_courses() -> list[Course]:
    """A realistic spread: two programs, two years, mandatory + elective mix."""
    courses: list[Course] = []
    spec = [
        (PROGRAM_A, 1, "Obligatory"),
        (PROGRAM_A, 1, "Obligatory"),
        (PROGRAM_A, 1, "Elective"),
        (PROGRAM_A, 2, "Obligatory"),
        (PROGRAM_A, 2, "Elective"),
        (PROGRAM_B, 1, "Obligatory"),
        (PROGRAM_B, 1, "Obligatory"),
        (PROGRAM_B, 1, "Elective"),
        (PROGRAM_B, 2, "Obligatory"),
        (PROGRAM_B, 2, "Elective"),
    ]
    for index, (program, year, requirement) in enumerate(spec):
        courses.append(_course(f"100{index:02d}", program, year, requirement))
    return courses


def _build_schedules(courses: list[Course]) -> list[Schedule]:
    rng = random.Random(SEED)
    course_ids = [c.id for c in courses]
    schedules: list[Schedule] = []
    for _ in range(SCHEDULE_COUNT):
        assignments = {
            course_id: rng.choice(_DATE_POOL) for course_id in course_ids
        }
        schedules.append(Schedule(period=BASE_PERIOD, assignments=assignments))
    return schedules


@pytest.fixture(scope="module")
def courses() -> list[Course]:
    return _build_courses()


@pytest.fixture(scope="module")
def schedules(courses: list[Course]) -> list[Schedule]:
    return _build_schedules(courses)


# ---------------------------------------------------------------------------
# The combinatorial stress test
# ---------------------------------------------------------------------------

ALL_CRITERIA = list(SortCriterion)
ALL_PERMUTATIONS = list(permutations(ALL_CRITERIA))


def test_there_are_exactly_120_permutations() -> None:
    assert len(ALL_PERMUTATIONS) == 120  # 5! over the five sort criteria


@pytest.mark.parametrize("ordering", ALL_PERMUTATIONS)
def test_sort_under_budget_for_every_permutation(
    schedules: list[Schedule],
    courses: list[Course],
    ordering: tuple[SortCriterion, ...],
) -> None:
    config = SortingConfig.from_ordered_criteria(ordering)
    selected_programs = [PROGRAM_A, PROGRAM_B]

    start = time.perf_counter()
    ranked = SortingEngine.sort(schedules, courses, config, selected_programs)
    elapsed = time.perf_counter() - start

    # Correctness guards so we cannot "pass" by silently no-op'ing.
    assert len(ranked) == SCHEDULE_COUNT
    assert ranked is not schedules  # sort() must return a new list

    assert elapsed < TIME_BUDGET_SECONDS, (
        f"Sorting {SCHEDULE_COUNT} schedules took {elapsed:.3f}s "
        f"(budget {TIME_BUDGET_SECONDS}s) for ordering "
        f"{[c.name for c in ordering]}"
    )
