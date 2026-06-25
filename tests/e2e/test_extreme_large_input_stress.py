"""
E2E Stress Test: Extreme large-input generation + sorting  (SCRUM-433/434/435)
------------------------------------------------------------------------------
Pushes the engine to its algorithmic limits and enforces *hard* upper bounds on
both wall-clock time and heap memory so a regression cannot silently hang CI or
OOM a standard runner.

Scope of the load (SCRUM-433 — extreme scale):
  * 220 courses (a mix of Obligatory and Elective) spread across 10 programs and
    multiple study years, so the conflict graph has realistic, overlapping
    clusters rather than one trivial chain.
  * 12 exam periods (date ranges) — well past the "10+" target.
  * Full Feature 3 + Feature 4 configuration in memory: classrooms, a proctor
    ratio, and time slots, mirroring a real heavy generation run.

The ``ScheduleGenerator`` yields lazily, so a 220-course Cartesian space is
effectively unbounded. To keep the run deterministic and tractable we drain a
*bounded first batch* of schedules per period (``BATCH_PER_PERIOD``) — exactly
the "first batch" the product surfaces to the user — and feed that batch through
the real ``SortingEngine`` with all five criteria enabled.

Memory (SCRUM-434):
  ``tracemalloc`` brackets the heavy generate+sort pipeline only; the peak heap
  is reported in MB so it is visible in pytest output (run with ``-s``).

Hard thresholds (SCRUM-435):
  * Execution time MUST be < ``TIME_BUDGET_SECONDS``.
  * Peak traced heap MUST be < ``PEAK_MEMORY_BUDGET_BYTES``.
  Either breach fails the test loudly.
"""

import time
import tracemalloc
from datetime import date, time as dtime, timedelta
from itertools import islice

import pytest

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.domain.classroom import Classroom
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.proctor import ProctorConfig
from src.domain.sorting import SortCriterion, SortingConfig
from src.domain.sorting_engine import SortingEngine
from src.domain.time_slot import TimeSlot
from src.engine.schedule_generator import ScheduleGenerator

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

COURSE_COUNT = 220          # SCRUM-433: 200+ courses
PROGRAM_COUNT = 10
YEARS = (1, 2, 3)
PERIOD_COUNT = 12           # SCRUM-433: 10+ exam periods
BATCH_PER_PERIOD = 250      # bounded "first batch" drained from the lazy engine

# Hard ceilings (SCRUM-435). These are intentionally strict to guard against
# CI hangs / OOM. They were exercised locally well under budget; if a slower
# shared CI runner trips them, bump TIME_BUDGET_SECONDS toward 15.0 and
# PEAK_MEMORY_BUDGET_MB toward 350 — the values stay strict enough to catch a
# real algorithmic or allocation regression while tolerating weak hardware.
TIME_BUDGET_SECONDS = 10.0
PEAK_MEMORY_BUDGET_MB = 250
PEAK_MEMORY_BUDGET_BYTES = PEAK_MEMORY_BUDGET_MB * 1024 * 1024

SEMESTER = "FALL"


# ---------------------------------------------------------------------------
# Dataset builders
# ---------------------------------------------------------------------------

def _program_id(index: int) -> str:
    return f"831{index:02d}"


SELECTED_PROGRAMS = [_program_id(i) for i in range(PROGRAM_COUNT)]


def _build_courses() -> list[Course]:
    """220 courses across 10 programs × 3 years, alternating Obligatory/Elective.

    Spreading offerings across programs/years keeps conflict clusters bounded
    (courses only conflict within a shared program+year+semester), so the
    backtracker still yields schedules quickly while the overall input is huge.
    """
    courses: list[Course] = []
    for i in range(COURSE_COUNT):
        program = _program_id(i % PROGRAM_COUNT)
        year = YEARS[i % len(YEARS)]
        requirement = "Obligatory" if i % 2 == 0 else "Elective"
        course = Course(
            id=f"{10000 + i}",
            name=f"Course {i}",
            instructor=f"Dr. {i % 25}",
            evaluation_type="Exam",
            offerings=[CourseOffering(program, year, SEMESTER, requirement, 120)],
        )
        courses.append(course)
    return courses


def _build_exam_periods() -> list[ExamPeriod]:
    """12 distinct two-week FALL periods with generous weekday windows."""
    periods: list[ExamPeriod] = []
    moadim = ["Aleph", "Bet"]
    for i in range(PERIOD_COUNT):
        start = date(2026, 1, 4) + timedelta(days=i * 15)
        end = start + timedelta(days=13)
        moed = moadim[i % len(moadim)]
        # Vary the period label so get_key() stays unique across the 12 periods.
        periods.append(ExamPeriod(SEMESTER, f"{moed}-{i}", [(start, end)]))
    return periods


def _build_feature4_config() -> tuple[list[Classroom], ProctorConfig, list[TimeSlot]]:
    """In-memory Feature 3 + Feature 4 load: classrooms, proctor ratio, slots."""
    classrooms = [Classroom(f"Room {n}", 40 + (n % 5) * 20) for n in range(30)]
    proctor_config = ProctorConfig(20)
    time_slots = [TimeSlot(dtime(h, 0)) for h in (9, 13, 19)]
    return classrooms, proctor_config, time_slots


# ---------------------------------------------------------------------------
# The extreme-scale stress test
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_extreme_large_input_stress() -> None:
    # Arrange — build the massive dataset and full Feature 3 + 4 configuration.
    courses = _build_courses()
    exam_periods = _build_exam_periods()
    classrooms, proctor_config, time_slots = _build_feature4_config()

    # Sanity-guard the scale so the test cannot quietly shrink below spec.
    assert len(courses) >= 200
    assert len(exam_periods) >= 10
    assert classrooms and time_slots and proctor_config is not None

    generator = ScheduleGenerator(ExactConflictStrategy(SELECTED_PROGRAMS))
    sort_config = SortingConfig.from_ordered_criteria(list(SortCriterion))

    # Act — bracket ONLY the heavy generate + sort pipeline with tracemalloc.
    tracemalloc.start()
    start = time.perf_counter()

    total_ranked = 0
    for period in exam_periods:
        # Drain a bounded first batch from the lazy backtracking generator.
        batch = list(
            islice(generator.generate_schedules(courses, period), BATCH_PER_PERIOD)
        )
        ranked = SortingEngine.sort(batch, courses, sort_config, SELECTED_PROGRAMS)
        total_ranked += len(ranked)

    elapsed = time.perf_counter() - start
    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Report (visible with `pytest -s`) — SCRUM-434.
    current_mb = current_bytes / (1024 * 1024)
    peak_mb = peak_bytes / (1024 * 1024)
    print(
        f"\n[extreme-stress] courses={len(courses)} periods={len(exam_periods)} "
        f"ranked={total_ranked} | time={elapsed:.3f}s "
        f"current={current_mb:.2f}MB peak={peak_mb:.2f}MB"
    )

    # Assert — engine actually did work, then enforce the hard ceilings.
    assert total_ranked > 0, "Engine produced no schedules for the extreme input"

    assert elapsed < TIME_BUDGET_SECONDS, (
        f"Extreme generate+sort took {elapsed:.3f}s "
        f"(hard budget {TIME_BUDGET_SECONDS}s)"
    )
    assert peak_bytes < PEAK_MEMORY_BUDGET_BYTES, (
        f"Peak heap {peak_mb:.2f}MB exceeded hard budget "
        f"{PEAK_MEMORY_BUDGET_MB}MB"
    )
