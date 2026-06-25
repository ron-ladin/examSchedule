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

import multiprocessing
import pickle
import queue
import threading
from datetime import date, time as dt_time

import pytest

from src.domain.exam_period import ExamPeriod
from src.domain.generation_result import GenerationDone, GenerationResult
from src.domain.classroom import Classroom
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.proctor import ProctorConfig
from src.domain.time_slot import TimeSlot
from src.engine.app_controller import CLASSROOM_VARIANT_MODE_FIRST
from src.engine.generation_workers import (
    _KindTaggedQueue,
    _run_generation_process,
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


class TestRunGenerationProcessStreaming:
    def test_single_period_done_marker_carries_period_key(self):
        result_q = _SimpleQueue()
        period = ExamPeriod(
            semester="FALL",
            moed="Aleph",
            date_ranges=[(date(2026, 1, 5), date(2026, 1, 5))],
        )

        _run_generation_process(
            result_q,
            courses=[],
            exam_periods=[period],
            selected_programs=[],
            cap=1,
            stream=True,
        )

        result = result_q.get()

        assert isinstance(result, GenerationDone)
        assert result.period_key == "FALL - Aleph"


class TestMultiprocessingSerialization:
    def test_generation_dtos_round_trip_through_pickle(self):
        ok = GenerationResult.ok({"FALL - Aleph": []}, {}, {"FALL - Aleph"})
        failure = GenerationResult.failure("boom")
        done = GenerationDone.done({"FALL - Aleph"}, period_key="FALL - Aleph")

        assert pickle.loads(pickle.dumps(ok)) == ok
        assert pickle.loads(pickle.dumps(failure)) == failure
        assert pickle.loads(pickle.dumps(done)) == done

    def test_representative_worker_arguments_are_picklable(self):
        period = ExamPeriod(
            semester="FALL",
            moed="Aleph",
            date_ranges=[(date(2026, 1, 5), date(2026, 1, 5))],
        )
        courses = [
            Course(
                id="C1",
                name="Algorithms",
                instructor="Dr. Ada",
                evaluation_type="Exam",
                offerings=[
                    CourseOffering(
                        "83101",
                        1,
                        "FALL",
                        "Obligatory",
                        student_count=20,
                    )
                ],
            )
        ]
        kwargs = {
            "settings": None,
            "cap": 1,
            "classrooms": [Classroom("R1", 40)],
            "time_slots": [TimeSlot(dt_time(9, 0))],
            "proctor_config": ProctorConfig(20),
            "allow_unassigned_classrooms": False,
            "classroom_variant_mode": CLASSROOM_VARIANT_MODE_FIRST,
            "stream": True,
        }

        payload = (courses, [period], ["83101"], kwargs)

        assert pickle.loads(pickle.dumps(payload))[2] == ["83101"]

    def test_real_spawn_generation_smoke_reaps_own_child_pid(self):
        if "spawn" not in multiprocessing.get_all_start_methods():
            pytest.skip("spawn multiprocessing context is unavailable")

        ctx = multiprocessing.get_context("spawn")
        result_q = ctx.Queue()
        period = ExamPeriod(
            semester="FALL",
            moed="Aleph",
            date_ranges=[(date(2026, 1, 5), date(2026, 1, 5))],
        )
        proc = ctx.Process(
            target=_run_generation_process,
            args=(result_q, [], [period], []),
            kwargs={"cap": 1, "stream": True},
            daemon=True,
        )

        proc.start()
        pid = proc.pid
        try:
            result = result_q.get(timeout=10)
            proc.join(timeout=10)
        finally:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2)
            result_q.cancel_join_thread()
            result_q.close()

        assert pid is not None
        assert not proc.is_alive()
        assert proc.exitcode == 0
        assert isinstance(result, GenerationDone)
        assert result.period_key == "FALL - Aleph"


def _feature4_courses() -> list[Course]:
    return [
        Course(
            id="C1",
            name="Algorithms",
            instructor="Dr. Ada",
            evaluation_type="Exam",
            offerings=[
                CourseOffering(
                    "83101",
                    1,
                    "FALL",
                    "Obligatory",
                    student_count=30,
                ),
                CourseOffering(
                    "83101",
                    1,
                    "SPRI",
                    "Obligatory",
                    student_count=30,
                ),
            ],
        )
    ]


def _semantic_signature(result: GenerationResult) -> tuple:
    by_period = []
    for period_key, schedules in sorted(result.schedules_by_period.items()):
        schedule_sigs = []
        for schedule in schedules:
            assignments = tuple(
                sorted((cid, exam_date.isoformat()) for cid, exam_date in schedule.assignments.items())
            )
            rooms = []
            for cid, assignments_for_course in sorted(schedule.classroom_assignments.items()):
                room_sig = tuple(
                    (
                        item.room.room_id,
                        item.slot.time.isoformat(timespec="minutes"),
                        item.date.isoformat(),
                        item.students_assigned,
                        item.proctor_count,
                    )
                    for item in assignments_for_course
                )
                rooms.append((cid, room_sig))
            schedule_sigs.append((assignments, tuple(rooms)))
        by_period.append((period_key, tuple(schedule_sigs)))
    return tuple(by_period), tuple(sorted(result.truncated_periods))


class TestSequentialVsPerPeriodGeneration:
    def test_parallel_period_split_preserves_feature4_semantics(self):
        courses = _feature4_courses()
        periods = [
            ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 5))]),
            ExamPeriod("SPRI", "Aleph", [(date(2026, 6, 1), date(2026, 6, 1))]),
        ]
        common_kwargs = {
            "cap": 10,
            "classrooms": [Classroom("R1", 100)],
            "time_slots": [TimeSlot(dt_time(9, 0))],
            "proctor_config": ProctorConfig(20),
            "allow_unassigned_classrooms": False,
            "classroom_variant_mode": CLASSROOM_VARIANT_MODE_FIRST,
        }

        sequential_q = _SimpleQueue()
        _run_generation_process(
            sequential_q,
            courses,
            periods,
            ["83101"],
            **common_kwargs,
        )
        sequential = sequential_q.get()

        merged_by_period = {}
        courses_by_id = {}
        truncated = set()
        for period in periods:
            period_q = _SimpleQueue()
            _run_generation_process(
                period_q,
                courses,
                [period],
                ["83101"],
                **common_kwargs,
            )
            partial = period_q.get()
            merged_by_period.update(partial.schedules_by_period)
            courses_by_id.update(partial.courses_by_id)
            truncated.update(partial.truncated_periods)

        split = GenerationResult.ok(merged_by_period, courses_by_id, truncated)

        assert _semantic_signature(split) == _semantic_signature(sequential)
