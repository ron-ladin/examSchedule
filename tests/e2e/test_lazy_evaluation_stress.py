"""Strict lazy-evaluation stress test for the Load More / Auto Variants path.

The desktop "Load More" button asks a persistent background worker for the next
page of classroom/time-slot variants. A *truly* lazy implementation must:

  1. Return the FIRST page after computing only what that page needs, even when
     the underlying combination space is astronomically large (30 rooms).
  2. RESUME from where it left off on the next "Load More", instead of
     re-running generation from scratch and islice()-ing past every item it
     already produced (the O(N^2) recompute trap).
  3. Hand back NEW, non-duplicate combinations on every page.

Each page is given a hard wall-clock budget. If the worker is doing eager work
(materialising a huge list up front, or recomputing earlier pages), the budget
is blown and the test fails loudly instead of freezing CI.
"""

import time
from datetime import date, time as dtime
from itertools import count
from multiprocessing import Process, Queue
from queue import Empty

from src.domain.classroom import Classroom
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.time_slot import TimeSlot
from src.engine.generation_workers import _run_load_more_worker

# A combination space large enough that any eager pass would hang.
N_ROOMS = 30
ROOM_CAPACITY = 40
STUDENT_COUNT = 120          # needs several rooms -> many feasible splits
PAGE_SIZE = 5
PER_PAGE_BUDGET_SECONDS = 2.0


def _build_scenario():
    period = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 5))])
    offering = CourseOffering("83101", 1, "FALL", "Obligatory", STUDENT_COUNT)
    course = Course("11111", "Stress", "Dr. Test", "Exam", [offering])
    schedule = Schedule(period, {"11111": date(2026, 1, 5)})
    rooms = [Classroom(f"Room {i}", ROOM_CAPACITY) for i in range(N_ROOMS)]
    slots = [TimeSlot(dtime(9, 0)), TimeSlot(dtime(13, 0)), TimeSlot(dtime(16, 0))]
    return schedule, course, rooms, slots


def _variant_signature(schedule: Schedule) -> tuple:
    """Identify a variant by its room/slot allocation, ignoring object identity."""
    items = []
    for course_id, assignments in sorted(schedule.classroom_assignments.items()):
        for a in assignments:
            items.append(
                (course_id, a.room.room_id, a.slot.time, a.students_assigned)
            )
    return tuple(items)


def _request_page(task_queue, result_queue, schedule, course, rooms, slots, offset):
    """Drive one Load More page through the persistent worker and time it."""
    task_queue.put(
        (
            "variants",
            (
                "FALL|Aleph",
                schedule,
                [course],
                ["83101"],
            ),
            {
                "cap": PAGE_SIZE,
                "offset": offset,
                "classrooms": rooms,
                "time_slots": slots,
                "proctor_config": ProctorConfig(20),
            },
        )
    )

    start = time.perf_counter()
    try:
        kind, result = result_queue.get(timeout=PER_PAGE_BUDGET_SECONDS + 8)
    except Empty:
        raise AssertionError(
            f"Worker produced no result for page at offset {offset} — "
            "eager evaluation hung the lazy generator."
        )
    elapsed = time.perf_counter() - start

    assert kind == "variants"
    assert result.success, f"Worker failed: {result.error}"
    schedules = result.schedules_by_period["FALL|Aleph"]
    return schedules, elapsed


def test_load_more_is_truly_lazy_and_resumable():
    schedule, course, rooms, slots = _build_scenario()

    task_queue: Queue = Queue()
    result_queue: Queue = Queue()

    worker = Process(target=_run_load_more_worker, args=(task_queue, result_queue))
    worker.start()
    try:
        seen: set[tuple] = set()
        offsets = count(0, PAGE_SIZE)

        # Page 1 — first page must come back fast despite the huge room space.
        page1, t1 = _request_page(
            task_queue, result_queue, schedule, course, rooms, slots, next(offsets)
        )
        assert page1, "First page returned no variants"
        assert t1 < PER_PAGE_BUDGET_SECONDS, (
            f"First page took {t1:.2f}s (> {PER_PAGE_BUDGET_SECONDS}s): "
            "generation is not lazy."
        )
        for s in page1:
            seen.add(_variant_signature(s))

        # Pages 2..N — each "Load More" must resume, stay under budget, and yield
        # only NEW combinations. Walking several contiguous pages is what exposes
        # the O(N^2) recompute trap: a non-resuming worker re-runs generation and
        # discards `offset` items on every page, so later pages slow down and/or
        # re-emit already-seen variants.
        for page_no in range(2, 6):
            page, elapsed = _request_page(
                task_queue, result_queue, schedule, course, rooms, slots, next(offsets)
            )
            assert page, f"Page {page_no} returned no variants"
            assert elapsed < PER_PAGE_BUDGET_SECONDS, (
                f"Load More page {page_no} took {elapsed:.2f}s "
                f"(> {PER_PAGE_BUDGET_SECONDS}s): the generator restarted "
                "instead of resuming."
            )

            new_sigs = {_variant_signature(s) for s in page}
            assert new_sigs.isdisjoint(seen), (
                f"Load More page {page_no} returned duplicate combinations "
                "already shown on an earlier page."
            )
            seen.update(new_sigs)
    finally:
        task_queue.put(None)
        worker.join(timeout=10)
        if worker.is_alive():
            worker.terminate()
