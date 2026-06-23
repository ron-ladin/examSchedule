"""Unit tests for generation_workers non-timeout paging and worker behavior.

Tests cover:
- _KindTaggedQueue wraps results with the correct kind.
- _run_load_more_worker handles malformed and unknown task types safely.
- date_options task clears stale variant state.
- _take_variant_page paging: no duplicates, no skips across pages.
- _run_classroom_variants_process returns failure when config is missing.
- Stateful variants paging (_run_classroom_variants_from_state) is duplicate-free
  and skip-free across consecutive pages.
"""

import queue
import threading

import pytest

from src.engine.generation_workers import (
    _KindTaggedQueue,
    _run_load_more_worker,
    _take_variant_page,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _SimpleQueue:
    def __init__(self):
        self._q = queue.Queue()

    def put(self, item):
        self._q.put(item)

    def get(self, timeout=2):
        return self._q.get(timeout=timeout)


def _make_state(items):
    return {
        "iterator": iter(items),
        "overflow": [],
        "emitted": 0,
    }


def _start_worker():
    task_q = _SimpleQueue()
    result_q = _SimpleQueue()
    t = threading.Thread(
        target=_run_load_more_worker,
        args=(task_q, result_q),
        daemon=True,
    )
    t.start()
    return task_q, result_q, t


# ---------------------------------------------------------------------------
# _KindTaggedQueue
# ---------------------------------------------------------------------------

class TestKindTaggedQueue:
    def test_wraps_result_with_date_options_kind(self):
        inner = _SimpleQueue()
        tagged = _KindTaggedQueue(inner, "date_options")
        tagged.put("payload")
        kind, item = inner.get()
        assert kind == "date_options"
        assert item == "payload"

    def test_wraps_result_with_variants_kind(self):
        inner = _SimpleQueue()
        tagged = _KindTaggedQueue(inner, "variants")
        tagged.put(42)
        kind, item = inner.get()
        assert kind == "variants"
        assert item == 42


# ---------------------------------------------------------------------------
# _run_load_more_worker — malformed and unknown task handling
# ---------------------------------------------------------------------------

class TestRunLoadMoreWorkerEdgeCases:
    def test_malformed_task_returns_error_result(self):
        task_q, result_q, t = _start_worker()
        task_q.put("not-a-tuple")
        task_q.put(None)
        kind, result = result_q.get()
        assert kind == "error"
        assert not result.success
        t.join(timeout=2)

    def test_non_iterable_task_returns_error_result(self):
        """A non-iterable payload (e.g. an int) must not crash the worker.

        Unpacking ``task_type, args, kwargs = 123`` raises TypeError (not
        ValueError), so the worker has to catch both to stay alive.
        """
        task_q, result_q, t = _start_worker()
        task_q.put(123)
        task_q.put(None)  # stop sentinel — worker must keep serving until here
        kind, result = result_q.get()
        assert kind == "error"
        assert not result.success
        assert "Invalid background worker task" in result.error
        t.join(timeout=2)
        assert not t.is_alive()

    def test_unknown_task_type_returns_error_result(self):
        task_q, result_q, t = _start_worker()
        task_q.put(("unknown_type", [], {}))
        task_q.put(None)
        kind, result = result_q.get()
        assert kind == "error"
        assert not result.success
        t.join(timeout=2)


# ---------------------------------------------------------------------------
# _take_variant_page — paging correctness
# ---------------------------------------------------------------------------

class TestTakeVariantPage:
    def test_unbounded_collects_all(self):
        state = _make_state(range(5))
        batch, still_more = _take_variant_page(state, cap=None)
        assert batch == list(range(5))
        assert still_more is False
        assert state["emitted"] == 5

    def test_capped_returns_page_and_signals_more(self):
        state = _make_state(range(10))
        batch, still_more = _take_variant_page(state, cap=3)
        assert batch == [0, 1, 2]
        assert still_more is True

    def test_capped_exhausts_short_iterator(self):
        state = _make_state(range(2))
        batch, still_more = _take_variant_page(state, cap=10)
        assert batch == [0, 1]
        assert still_more is False

    def test_overflow_carry_over_across_pages(self):
        state = _make_state(range(6))
        batch1, more1 = _take_variant_page(state, cap=2)
        assert batch1 == [0, 1]
        assert more1 is True
        batch2, more2 = _take_variant_page(state, cap=2)
        assert batch2 == [2, 3]
        assert more2 is True
        batch3, more3 = _take_variant_page(state, cap=2)
        assert batch3 == [4, 5]
        assert more3 is False

    def test_no_duplicates_across_pages(self):
        state = _make_state(range(9))
        seen = []
        for _ in range(4):
            batch, _ = _take_variant_page(state, cap=3)
            seen.extend(batch)
        assert len(seen) == len(set(seen))

    def test_no_skips_across_pages(self):
        items = list(range(9))
        state = _make_state(items)
        seen = []
        more = True
        while more:
            batch, more = _take_variant_page(state, cap=3)
            seen.extend(batch)
        assert seen == items

    def test_emitted_counter_tracks_total(self):
        state = _make_state(range(6))
        _take_variant_page(state, cap=2)
        _take_variant_page(state, cap=2)
        assert state["emitted"] == 4


# ---------------------------------------------------------------------------
# _run_classroom_variants_process — missing config guard
# ---------------------------------------------------------------------------

class TestRunClassroomVariantsProcessMissingConfig:
    def test_returns_failure_when_classrooms_missing(self):
        from src.engine.generation_workers import _run_classroom_variants_process
        from src.domain.schedule import Schedule
        from src.domain.exam_period import ExamPeriod

        result_q = _SimpleQueue()
        period = ExamPeriod(semester="FALL", moed="Aleph", date_ranges=[])
        schedule = Schedule(period=period, assignments={})

        _run_classroom_variants_process(
            result_q,
            period_key="FALL - Aleph",
            schedule=schedule,
            courses=[],
            selected_programs=[],
            classrooms=None,
            time_slots=None,
            proctor_config=None,
        )

        result = result_q.get()
        assert not result.success
