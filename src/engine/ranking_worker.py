"""Background worker for Result Ranking.

The UI uses this module to keep expensive re-ranking work out of the PyQt main
thread. SQLite-backed result sets send only store paths and period keys; plain
in-memory result sets send their small schedule lists and receive sorted lists
back.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field

from src.adapters.sqlite_schedule_store import SQLiteScheduleStore
from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.sorting import SortingConfig
from src.domain.sorting_engine import SortingEngine


@dataclass(frozen=True)
class RankingJob:
    """Picklable payload for one ranking request."""

    sorting: SortingConfig
    courses: list[Course]
    selected_programs: list[str] | None = None
    schedules_by_period: dict[str, list[Schedule]] = field(default_factory=dict)
    sqlite_store_specs: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class RankingWorkerResult:
    """Small result returned by the ranking worker."""

    success: bool
    schedules_by_period: dict[str, list[Schedule]] = field(default_factory=dict)
    error: str | None = None

    @classmethod
    def ok(
        cls,
        schedules_by_period: dict[str, list[Schedule]] | None = None,
    ) -> "RankingWorkerResult":
        return cls(success=True, schedules_by_period=dict(schedules_by_period or {}))

    @classmethod
    def failure(cls, error: str) -> "RankingWorkerResult":
        return cls(success=False, error=error)


def _put_ranking_result(result_queue, message: RankingWorkerResult) -> None:
    """Serialize before queueing so pickle errors happen inside the worker."""
    pickle.dumps(message)
    result_queue.put(message)


def run_ranking_worker(result_queue, job: RankingJob) -> None:
    """Sort cached schedules or warm SQLite ordering, then return a small result."""
    try:
        ranked = {
            period_key: SortingEngine.sort(
                schedules,
                job.courses,
                job.sorting,
                job.selected_programs,
            )
            for period_key, schedules in job.schedules_by_period.items()
        }

        for store_path, period_keys in job.sqlite_store_specs:
            store = SQLiteScheduleStore(store_path, delete_on_close=False)
            try:
                for period_key in period_keys:
                    store.warm_order(period_key, job.sorting)
            finally:
                store.close(delete=False)

        _put_ranking_result(result_queue, RankingWorkerResult.ok(ranked))
    except Exception as exc:
        _put_ranking_result(result_queue, RankingWorkerResult.failure(str(exc)))
