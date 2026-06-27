"""Lightweight runtime metrics for generation, loading, and ranking."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PerformanceSnapshot:
    """Immutable view of the latest measured workload timings/counters."""

    generation_seconds: float = 0.0
    total_generated_schedules: int = 0
    schedules_stored_sqlite: int = 0
    domain_prunes: int = 0
    threshold_rejections: int = 0
    forward_checking_rejections: int = 0
    ranking_seconds: float = 0.0
    load_more_batch_seconds: float = 0.0
    auto_load_batch_seconds: float = 0.0
    sqlite_stored_row_count: int = 0
    active_batch_size: int = 0


class PerformanceMetrics:
    """Low-overhead mutable metrics collector.

    Metrics are diagnostic only. Scheduling correctness must never depend on
    these counters being present or exact.
    """

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._generation_started_at: float | None = None
        self._ranking_started_at: float | None = None
        self._load_batch_started_at: float | None = None
        self._load_batch_is_auto = False
        self._snapshot = PerformanceSnapshot()

    def snapshot(self) -> PerformanceSnapshot:
        """Return the latest completed metrics snapshot."""
        return self._snapshot

    def reset_generation(self) -> None:
        """Clear generation counters before a new run starts."""
        self._generation_started_at = None
        self._snapshot = PerformanceSnapshot(
            ranking_seconds=self._snapshot.ranking_seconds,
            load_more_batch_seconds=self._snapshot.load_more_batch_seconds,
            auto_load_batch_seconds=self._snapshot.auto_load_batch_seconds,
            active_batch_size=self._snapshot.active_batch_size,
        )

    def start_generation(self, batch_size: int = 0) -> None:
        """Record generation start time and active batch size."""
        self.reset_generation()
        self._generation_started_at = self._clock()
        self._snapshot = PerformanceSnapshot(active_batch_size=batch_size)

    def finish_generation(
        self,
        *,
        total_generated_schedules: int = 0,
        schedules_stored_sqlite: int = 0,
        domain_prunes: int = 0,
        threshold_rejections: int = 0,
        forward_checking_rejections: int = 0,
        sqlite_stored_row_count: int = 0,
    ) -> PerformanceSnapshot:
        """Record generation completion counters and duration."""
        elapsed = self._elapsed_since(self._generation_started_at)
        self._generation_started_at = None
        self._snapshot = PerformanceSnapshot(
            generation_seconds=elapsed,
            total_generated_schedules=total_generated_schedules,
            schedules_stored_sqlite=schedules_stored_sqlite,
            domain_prunes=domain_prunes,
            threshold_rejections=threshold_rejections,
            forward_checking_rejections=forward_checking_rejections,
            ranking_seconds=self._snapshot.ranking_seconds,
            load_more_batch_seconds=self._snapshot.load_more_batch_seconds,
            auto_load_batch_seconds=self._snapshot.auto_load_batch_seconds,
            sqlite_stored_row_count=sqlite_stored_row_count,
            active_batch_size=self._snapshot.active_batch_size,
        )
        return self._snapshot

    def start_ranking(self) -> None:
        """Record ranking start time."""
        self._ranking_started_at = self._clock()

    def finish_ranking(self) -> PerformanceSnapshot:
        """Record ranking completion duration."""
        elapsed = self._elapsed_since(self._ranking_started_at)
        self._ranking_started_at = None
        self._snapshot = PerformanceSnapshot(
            generation_seconds=self._snapshot.generation_seconds,
            total_generated_schedules=self._snapshot.total_generated_schedules,
            schedules_stored_sqlite=self._snapshot.schedules_stored_sqlite,
            domain_prunes=self._snapshot.domain_prunes,
            threshold_rejections=self._snapshot.threshold_rejections,
            forward_checking_rejections=self._snapshot.forward_checking_rejections,
            ranking_seconds=elapsed,
            load_more_batch_seconds=self._snapshot.load_more_batch_seconds,
            auto_load_batch_seconds=self._snapshot.auto_load_batch_seconds,
            sqlite_stored_row_count=self._snapshot.sqlite_stored_row_count,
            active_batch_size=self._snapshot.active_batch_size,
        )
        return self._snapshot

    def start_load_batch(self, *, batch_size: int, auto_load: bool) -> None:
        """Record Load More / Auto Load batch start."""
        self._load_batch_started_at = self._clock()
        self._load_batch_is_auto = auto_load
        self._snapshot = PerformanceSnapshot(
            generation_seconds=self._snapshot.generation_seconds,
            total_generated_schedules=self._snapshot.total_generated_schedules,
            schedules_stored_sqlite=self._snapshot.schedules_stored_sqlite,
            domain_prunes=self._snapshot.domain_prunes,
            threshold_rejections=self._snapshot.threshold_rejections,
            forward_checking_rejections=self._snapshot.forward_checking_rejections,
            ranking_seconds=self._snapshot.ranking_seconds,
            load_more_batch_seconds=self._snapshot.load_more_batch_seconds,
            auto_load_batch_seconds=self._snapshot.auto_load_batch_seconds,
            sqlite_stored_row_count=self._snapshot.sqlite_stored_row_count,
            active_batch_size=batch_size,
        )

    def finish_load_batch(
        self,
        *,
        sqlite_stored_row_count: int = 0,
    ) -> PerformanceSnapshot:
        """Record the latest Load More / Auto Load batch duration."""
        elapsed = self._elapsed_since(self._load_batch_started_at)
        self._load_batch_started_at = None
        load_seconds = self._snapshot.load_more_batch_seconds
        auto_seconds = self._snapshot.auto_load_batch_seconds
        if self._load_batch_is_auto:
            auto_seconds = elapsed
        else:
            load_seconds = elapsed
        self._load_batch_is_auto = False

        self._snapshot = PerformanceSnapshot(
            generation_seconds=self._snapshot.generation_seconds,
            total_generated_schedules=self._snapshot.total_generated_schedules,
            schedules_stored_sqlite=self._snapshot.schedules_stored_sqlite,
            domain_prunes=self._snapshot.domain_prunes,
            threshold_rejections=self._snapshot.threshold_rejections,
            forward_checking_rejections=self._snapshot.forward_checking_rejections,
            ranking_seconds=self._snapshot.ranking_seconds,
            load_more_batch_seconds=load_seconds,
            auto_load_batch_seconds=auto_seconds,
            sqlite_stored_row_count=sqlite_stored_row_count,
            active_batch_size=self._snapshot.active_batch_size,
        )
        return self._snapshot

    def _elapsed_since(self, started_at: float | None) -> float:
        if started_at is None:
            return 0.0
        return max(0.0, self._clock() - started_at)
