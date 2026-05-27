from __future__ import annotations

import threading
from collections.abc import Iterator
from itertools import product as cartesian_product
from typing import Any

from src.api.adapters.interfaces import IOutputExporter
from src.domain.course import Course
from src.domain.schedule import Schedule

# How many items fit on one page by default
PAGE_SIZE: int = 50

# Maximum schedules we keep in memory — stops the list from growing forever
MAX_SCHEDULES: int = 10_000


class PaginatedExporter(IOutputExporter):
    """Thread-safe in-memory store for generated schedules with pagination support.

    How it connects to AppController:
    AppController calls export_schedules() → we consume the cross-product of all
    period iterators and call add() for each combined schedule.
    The API then reads results via get_page() and total().

    Thread safety:
    add() is called from asyncio.to_thread (generator thread).
    get_page() and total() are called from the async event loop.
    Both sides must hold self._lock.
    """

    def __init__(self) -> None:
        # The list that holds all saved schedules
        self._items: list[Any] = []
        # Lock so only one thread can read or write at a time
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # v1.0 contract — required by AppController                           #
    # ------------------------------------------------------------------ #

    def export_schedules(
        self,
        schedules_by_period: dict[str, Iterator[Schedule]],
        courses_by_id: dict[str, Course],
    ) -> None:
        """Build the cross-product of all period schedules and store each combination.

        Why cross-product: each period (e.g. FALL-Aleph, FALL-Bet) produces its
        own set of valid schedules. A full exam timetable is one schedule per period
        combined — so we need every combination across periods.

        Note: each period iterator must be materialised into a list because
        cartesian_product needs to iterate inner lists multiple times.
        """
        if not schedules_by_period:
            return

        period_keys = list(schedules_by_period.keys())

        # Materialise each Iterator into a list — cartesian_product needs
        # to iterate each inner sequence multiple times, which lazy iterators don't support
        period_schedules: list[list[Schedule]] = [
            list(schedules_by_period[k]) for k in period_keys
        ]

        # Each combo is one complete timetable: one Schedule object per period
        for combo in cartesian_product(*period_schedules):
            combined: dict[str, Any] = {
                period_key: [
                    {
                        "course_id": course_id,
                        "date": exam_date.strftime("%d-%m-%Y"),
                        # Include name + instructor so the frontend doesn't need a separate lookup
                        "name": courses_by_id[course_id].name if course_id in courses_by_id else course_id,
                        "instructor": courses_by_id[course_id].instructor if course_id in courses_by_id else "",
                    }
                    for course_id, exam_date in sorted(
                        schedule.assignments.items(), key=lambda x: x[1]  # sort by date
                    )
                ]
                for period_key, schedule in zip(period_keys, combo)
            }
            self.add(combined)

    # ------------------------------------------------------------------ #
    # Pagination API — used by the REST endpoints                         #
    # ------------------------------------------------------------------ #

    def add(self, item: Any) -> None:
        """Save one schedule to the list. Called internally by export_schedules()."""
        with self._lock:
            # If we already hit the cap, stop adding (do not crash)
            if len(self._items) >= MAX_SCHEDULES:
                return
            self._items.append(item)

    def get_all(self) -> list[Any]:
        """Return a snapshot of every stored schedule (for IPC transfer in _sync_generate)."""
        with self._lock:
            return list(self._items)

    def get_page(self, page: int, size: int = PAGE_SIZE) -> list[Any]:
        """Return one page of schedules. page=0 is the first page, page=1 is the second, etc."""
        with self._lock:
            # Calculate where this page starts and return only that slice
            start = page * size
            return self._items[start : start + size]

    def total(self) -> int:
        """Return how many schedules are stored right now."""
        with self._lock:
            return len(self._items)

    def reset(self) -> None:
        """Delete all stored schedules. Called before starting a new generation run."""
        with self._lock:
            self._items = []
