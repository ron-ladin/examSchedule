"""Dynamic resource guard for large schedule result caches.

The guard measures current process/disk usage and uses recent batch deltas to
decide whether another Load More / Auto Load batch is safe. It deliberately
does not impose a normal schedule-count cap; SQLite row counts can grow as long
as RAM and disk budgets remain healthy.
"""

from __future__ import annotations

import math
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no cover - presence depends on the user's environment.
    import psutil as _PSUTIL
except Exception:  # pragma: no cover - exercised by fallback tests.
    _PSUTIL = None

_MB = 1024 * 1024
_GB_MB = 1024.0
_EWMA_ALPHA = 0.3


@dataclass(frozen=True)
class ResourceBudget:
    ram_soft_limit_mb: float
    ram_hard_limit_mb: float
    min_free_ram_mb: float
    max_db_size_mb: float
    min_free_disk_mb: float


@dataclass(frozen=True)
class ResourceSnapshot:
    process_rss_mb: float
    system_total_ram_mb: float
    system_available_ram_mb: float
    db_size_mb: float
    wal_size_mb: float
    shm_size_mb: float
    db_total_size_mb: float
    free_disk_mb: float


@dataclass(frozen=True)
class ResourceDecision:
    can_continue: bool
    should_warn: bool
    reason: str | None
    snapshot: ResourceSnapshot
    budget: ResourceBudget


@dataclass(frozen=True)
class BatchResourceDeltas:
    rss_delta_mb: float
    db_delta_mb: float
    wal_delta_mb: float
    sqlite_total_delta_mb: float
    ram_per_schedule_kb: float
    db_per_schedule_kb: float
    wal_per_schedule_kb: float
    sqlite_total_per_schedule_kb: float
    rolling_ram_per_schedule_kb: float
    rolling_db_per_schedule_kb: float
    rolling_wal_per_schedule_kb: float
    rolling_sqlite_total_per_schedule_kb: float


