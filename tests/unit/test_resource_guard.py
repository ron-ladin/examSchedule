"""Tests for dynamic RAM/disk resource protection."""

from __future__ import annotations

from collections import namedtuple

from src.domain.resource_guard import (
    ResourceBudget,
    ResourceGuard,
    ResourceSnapshot,
)

_DiskUsage = namedtuple("usage", "total used free")
_VMem = namedtuple("vmem", "total available")
_MemInfo = namedtuple("meminfo", "rss")

MB = 1024 * 1024


class _FakeProcess:
    def __init__(self, rss: int):
        self._rss = rss

    def memory_info(self):
        return _MemInfo(rss=self._rss)


class _FakePsutil:
    def __init__(self, *, total_mb: float, available_mb: float, rss_mb: float):
        self._total = int(total_mb * MB)
        self._available = int(available_mb * MB)
        self._rss = int(rss_mb * MB)

    def virtual_memory(self):
        return _VMem(total=self._total, available=self._available)

    def Process(self):
        return _FakeProcess(self._rss)


def _disk(total_mb: float, free_mb: float):
    return _DiskUsage(
        total=int(total_mb * MB),
        used=int((total_mb - free_mb) * MB),
        free=int(free_mb * MB),
    )


def test_dynamic_budget_uses_machine_ram_and_disk_baselines(tmp_path):
    guard = ResourceGuard(
        lambda: tmp_path / "cache.sqlite3",
        psutil_module=_FakePsutil(
            total_mb=16_384,
            available_mb=12_000,
            rss_mb=512,
        ),
        disk_usage_func=lambda _path: _disk(total_mb=100_000, free_mb=80_000),
    )

    snapshot = guard.snapshot()
    budget = guard.budget(snapshot)

    assert snapshot.process_rss_mb == 512
    assert budget.ram_hard_limit_mb == 16_384 * 0.90
    assert budget.ram_soft_limit_mb == 16_384 * 0.80
    assert budget.min_free_ram_mb == max(1536, 16_384 * 0.15)
    assert budget.max_db_size_mb == 40_000
    assert budget.min_free_disk_mb == 8_000


def test_db_wal_and_shm_sizes_are_included(tmp_path):
    db_path = tmp_path / "cache.sqlite3"
    db_path.write_bytes(b"0" * (2 * MB))
    db_path.with_name(db_path.name + "-wal").write_bytes(b"1" * MB)
    db_path.with_name(db_path.name + "-shm").write_bytes(b"2" * (3 * MB))
    guard = ResourceGuard(
        lambda: db_path,
        psutil_module=None,
        disk_usage_func=lambda _path: _disk(total_mb=100_000, free_mb=80_000),
    )

    snapshot = guard.snapshot()

    assert snapshot.db_size_mb == 2
    assert snapshot.wal_size_mb == 1
    assert snapshot.shm_size_mb == 3
    assert snapshot.db_total_size_mb == 6


def test_soft_warning_and_hard_pause_decisions(tmp_path):
    budget = ResourceBudget(
        ram_soft_limit_mb=800,
        ram_hard_limit_mb=1000,
        min_free_ram_mb=300,
        max_db_size_mb=10_000,
        min_free_disk_mb=2000,
    )
    guard = ResourceGuard(
        lambda: tmp_path / "cache.sqlite3",
        budget=budget,
        psutil_module=_FakePsutil(total_mb=4000, available_mb=1000, rss_mb=790),
        disk_usage_func=lambda _path: _disk(total_mb=100_000, free_mb=80_000),
    )

    warning = guard.evaluate(estimated_ram_growth_mb=20)
    hard = guard.evaluate(estimated_ram_growth_mb=250)

    assert warning.can_continue is True
    assert warning.should_warn is True
    assert "soft limit" in warning.reason
    assert hard.can_continue is False
    assert "hard limit" in hard.reason


