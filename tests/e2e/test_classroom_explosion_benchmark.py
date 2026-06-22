"""Strict performance stress test for the O(2^R) classroom explosion (Issue #1).

This test reproduces the exact "Load More" scenario the desktop worker drives:
a single date with a single exam spread over many small rooms, with
``max_options_per_day=None`` (precisely what the worker passes) and a small
per-schedule page limit. Only the FIRST PAGE is pulled via ``islice``.

The disputed claim is that per-schedule paging ("load more") protects against
the per-date room-combination blowup. It does NOT: each date's option list is
fully materialised *before* page 1 can be yielded. If the per-date search is
unbounded (O(2^R) in room count), pulling even the first page hangs.

A branch with per-day pruning/clamping returns the first page in well under a
second. A branch without it hangs. We enforce that distinction with a hard
thread timeout so the test fails loudly instead of freezing CI.
"""

import time
from datetime import date, time as dtime
from itertools import islice
from threading import Thread

from src.domain.classroom import Classroom
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.time_slot import TimeSlot
from src.engine.classroom_assigner import ClassroomAssigner

# Scenario knobs chosen to maximise the per-date combination search while
# staying faithful to the worker's real call.
N_ROOMS = 28           # 28 rooms => up to 2^28 room subsets if unpruned
ROOM_CAPACITY = 10     # small rooms force multi-room splits
STUDENT_COUNT = 100    # needs several rooms, so size-1..R combos are all live
PAGE_SIZE = 5          # caller wants only the first page (5 variants)
HANG_TIMEOUT_SECONDS = 20  # >20s to return page 1 == O(2^R) explosion


def _build_scenario():
    """Build the single-date / single-exam / many-room stress scenario."""
    period = ExamPeriod(
        "FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 5))]
    )
    offering = CourseOffering("83101", 1, "FALL", "Obligatory", STUDENT_COUNT)
    course = Course("11111", "Stress", "Dr. Test", "Exam", [offering])
    schedule = Schedule(period, {"11111": date(2026, 1, 5)})
    rooms = [Classroom(f"Room {i}", ROOM_CAPACITY) for i in range(N_ROOMS)]
    slots = [TimeSlot(dtime(9, 0))]
    return schedule, course, rooms, slots


def test_first_page_returns_without_explosion():
    """First page must return fast; a hang proves the O(2^R) explosion.

    Mirrors the worker call exactly: max_options_per_day=None (clamped by a
    correct branch, unbounded by a vulnerable one) and a small per-schedule
    page limit, pulling only the first page with islice.
    """
    schedule, course, rooms, slots = _build_scenario()

    result: dict[str, object] = {}

    def _pull_first_page() -> None:
        started = time.perf_counter()
        variant_iter = ClassroomAssigner.assign_variants(
            schedule,
            [course],
            ["83101"],
            rooms,
            slots,
            ProctorConfig(20),
            allow_unassigned=False,
            max_options_per_day=None,            # exactly what the worker passes
            max_options_per_schedule=PAGE_SIZE + 1,  # first-page request
        )
        first_page = list(islice(variant_iter, 0, PAGE_SIZE))
        result["elapsed"] = time.perf_counter() - started
        result["count"] = len(first_page)

    worker = Thread(target=_pull_first_page, daemon=True)
    worker.start()
    worker.join(timeout=HANG_TIMEOUT_SECONDS)

    if worker.is_alive():
        # The worker thread is a daemon, so it will not block process exit.
        assert False, (
            f"HANG DETECTED: First page took >{HANG_TIMEOUT_SECONDS}s to "
            f"return due to O(2^R) classroom combination explosion "
            f"({N_ROOMS} rooms, per-date search not pruned/clamped)."
        )

    elapsed = result["elapsed"]
    count = result["count"]
    assert count >= 1, "Expected at least one valid variant on the first page"
    # Sanity guard: a pruned branch returns in well under a second; allow slack.
    assert elapsed < HANG_TIMEOUT_SECONDS, (
        f"First page returned but took {elapsed:.2f}s "
        f"(threshold {HANG_TIMEOUT_SECONDS}s) — pruning is ineffective."
    )
    print(
        f"\n[benchmark] {N_ROOMS} rooms, first page of {count} variant(s) "
        f"returned in {elapsed:.3f}s"
    )
