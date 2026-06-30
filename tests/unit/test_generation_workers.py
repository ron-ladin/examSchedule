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
from src.domain.settings import Settings
from src.domain.sorting import SortCriterion, SortingConfig, SortRule
from src.domain.threshold import Criterion, ThresholdEntry, ThresholdSettings
from src.domain.time_slot import TimeSlot
from src.engine.app_controller import CLASSROOM_VARIANT_MODE_FIRST
import src.engine.generation_workers as gw
from src.engine.generation_workers import (
    _KindTaggedQueue,
    _run_date_options_from_state,
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


def _date_option_courses() -> list[Course]:
    return [
        Course(
            id="C1",
            name="Algorithms",
            instructor="Dr. Ada",
            evaluation_type="Exam",
            offerings=[CourseOffering("83101", 1, "FALL", "Obligatory")],
        ),
        Course(
            id="C2",
            name="Databases",
            instructor="Dr. Turing",
            evaluation_type="Exam",
            offerings=[CourseOffering("83101", 1, "FALL", "Obligatory")],
        ),
    ]


def _date_option_period(
    start: date = date(2026, 1, 5),
    end: date = date(2026, 1, 7),
    moed: str = "Aleph",
) -> ExamPeriod:
    return ExamPeriod("FALL", moed, [(start, end)])


def _schedule_signature(schedule) -> tuple:
    assignments = tuple(
        sorted(
            (course_id, exam_date.isoformat())
            for course_id, exam_date in schedule.assignments.items()
        )
    )
    rooms = []
    for course_id, assignments_for_course in sorted(
        schedule.classroom_assignments.items()
    ):
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
        rooms.append((course_id, room_sig))
    unassigned = tuple(sorted(schedule.unassigned_classroom_exams.items()))
    return assignments, tuple(rooms), unassigned


def _date_signature(
    result: GenerationResult,
    period_key: str = "FALL - Aleph",
) -> list[tuple]:
    schedules = result.schedules_by_period.get(period_key, [])
    return [
        _schedule_signature(schedule)
        for schedule in schedules
    ]


def _settings(
    thresholds: ThresholdSettings | None = None,
    sorting: SortingConfig | None = None,
) -> Settings:
    return Settings(
        thresholds=thresholds or ThresholdSettings(),
        sorting=sorting or SortingConfig(),
    )


def _direct_generation_result(
    *,
    courses: list[Course],
    periods: list[ExamPeriod],
    selected_programs: list[str],
    settings: Settings,
    period_key: str,
    **kwargs,
) -> GenerationResult:
    direct_q = _SimpleQueue()
    _run_generation_process(
        direct_q,
        courses,
        periods,
        selected_programs,
        settings=settings,
        cap=None,
        period_key=period_key,
        **kwargs,
    )
    return direct_q.get()


def _collect_stateful_date_signatures(
    *,
    courses: list[Course],
    periods: list[ExamPeriod],
    selected_programs: list[str],
    settings: Settings,
    period_key: str,
    cap: int = 2,
    states: dict | None = None,
    **kwargs,
) -> tuple[list[tuple], dict]:
    state_map = {} if states is None else states
    result_q = _SimpleQueue()
    seen: list[tuple] = []
    offset = 0
    more = True
    guard = 0

    while more:
        guard += 1
        assert guard < 20, "stateful date pagination did not terminate"
        _run_date_options_from_state(
            result_q,
            state_map,
            courses=courses,
            exam_periods=periods,
            selected_programs=selected_programs,
            settings=settings,
            cap=cap,
            period_key=period_key,
            offset=offset,
            **kwargs,
        )
        result = result_q.get()
        assert result.success, result.error
        batch = _date_signature(result, period_key)
        seen.extend(batch)
        offset += len(batch)
        more = period_key in result.truncated_periods

    return seen, state_map


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


class TestStatefulDateOptions:
    def test_second_batch_reuses_existing_iterator(self, monkeypatch):
        states = {}
        result_q = _SimpleQueue()
        created = {"count": 0}
        real_generator = gw.ScheduleGenerator

        class _CountingGenerator(real_generator):
            def __init__(self, *args, **kwargs):
                created["count"] += 1
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(gw, "ScheduleGenerator", _CountingGenerator)

        kwargs = {
            "courses": _date_option_courses(),
            "exam_periods": [_date_option_period()],
            "selected_programs": ["83101"],
            "settings": _settings(),
            "cap": 2,
            "period_key": "FALL - Aleph",
            "offset": 0,
        }

        _run_date_options_from_state(result_q, states, **kwargs)
        first = result_q.get()

        kwargs["offset"] = len(first.schedules_by_period["FALL - Aleph"])
        _run_date_options_from_state(result_q, states, **kwargs)
        second = result_q.get()

        assert created["count"] == 1
        assert first.truncated_periods == {"FALL - Aleph"}
        assert _date_signature(first)
        assert _date_signature(second)

    def test_sequential_batches_have_no_duplicates_or_missing_schedules(self):
        states = {}
        result_q = _SimpleQueue()
        courses = _date_option_courses()
        period = _date_option_period()
        settings = _settings()

        seen: list[tuple] = []
        offset = 0
        more = True
        while more:
            _run_date_options_from_state(
                result_q,
                states,
                courses=courses,
                exam_periods=[period],
                selected_programs=["83101"],
                settings=settings,
                cap=2,
                period_key="FALL - Aleph",
                offset=offset,
            )
            result = result_q.get()
            batch = _date_signature(result)
            seen.extend(batch)
            offset += len(batch)
            more = "FALL - Aleph" in result.truncated_periods

        direct_q = _SimpleQueue()
        _run_generation_process(
            direct_q,
            courses,
            [period],
            ["83101"],
            settings=settings,
            cap=None,
            period_key="FALL - Aleph",
        )
        direct = direct_q.get()

        assert seen == _date_signature(direct)
        assert len(seen) == len(set(seen))
        assert states == {}

    def test_stateful_batches_match_direct_generation_without_thresholds(self):
        courses = _date_option_courses()
        period = _date_option_period()
        settings = _settings()

        seen, states = _collect_stateful_date_signatures(
            courses=courses,
            periods=[period],
            selected_programs=["83101"],
            settings=settings,
            period_key="FALL - Aleph",
            cap=2,
        )
        direct = _direct_generation_result(
            courses=courses,
            periods=[period],
            selected_programs=["83101"],
            settings=settings,
            period_key="FALL - Aleph",
        )

        assert seen == _date_signature(direct)
        assert len(seen) == len(set(seen))
        assert states == {}

    def test_stateful_batches_match_direct_generation_with_thresholds_and_sorting(self):
        courses = _date_option_courses()
        period = _date_option_period(date(2026, 1, 5), date(2026, 1, 8))
        settings = _settings(
            thresholds=ThresholdSettings(
                entries=(ThresholdEntry(Criterion.MAX_EXAMS_PER_DAY, True, 1),)
            ),
            sorting=SortingConfig(
                rules=(SortRule(1, SortCriterion.SORT_MIN_DAYS_MANDATORY),)
            ),
        )

        seen, _states = _collect_stateful_date_signatures(
            courses=courses,
            periods=[period],
            selected_programs=["83101"],
            settings=settings,
            period_key="FALL - Aleph",
            cap=2,
        )
        direct = _direct_generation_result(
            courses=courses,
            periods=[period],
            selected_programs=["83101"],
            settings=settings,
            period_key="FALL - Aleph",
        )

        assert set(seen) == set(_date_signature(direct))
        assert len(seen) == len(set(seen))

    def test_stateful_batches_match_direct_generation_with_feature4_assigned_rooms(self):
        courses = _feature4_courses()
        period = _date_option_period()
        settings = _settings()
        feature4_kwargs = {
            "classrooms": [Classroom("R1", 100)],
            "time_slots": [TimeSlot(dt_time(9, 0))],
            "proctor_config": ProctorConfig(20),
            "allow_unassigned_classrooms": False,
            "classroom_variant_mode": CLASSROOM_VARIANT_MODE_FIRST,
        }

        seen, _states = _collect_stateful_date_signatures(
            courses=courses,
            periods=[period],
            selected_programs=["83101"],
            settings=settings,
            period_key="FALL - Aleph",
            cap=2,
            **feature4_kwargs,
        )
        direct = _direct_generation_result(
            courses=courses,
            periods=[period],
            selected_programs=["83101"],
            settings=settings,
            period_key="FALL - Aleph",
            **feature4_kwargs,
        )

        assert seen == _date_signature(direct)
        assert all(signature[1] for signature in seen)

    def test_stateful_batches_match_direct_generation_with_feature4_unassigned_allowed(self):
        courses = _feature4_courses()
        period = _date_option_period()
        settings = _settings()
        feature4_kwargs = {
            "classrooms": [Classroom("Tiny", 1)],
            "time_slots": [TimeSlot(dt_time(9, 0))],
            "proctor_config": ProctorConfig(20),
            "allow_unassigned_classrooms": True,
            "classroom_variant_mode": CLASSROOM_VARIANT_MODE_FIRST,
        }

        seen, _states = _collect_stateful_date_signatures(
            courses=courses,
            periods=[period],
            selected_programs=["83101"],
            settings=settings,
            period_key="FALL - Aleph",
            cap=2,
            **feature4_kwargs,
        )
        direct = _direct_generation_result(
            courses=courses,
            periods=[period],
            selected_programs=["83101"],
            settings=settings,
            period_key="FALL - Aleph",
            **feature4_kwargs,
        )

        assert seen == _date_signature(direct)
        assert all(signature[2] for signature in seen)

    def test_stateful_date_batches_are_deterministic_across_repeated_runs(self):
        kwargs = {
            "courses": _date_option_courses(),
            "periods": [_date_option_period()],
            "selected_programs": ["83101"],
            "settings": _settings(),
            "period_key": "FALL - Aleph",
            "cap": 2,
        }

        first, _states = _collect_stateful_date_signatures(**kwargs)
        second, _states = _collect_stateful_date_signatures(**kwargs)

        assert first == second

    def test_mismatched_offset_returns_failure(self):
        states = {}
        result_q = _SimpleQueue()
        kwargs = {
            "courses": _date_option_courses(),
            "exam_periods": [_date_option_period()],
            "selected_programs": ["83101"],
            "settings": _settings(),
            "cap": 2,
            "period_key": "FALL - Aleph",
            "offset": 0,
        }

        _run_date_options_from_state(result_q, states, **kwargs)
        result_q.get()

        kwargs["offset"] = 99
        _run_date_options_from_state(result_q, states, **kwargs)
        failure = result_q.get()

        assert not failure.success
        assert "Stale date-options pagination state" in failure.error

    def test_changed_settings_create_new_cursor(self, monkeypatch):
        states = {}
        result_q = _SimpleQueue()
        created = {"count": 0}
        real_generator = gw.ScheduleGenerator

        class _CountingGenerator(real_generator):
            def __init__(self, *args, **kwargs):
                created["count"] += 1
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(gw, "ScheduleGenerator", _CountingGenerator)
        courses = _date_option_courses()
        period = _date_option_period()

        _run_date_options_from_state(
            result_q,
            states,
            courses=courses,
            exam_periods=[period],
            selected_programs=["83101"],
            settings=_settings(),
            cap=1,
            period_key="FALL - Aleph",
            offset=0,
        )
        result_q.get()

        changed_settings = _settings(
            ThresholdSettings(
                entries=(ThresholdEntry(Criterion.MAX_EXAMS_PER_DAY, True, 1),)
            )
        )
        _run_date_options_from_state(
            result_q,
            states,
            courses=courses,
            exam_periods=[period],
            selected_programs=["83101"],
            settings=changed_settings,
            cap=1,
            period_key="FALL - Aleph",
            offset=0,
        )
        result_q.get()

        assert created["count"] == 2

    def test_sorting_only_change_reuses_date_cursor(self, monkeypatch):
        states = {}
        result_q = _SimpleQueue()
        created = {"count": 0}
        real_generator = gw.ScheduleGenerator

        class _CountingGenerator(real_generator):
            def __init__(self, *args, **kwargs):
                created["count"] += 1
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(gw, "ScheduleGenerator", _CountingGenerator)
        courses = _date_option_courses()
        period = _date_option_period()

        _run_date_options_from_state(
            result_q,
            states,
            courses=courses,
            exam_periods=[period],
            selected_programs=["83101"],
            settings=_settings(),
            cap=1,
            period_key="FALL - Aleph",
            offset=0,
        )
        first = result_q.get()
        assert first.success

        sorting_only_settings = _settings(
            sorting=SortingConfig(
                rules=(SortRule(1, SortCriterion.SORT_MIN_DAYS_MANDATORY),)
            )
        )
        _run_date_options_from_state(
            result_q,
            states,
            courses=courses,
            exam_periods=[period],
            selected_programs=["83101"],
            settings=sorting_only_settings,
            cap=1,
            period_key="FALL - Aleph",
            offset=1,
        )
        second = result_q.get()

        assert second.success
        assert created["count"] == 1
        assert len(states) == 1

    def test_independent_periods_keep_independent_cursors(self):
        states = {}
        result_q = _SimpleQueue()
        courses = _date_option_courses()
        periods = [
            _date_option_period(moed="Aleph"),
            _date_option_period(date(2026, 2, 2), date(2026, 2, 4), moed="Bet"),
        ]

        _run_date_options_from_state(
            result_q,
            states,
            courses=courses,
            exam_periods=periods,
            selected_programs=["83101"],
            settings=_settings(),
            cap=1,
            period_key="FALL - Aleph",
            offset=0,
        )
        result_q.get()
        _run_date_options_from_state(
            result_q,
            states,
            courses=courses,
            exam_periods=periods,
            selected_programs=["83101"],
            settings=_settings(),
            cap=1,
            period_key="FALL - Bet",
            offset=0,
        )
        result_q.get()

        assert len(states) == 2

    def test_multiple_period_stateful_batches_match_direct_generation(self):
        states = {}
        courses = _date_option_courses()
        periods = [
            _date_option_period(moed="Aleph"),
            _date_option_period(date(2026, 2, 2), date(2026, 2, 4), moed="Bet"),
        ]
        settings = _settings()

        for period_key in ("FALL - Aleph", "FALL - Bet"):
            seen, states = _collect_stateful_date_signatures(
                courses=courses,
                periods=periods,
                selected_programs=["83101"],
                settings=settings,
                period_key=period_key,
                cap=2,
                states=states,
            )
            direct = _direct_generation_result(
                courses=courses,
                periods=periods,
                selected_programs=["83101"],
                settings=settings,
                period_key=period_key,
            )

            assert seen == _date_signature(direct, period_key)
            assert len(seen) == len(set(seen))

    def test_changed_period_data_replaces_old_cursor_for_same_period_key(self):
        states = {}
        result_q = _SimpleQueue()
        courses = _date_option_courses()

        _run_date_options_from_state(
            result_q,
            states,
            courses=courses,
            exam_periods=[_date_option_period()],
            selected_programs=["83101"],
            settings=_settings(),
            cap=1,
            period_key="FALL - Aleph",
            offset=0,
        )
        result_q.get()

        _run_date_options_from_state(
            result_q,
            states,
            courses=courses,
            exam_periods=[_date_option_period(date(2026, 3, 2), date(2026, 3, 4))],
            selected_programs=["83101"],
            settings=_settings(),
            cap=1,
            period_key="FALL - Aleph",
            offset=0,
        )
        result_q.get()

        assert len(states) == 1

    def test_changed_course_metadata_replaces_old_cursor(self, monkeypatch):
        states = {}
        result_q = _SimpleQueue()
        created = {"count": 0}
        real_generator = gw.ScheduleGenerator

        class _CountingGenerator(real_generator):
            def __init__(self, *args, **kwargs):
                created["count"] += 1
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(gw, "ScheduleGenerator", _CountingGenerator)
        courses = _date_option_courses()

        _run_date_options_from_state(
            result_q,
            states,
            courses=courses,
            exam_periods=[_date_option_period()],
            selected_programs=["83101"],
            settings=_settings(),
            cap=1,
            period_key="FALL - Aleph",
            offset=0,
        )
        result_q.get()

        renamed_courses = _date_option_courses()
        renamed_courses[0].name = "Algorithms Renamed"
        _run_date_options_from_state(
            result_q,
            states,
            courses=renamed_courses,
            exam_periods=[_date_option_period()],
            selected_programs=["83101"],
            settings=_settings(),
            cap=1,
            period_key="FALL - Aleph",
            offset=0,
        )
        result_q.get()

        assert created["count"] == 2

    def test_changed_feature4_inputs_replace_old_cursor(self):
        states = {}
        result_q = _SimpleQueue()
        courses = _date_option_courses()
        period = _date_option_period()

        common = {
            "courses": courses,
            "exam_periods": [period],
            "selected_programs": ["83101"],
            "settings": _settings(),
            "cap": 1,
            "period_key": "FALL - Aleph",
            "offset": 0,
            "time_slots": [TimeSlot(dt_time(9, 0))],
            "proctor_config": ProctorConfig(20),
            "classroom_variant_mode": CLASSROOM_VARIANT_MODE_FIRST,
        }

        _run_date_options_from_state(
            result_q,
            states,
            classrooms=[Classroom("R1", 100)],
            **common,
        )
        result_q.get()
        _run_date_options_from_state(
            result_q,
            states,
            classrooms=[Classroom("R2", 100)],
            **common,
        )
        result_q.get()

        assert len(states) == 1


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