class ResourceGuard:
    """Evaluate RAM/disk pressure for growing SQLite-backed result caches."""

    def __init__(
        self,
        db_path_provider: Callable[[], Path | str | None] | None = None,
        *,
        budget: ResourceBudget | None = None,
        psutil_module: Any = _PSUTIL,
        disk_usage_func: Callable[[str | Path], shutil._ntuple_diskusage] = (
            shutil.disk_usage
        ),
        max_db_size_mb: float | None = None,
    ) -> None:
        self._db_path_provider = db_path_provider
        self._budget_override = budget
        self._psutil = psutil_module
        self._disk_usage_func = disk_usage_func
        self._configured_max_db_size_mb = max_db_size_mb
        self._initial_free_disk_mb: float | None = None

        self._ram_per_schedule_kb: float | None = None
        self._db_per_schedule_kb: float | None = None
        self._wal_per_schedule_kb: float | None = None
        self._sqlite_total_per_schedule_kb: float | None = None

    @property
    def ram_per_schedule_kb(self) -> float:
        return self._ram_per_schedule_kb or 0.0

    @property
    def db_per_schedule_kb(self) -> float:
        return self._db_per_schedule_kb or 0.0

    @property
    def wal_per_schedule_kb(self) -> float:
        return self._wal_per_schedule_kb or 0.0

    @property
    def sqlite_total_per_schedule_kb(self) -> float:
        return self._sqlite_total_per_schedule_kb or 0.0

    def snapshot(self, db_path: Path | str | None = None) -> ResourceSnapshot:
        """Measure current process RAM and SQLite/disk usage.

        When psutil is unavailable, RAM values are reported as unknown-safe
        values while disk checks continue through ``shutil.disk_usage``.
        """
        resolved_db = self._resolve_db_path(db_path)
        disk_target = self._disk_target(resolved_db)
        disk_usage = self._disk_usage_func(disk_target)
        disk_total_mb = disk_usage.total / _MB
        free_disk_mb = disk_usage.free / _MB
        if self._initial_free_disk_mb is None:
            self._initial_free_disk_mb = free_disk_mb

        total_ram_mb = 0.0
        available_ram_mb = math.inf
        process_rss_mb = 0.0
        if self._psutil is not None:
            try:
                virtual_memory = self._psutil.virtual_memory()
                total_ram_mb = virtual_memory.total / _MB
                available_ram_mb = virtual_memory.available / _MB
            except Exception:
                total_ram_mb = 0.0
                available_ram_mb = math.inf

            try:
                process_rss_mb = self._psutil.Process().memory_info().rss / _MB
            except Exception:
                process_rss_mb = 0.0

        db_size_mb = self._file_size_mb(resolved_db)
        wal_size_mb = self._file_size_mb(self._sidecar_path(resolved_db, "-wal"))
        shm_size_mb = self._file_size_mb(self._sidecar_path(resolved_db, "-shm"))

        return ResourceSnapshot(
            process_rss_mb=process_rss_mb,
            system_total_ram_mb=total_ram_mb,
            system_available_ram_mb=available_ram_mb,
            db_size_mb=db_size_mb,
            wal_size_mb=wal_size_mb,
            shm_size_mb=shm_size_mb,
            db_total_size_mb=db_size_mb + wal_size_mb + shm_size_mb,
            free_disk_mb=free_disk_mb,
        )

    def budget(self, snapshot: ResourceSnapshot | None = None) -> ResourceBudget:
        if self._budget_override is not None:
            return self._budget_override

        snapshot = snapshot or self.snapshot()
        if snapshot.system_total_ram_mb > 0:
            ram_hard_limit_mb = max(512.0, snapshot.system_total_ram_mb * 0.25)
            ram_soft_limit_mb = ram_hard_limit_mb * 0.8
            min_free_ram_mb = max(2048.0, snapshot.system_total_ram_mb * 0.15)
        else:
            ram_hard_limit_mb = math.inf
            ram_soft_limit_mb = math.inf
            min_free_ram_mb = 0.0

        disk_total_baseline_mb = snapshot.free_disk_mb + snapshot.db_total_size_mb
        min_free_disk_mb = max(5.0 * _GB_MB, disk_total_baseline_mb * 0.10)

        if self._configured_max_db_size_mb is not None:
            max_db_size_mb = self._configured_max_db_size_mb
        else:
            initial_free = (
                self._initial_free_disk_mb
                if self._initial_free_disk_mb is not None
                else snapshot.free_disk_mb
            )
            max_db_size_mb = max(0.0, initial_free * 0.5)

        return ResourceBudget(
            ram_soft_limit_mb=ram_soft_limit_mb,
            ram_hard_limit_mb=ram_hard_limit_mb,
            min_free_ram_mb=min_free_ram_mb,
            max_db_size_mb=max_db_size_mb,
            min_free_disk_mb=min_free_disk_mb,
        )

    def estimate_next_batch(
        self,
        schedule_count: int,
    ) -> dict[str, float]:
        """Estimate next-batch RAM/SQLite growth from rolling per-row averages."""
        count = max(0, int(schedule_count))
        return {
            "estimated_ram_growth_mb": (self.ram_per_schedule_kb * count) / 1024.0,
            "estimated_db_growth_mb": (
                self.sqlite_total_per_schedule_kb * count
            )
            / 1024.0,
        }

    def evaluate(
        self,
        *,
        estimated_ram_growth_mb: float = 0.0,
        estimated_db_growth_mb: float = 0.0,
        db_path: Path | str | None = None,
    ) -> ResourceDecision:
        snapshot = self.snapshot(db_path)
        budget = self.budget(snapshot)

        projected_rss = snapshot.process_rss_mb + max(0.0, estimated_ram_growth_mb)
        projected_available_ram = (
            snapshot.system_available_ram_mb - max(0.0, estimated_ram_growth_mb)
        )
        projected_db_total = snapshot.db_total_size_mb + max(
            0.0,
            estimated_db_growth_mb,
        )
        projected_free_disk = snapshot.free_disk_mb - max(
            0.0,
            estimated_db_growth_mb,
        )

        hard_reasons: list[str] = []
        if math.isfinite(budget.ram_hard_limit_mb):
            if projected_rss >= budget.ram_hard_limit_mb:
                hard_reasons.append("process RAM would exceed the hard limit")
            if projected_available_ram <= budget.min_free_ram_mb:
                hard_reasons.append("available RAM reserve would be exhausted")

        if projected_db_total >= budget.max_db_size_mb:
            hard_reasons.append("SQLite database would exceed the size budget")
        if projected_free_disk <= budget.min_free_disk_mb:
            hard_reasons.append("free disk reserve would be exhausted")

        if hard_reasons:
            return ResourceDecision(
                can_continue=False,
                should_warn=True,
                reason="; ".join(hard_reasons),
                snapshot=snapshot,
                budget=budget,
            )

        warn_reasons: list[str] = []
        if math.isfinite(budget.ram_soft_limit_mb):
            if projected_rss >= budget.ram_soft_limit_mb:
                warn_reasons.append("process RAM is near the soft limit")
            if projected_available_ram <= budget.min_free_ram_mb * 1.25:
                warn_reasons.append("available RAM is near reserve")
        if budget.max_db_size_mb > 0 and projected_db_total >= budget.max_db_size_mb * 0.8:
            warn_reasons.append("SQLite database is near its size budget")
        if projected_free_disk <= budget.min_free_disk_mb * 1.25:
            warn_reasons.append("free disk is near reserve")

        return ResourceDecision(
            can_continue=True,
            should_warn=bool(warn_reasons),
            reason="; ".join(warn_reasons) if warn_reasons else None,
            snapshot=snapshot,
            budget=budget,
        )

    def record_batch(
        self,
        before: ResourceSnapshot,
        after: ResourceSnapshot,
        schedule_count: int,
    ) -> BatchResourceDeltas:
        count = max(0, int(schedule_count))
        rss_delta_mb = max(0.0, after.process_rss_mb - before.process_rss_mb)
        db_delta_mb = max(0.0, after.db_size_mb - before.db_size_mb)
        wal_delta_mb = max(0.0, after.wal_size_mb - before.wal_size_mb)
        sqlite_total_delta_mb = max(
            0.0,
            after.db_total_size_mb - before.db_total_size_mb,
        )

        if count > 0:
            ram_per_schedule_kb = rss_delta_mb * 1024.0 / count
            db_per_schedule_kb = db_delta_mb * 1024.0 / count
            wal_per_schedule_kb = wal_delta_mb * 1024.0 / count
            sqlite_total_per_schedule_kb = sqlite_total_delta_mb * 1024.0 / count
            self._ram_per_schedule_kb = self._ewma(
                self._ram_per_schedule_kb,
                ram_per_schedule_kb,
            )
            self._db_per_schedule_kb = self._ewma(
                self._db_per_schedule_kb,
                db_per_schedule_kb,
            )
            self._wal_per_schedule_kb = self._ewma(
                self._wal_per_schedule_kb,
                wal_per_schedule_kb,
            )
            self._sqlite_total_per_schedule_kb = self._ewma(
                self._sqlite_total_per_schedule_kb,
                sqlite_total_per_schedule_kb,
            )
        else:
            ram_per_schedule_kb = 0.0
            db_per_schedule_kb = 0.0
            wal_per_schedule_kb = 0.0
            sqlite_total_per_schedule_kb = 0.0

        return BatchResourceDeltas(
            rss_delta_mb=rss_delta_mb,
            db_delta_mb=db_delta_mb,
            wal_delta_mb=wal_delta_mb,
            sqlite_total_delta_mb=sqlite_total_delta_mb,
            ram_per_schedule_kb=ram_per_schedule_kb,
            db_per_schedule_kb=db_per_schedule_kb,
            wal_per_schedule_kb=wal_per_schedule_kb,
            sqlite_total_per_schedule_kb=sqlite_total_per_schedule_kb,
            rolling_ram_per_schedule_kb=self.ram_per_schedule_kb,
            rolling_db_per_schedule_kb=self.db_per_schedule_kb,
            rolling_wal_per_schedule_kb=self.wal_per_schedule_kb,
            rolling_sqlite_total_per_schedule_kb=(
                self.sqlite_total_per_schedule_kb
            ),
        )

    def _resolve_db_path(self, db_path: Path | str | None) -> Path | None:
        if db_path is not None:
            return Path(db_path)
        if self._db_path_provider is None:
            return None
        provided = self._db_path_provider()
        return None if provided is None else Path(provided)

    def _disk_target(self, db_path: Path | None) -> Path:
        if db_path is None:
            return Path.cwd()
        if db_path.exists():
            return db_path.parent if db_path.is_file() else db_path
        return db_path.parent

    @staticmethod
    def _sidecar_path(db_path: Path | None, suffix: str) -> Path | None:
        if db_path is None:
            return None
        return db_path.with_name(db_path.name + suffix)

    @staticmethod
    def _file_size_mb(path: Path | None) -> float:
        if path is None:
            return 0.0
        try:
            return path.stat().st_size / _MB
        except OSError:
            return 0.0

    @staticmethod
    def _ewma(previous: float | None, value: float) -> float:
        if previous is None:
            return value
        return previous * (1.0 - _EWMA_ALPHA) + value * _EWMA_ALPHA
