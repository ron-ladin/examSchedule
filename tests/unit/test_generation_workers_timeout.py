"""Unit tests for the generation-timeout plumbing in _MemoryExporter and helpers.

These tests use lightweight fakes — no real multiprocessing, no Qt, no file I/O.
They verify that timeout_seconds=<small> causes early truncation with
has_more=True, while timeout_seconds=None preserves the original unlimited behaviour.
"""

import time

from src.engine.generation_workers import (
    _MemoryExporter,
    _take_variant_page,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slow_schedules(delay: float = 0.05):
    """Yield one item, then stall long enough that the deadline fires."""
    yield 0
    time.sleep(delay)
    yield 1
    yield 2


class _FakeCourse:
    """Minimal stand-in for Course — only id is needed."""
    def __init__(self, cid: str) -> None:
        self.id = cid


class _MinimalExporter(_MemoryExporter):
    """_MemoryExporter with _sort bypassed (no domain objects required)."""
    def _sort(self, schedules, courses):
        return schedules


# ---------------------------------------------------------------------------
# _MemoryExporter timeout tests
# ---------------------------------------------------------------------------

class TestMemoryExporterTimeout:
    """_MemoryExporter with cap=None and a tight timeout stops early."""

    def _run(self, iterator, timeout_seconds):
        exporter = _MinimalExporter(cap=None, timeout_seconds=timeout_seconds)
        exporter.export_schedules({"A": iterator}, {"c1": _FakeCourse("c1")})
        return exporter

    def test_no_timeout_collects_all(self):
        exporter = self._run(iter(range(10)), timeout_seconds=None)

        assert exporter.schedules_by_period["A"] == list(range(10))
        assert exporter.has_more_by_period["A"] is False
        assert "A" not in exporter.truncated_periods

    def test_tight_timeout_truncates(self):
        # One item arrives immediately; then a 0.2 s sleep fires before timeout.
        exporter = self._run(_slow_schedules(delay=0.2), timeout_seconds=0.05)

        assert len(exporter.schedules_by_period["A"]) >= 1
        assert exporter.has_more_by_period["A"] is True
        assert "A" in exporter.truncated_periods

    def test_generous_timeout_does_not_truncate_finite_iterator(self):
        exporter = self._run(iter(range(10)), timeout_seconds=10.0)

        assert exporter.schedules_by_period["A"] == list(range(10))
        assert exporter.has_more_by_period["A"] is False
        assert "A" not in exporter.truncated_periods


# ---------------------------------------------------------------------------
# _take_variant_page timeout tests
# ---------------------------------------------------------------------------

class TestTakeVariantPageTimeout:
    """_take_variant_page with a past deadline returns partial batch + still_more=True."""

    def _make_state(self, items):
        return {
            "iterator": iter(items),
            "overflow": [],
            "emitted": 0,
        }

    def test_no_deadline_takes_all_unbounded(self):
        state = self._make_state(range(5))
        batch, still_more = _take_variant_page(state, cap=None, deadline=None)

        assert batch == list(range(5))
        assert still_more is False

    def test_expired_deadline_stops_early_unbounded(self):
        past = time.perf_counter() - 1.0  # already expired
        state = self._make_state(range(100))
        batch, still_more = _take_variant_page(state, cap=None, deadline=past)

        assert still_more is True
        assert len(batch) < 100

    def test_expired_deadline_stops_early_capped(self):
        past = time.perf_counter() - 1.0
        state = self._make_state(range(100))
        batch, still_more = _take_variant_page(state, cap=50, deadline=past)

        assert still_more is True
        assert len(batch) < 50

    def test_generous_deadline_capped_normal_behaviour(self):
        future = time.perf_counter() + 60.0
        state = self._make_state(range(5))
        batch, still_more = _take_variant_page(state, cap=3, deadline=future)

        assert batch == [0, 1, 2]
        assert still_more is True  # items 3 and 4 remain

    def test_no_deadline_capped_exhausts_iterator(self):
        state = self._make_state(range(2))
        batch, still_more = _take_variant_page(state, cap=10, deadline=None)

        assert batch == [0, 1]
        assert still_more is False