def test_ram_with_more_than_three_gb_available_continues_without_warning(tmp_path):
    guard = ResourceGuard(
        lambda: tmp_path / "cache.sqlite3",
        psutil_module=_FakePsutil(
            total_mb=16_384,
            available_mb=3400,
            rss_mb=512,
        ),
        disk_usage_func=lambda _path: _disk(total_mb=100_000, free_mb=80_000),
    )

    decision = guard.evaluate(estimated_ram_growth_mb=100)

    assert decision.can_continue is True
    assert decision.should_warn is False
    assert decision.reason is None


def test_eighty_five_percent_ram_usage_warns_instead_of_hard_stop(tmp_path):
    guard = ResourceGuard(
        lambda: tmp_path / "cache.sqlite3",
        psutil_module=_FakePsutil(
            total_mb=16_384,
            available_mb=2400,
            rss_mb=512,
        ),
        disk_usage_func=lambda _path: _disk(total_mb=100_000, free_mb=80_000),
    )

    decision = guard.evaluate()

    assert decision.can_continue is True
    assert decision.should_warn is True
    assert "available RAM" in decision.reason


def test_critical_available_ram_blocks_before_hard_reserve_is_exhausted(tmp_path):
    guard = ResourceGuard(
        lambda: tmp_path / "cache.sqlite3",
        psutil_module=_FakePsutil(
            total_mb=16_384,
            available_mb=1500,
            rss_mb=512,
        ),
        disk_usage_func=lambda _path: _disk(total_mb=100_000, free_mb=80_000),
    )

    decision = guard.evaluate()

    assert decision.can_continue is False
    assert decision.should_warn is True
    assert "critical reserve" in decision.reason


def test_projected_next_batch_below_hard_ram_reserve_blocks(tmp_path):
    guard = ResourceGuard(
        lambda: tmp_path / "cache.sqlite3",
        psutil_module=_FakePsutil(
            total_mb=16_384,
            available_mb=2000,
            rss_mb=512,
        ),
        disk_usage_func=lambda _path: _disk(total_mb=100_000, free_mb=80_000),
    )

    decision = guard.evaluate(estimated_ram_growth_mb=1100)

    assert decision.can_continue is False
    assert decision.should_warn is True
    assert "hard reserve" in decision.reason


def test_fallback_without_psutil_still_checks_disk(tmp_path):
    db_path = tmp_path / "cache.sqlite3"
    db_path.write_bytes(b"0" * MB)
    budget = ResourceBudget(
        ram_soft_limit_mb=float("inf"),
        ram_hard_limit_mb=float("inf"),
        min_free_ram_mb=0,
        max_db_size_mb=500,
        min_free_disk_mb=200,
    )
    guard = ResourceGuard(
        lambda: db_path,
        budget=budget,
        psutil_module=None,
        disk_usage_func=lambda _path: _disk(total_mb=1000, free_mb=250),
    )

    decision = guard.evaluate(estimated_db_growth_mb=100)

    assert decision.snapshot.process_rss_mb == 0
    assert decision.can_continue is False
    assert "disk reserve" in decision.reason


def test_record_batch_updates_rolling_per_schedule_estimates():
    guard = ResourceGuard(psutil_module=None)
    before = ResourceSnapshot(
        process_rss_mb=100,
        system_total_ram_mb=0,
        system_available_ram_mb=float("inf"),
        db_size_mb=20,
        wal_size_mb=5,
        shm_size_mb=1,
        db_total_size_mb=26,
        free_disk_mb=10_000,
    )
    after = ResourceSnapshot(
        process_rss_mb=110,
        system_total_ram_mb=0,
        system_available_ram_mb=float("inf"),
        db_size_mb=30,
        wal_size_mb=7,
        shm_size_mb=1,
        db_total_size_mb=38,
        free_disk_mb=9988,
    )

    deltas = guard.record_batch(before, after, 10)

    assert deltas.ram_per_schedule_kb == 1024
    assert deltas.db_per_schedule_kb == 1024
    assert deltas.wal_per_schedule_kb == 204.8
    assert deltas.sqlite_total_per_schedule_kb == 1228.8
    estimate = guard.estimate_next_batch(10)
    assert estimate["estimated_ram_growth_mb"] == 10
    assert estimate["estimated_db_growth_mb"] == 12
