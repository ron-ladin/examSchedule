"""Unit tests for GenerationPoller multiprocessing lifecycle hardening.

The tests use deterministic fake queues/processes instead of real children for
most cases.  That lets us exercise startup rollback, run identity, reentrancy,
queue failures, protocol validation, exit-code handling, and cleanup without
flaky timing or orphan-process risk.
"""

import os
import queue
import sys
import time
import types
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtCore", exc_type=ImportError)

from PyQt6.QtWidgets import QApplication  # noqa: E402

import src.ui.generation_poller as gp  # noqa: E402
from src.domain.exam_period import ExamPeriod  # noqa: E402
from src.domain.generation_result import GenerationDone, GenerationResult  # noqa: E402
from src.ui.generation_poller import GenerationPoller  # noqa: E402


def _get_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class _FakeController:
    """Minimal controller capturing the calls the poller makes on it."""

    def __init__(
        self,
        periods: list[ExamPeriod] | None = None,
        courses: list | None = None,
    ) -> None:
        self.begin_calls = 0
        self.incremental_batches: list[dict] = []
        self.succeeded_with = None
        self.stale_count = 0
        self.raise_on_cache = False
        self.courses = list(courses or [])
        self.settings = None
        self._periods = list(periods or [])

    def begin_streaming_cache(self) -> None:
        self.begin_calls += 1
        self.incremental_batches.clear()

    def cache_generated_results_incremental(self, partial: dict) -> dict:
        if self.raise_on_cache:
            raise RuntimeError("cache update failed")
        self.incremental_batches.append(partial)
        return partial

    def on_generation_succeeded(self, truncated) -> None:
        self.succeeded_with = set(truncated)

    def mark_results_stale(self) -> None:
        self.stale_count += 1
        self.incremental_batches.clear()

    def get_exam_periods(self) -> list[ExamPeriod]:
        return list(self._periods)

    def engine_classrooms(self) -> list:
        return []

    def engine_time_slots(self) -> list:
        return []

    def engine_proctor_config(self):
        return None


class _FakeProcess:
    """Stand-in for multiprocessing.Process with controllable liveness."""

    _next_pid = 10_000

    def __init__(self, alive: bool = True, exitcode: int | None = None) -> None:
        self._alive = alive
        self.exitcode = exitcode
        self.pid = _FakeProcess._next_pid
        _FakeProcess._next_pid += 1
        self.terminated = 0
        self.killed = 0
        self.join_calls = 0
        self.join_timeouts: list[float | None] = []
        self.stubborn = False

    def is_alive(self) -> bool:
        return self._alive

    def finish(self, exitcode: int = 0) -> None:
        self._alive = False
        self.exitcode = exitcode

    def terminate(self) -> None:
        self.terminated += 1
        if not self.stubborn:
            self.finish(-15)

    def kill(self) -> None:
        self.killed += 1
        self.finish(-9)

    def join(self, timeout=None) -> None:
        self.join_calls += 1
        self.join_timeouts.append(timeout)


class _RecordingProcess(_FakeProcess):
    """Spawn fake that records construction args and start()."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(alive=False, exitcode=None)
        self.construct_args = args
        self.construct_kwargs = kwargs
        self.started = False
        self.fail_start = False
        self.live_counter: dict[str, int] | None = None

    def start(self) -> None:
        if self.fail_start:
            raise RuntimeError("start failed")
        self.started = True
        self._alive = True
        self.exitcode = None
        if self.live_counter is not None:
            self.live_counter["live"] += 1
            self.live_counter["max_live"] = max(
                self.live_counter["max_live"],
                self.live_counter["live"],
            )

    def finish(self, exitcode: int = 0) -> None:
        was_alive = self._alive
        super().finish(exitcode)
        if was_alive and self.live_counter is not None:
            self.live_counter["live"] -= 1


class _FakeMpQueue:
    def __init__(self, maxsize=0):
        self.maxsize = maxsize
        self._q = queue.Queue(maxsize=maxsize)
        self.cancelled = False
        self.closed = False

    def put(self, item):
        self._q.put(item)

    def get_nowait(self):
        return self._q.get_nowait()

    def get(self, timeout=None):
        return self._q.get(timeout=timeout)

    def cancel_join_thread(self):
        self.cancelled = True

    def close(self):
        self.closed = True


class _LateQueue:
    """get_nowait() raises Empty; blocking get() returns queued items."""

    def __init__(self, items) -> None:
        self._items = list(items)
        self.cancelled = False
        self.closed = False

    def get_nowait(self):
        raise queue.Empty

    def get(self, timeout=None):
        if self._items:
            return self._items.pop(0)
        raise queue.Empty

    def cancel_join_thread(self):
        self.cancelled = True

    def close(self):
        self.closed = True


class _RaisingPollQueue(_FakeMpQueue):
    def __init__(self, exc):
        super().__init__(maxsize=2)
        self._exc = exc

    def get_nowait(self):
        raise self._exc


class _ExplodingQueue(_FakeMpQueue):
    def cancel_join_thread(self):
        raise RuntimeError("cancel failed")

    def close(self):
        raise RuntimeError("close failed")


class _ExplodingProcess(_FakeProcess):
    def is_alive(self) -> bool:
        raise RuntimeError("is_alive failed")

    def terminate(self) -> None:
        raise RuntimeError("terminate failed")

    def kill(self) -> None:
        raise RuntimeError("kill failed")

    def join(self, timeout=None) -> None:
        raise RuntimeError("join failed")

    @property
    def exitcode(self):  # type: ignore[override]
        raise RuntimeError("exitcode failed")

    @exitcode.setter
    def exitcode(self, value):  # type: ignore[override]
        self._exitcode = value


class _EventProcess(_FakeProcess):
    def __init__(self, label: str, events: list[tuple], alive: bool = True) -> None:
        super().__init__(alive=alive, exitcode=None if alive else 0)
        self.label = label
        self.events = events

    def terminate(self) -> None:
        self.events.append(("terminate", self.label))
        super().terminate()

    def kill(self) -> None:
        self.events.append(("kill", self.label))
        super().kill()

    def join(self, timeout=None) -> None:
        self.events.append(("join", self.label, timeout))
        super().join(timeout=timeout)


class _Unpicklable:
    def __deepcopy__(self, memo):
        return self

    def __getstate__(self):
        raise TypeError("cannot pickle this")


def _collect(signal) -> list:
    received: list = []
    signal.connect(lambda payload=None: received.append(payload))
    return received


def _period(moed: str, day: int = 5, semester: str = "FALL") -> ExamPeriod:
    return ExamPeriod(
        semester=semester,
        moed=moed,
        date_ranges=[(date(2026, 1, day), date(2026, 1, day))],
    )


def _patch_process_spawning(
    monkeypatch,
    *,
    fail_construct_at: int | None = None,
    fail_start_at: int | None = None,
    live_counter: dict[str, int] | None = None,
):
    created = {"queues": [], "procs": []}

    def fake_queue(maxsize=0):
        q = _FakeMpQueue(maxsize=maxsize)
        created["queues"].append(q)
        return q

    def fake_process(*args, **kwargs):
        index = len(created["procs"]) + 1
        if fail_construct_at == index:
            raise RuntimeError("process construction failed")
        proc = _RecordingProcess(*args, **kwargs)
        proc.fail_start = fail_start_at == index
        proc.live_counter = live_counter
        created["procs"].append(proc)
        return proc

    monkeypatch.setattr(
        gp,
        "worker_context",
        lambda: types.SimpleNamespace(Queue=fake_queue, Process=fake_process),
    )
    return created


def _new_poller(controller: _FakeController | None = None) -> GenerationPoller:
    _get_qapp()
    return GenerationPoller(controller or _FakeController())


def _arm_worker(
    poller: GenerationPoller,
    period_key: str = "FALL - Aleph",
    *,
    alive: bool = True,
    exitcode: int | None = None,
    queue_obj=None,
    process_obj=None,
    started_at: float | None = None,
) -> tuple[int, gp._WorkerState]:
    if poller._active_run_id is None:
        poller._run_sequence += 1
        poller._active_run_id = poller._run_sequence
        poller._start_time = time.monotonic()
    run_id = poller._active_run_id
    assert run_id is not None
    poller._expected_period_keys.add(period_key)
    poller._worker_limit = max(poller._worker_limit, 1)
    process = process_obj or _FakeProcess(alive=alive, exitcode=exitcode)
    state = gp._WorkerState(
        run_id=run_id,
        period_key=period_key,
        queue=queue_obj if queue_obj is not None else _FakeMpQueue(maxsize=2),
        process=process,
        started_at=time.monotonic() if started_at is None else started_at,
    )
    poller._workers[period_key] = state
    poller._set_legacy_refs()
    return run_id, state


@pytest.mark.parametrize(
    "period_count,cpu_count,expected",
    [
        (0, 8, 0),
        (1, 8, 1),
        (10, 8, gp._MAX_PARALLEL_GENERATION_WORKERS),
        (10, 2, 1),
        (10, None, 1),
    ],
)
def test_compute_worker_limit_is_cpu_aware_and_bounded(
    monkeypatch,
    period_count,
    cpu_count,
    expected,
):
    monkeypatch.setattr(gp.os, "cpu_count", lambda: cpu_count)

    assert gp._compute_worker_limit(period_count) == expected


def test_start_spawns_only_bounded_period_workers(monkeypatch):
    periods = [_period("Aleph"), _period("Bet"), _period("Gimel")]
    poller = _new_poller(_FakeController(periods))
    created = _patch_process_spawning(monkeypatch)
    monkeypatch.setattr(gp.os, "cpu_count", lambda: 3)  # cpu budget = 2 workers

    poller.start(["83101"], {"83101": "#005ac2"}, allow_unassigned=False)

    assert len(created["procs"]) == 2
    assert all(proc.started for proc in created["procs"])
    assert len(poller._workers) == 2
    assert [q.maxsize for q in created["queues"]] == [
        gp._PER_WORKER_QUEUE_MAXSIZE,
        gp._PER_WORKER_QUEUE_MAXSIZE,
    ]

    for index, proc in enumerate(created["procs"]):
        assert proc.construct_kwargs["target"] is gp._run_generation_process
        assert proc.construct_kwargs["daemon"] is True
        queue_obj, _courses, worker_periods, _selected = proc.construct_kwargs["args"]
        assert queue_obj is created["queues"][index]
        assert len(worker_periods) == 1
        worker_kwargs = proc.construct_kwargs["kwargs"]
        assert worker_kwargs["stream"] is True
        assert worker_kwargs["cap"] == gp.LOAD_BATCH_SIZE
        assert (
            worker_kwargs["classroom_variant_mode"]
            == gp.CLASSROOM_VARIANT_MODE_FIRST
        )

    poller.stop()


def test_input_periods_start_in_canonical_order(monkeypatch):
    periods = [
        _period("Gimel", semester="SUMM"),
        _period("Bet", semester="FALL"),
        _period("Aleph", semester="SPRI"),
        _period("Aleph", semester="FALL"),
    ]
    poller = _new_poller(_FakeController(periods))
    created = _patch_process_spawning(monkeypatch)
    monkeypatch.setattr(gp.os, "cpu_count", lambda: 8)

    poller.start(["83101"], {}, allow_unassigned=False)

    started_keys = [
        proc.construct_kwargs["args"][2][0].get_key()
        for proc in created["procs"]
    ]
    assert started_keys == [
        "FALL - Aleph",
        "FALL - Bet",
        "SPRI - Aleph",
        "SUMM - Gimel",
    ]
    poller.stop()


def test_duplicate_period_validation_happens_before_spawning(monkeypatch):
    poller = _new_poller(_FakeController([_period("Aleph"), _period("Aleph")]))
    failed = _collect(poller.generation_failed)
    created = _patch_process_spawning(monkeypatch)

    poller.start(["83101"], {}, allow_unassigned=False)

    assert len(failed) == 1
    assert created["procs"] == []


def test_streamed_completion_order_does_not_change_controller_cache_order():
    from src.controller import DesktopController

    ctrl = DesktopController()
    ctrl.begin_streaming_cache()

    ctrl.cache_generated_results_incremental({"SUMM - Gimel": []})
    ctrl.cache_generated_results_incremental({"FALL - Aleph": []})
    ctrl.cache_generated_results_incremental({"SPRI - Bet": []})

    assert list(ctrl._last_results) == [
        "FALL - Aleph",
        "SPRI - Bet",
        "SUMM - Gimel",
    ]


def test_cache_generated_results_returns_canonical_order_for_random_input():
    from src.controller import DesktopController

    ctrl = DesktopController()
    result = ctrl.cache_generated_results(
        {
            "SUMM - Bet": [],
            "FALL - Gimel": [],
            "FALL - Aleph": [],
            "SPRI - Aleph": [],
        }
    )

    assert list(result) == [
        "FALL - Aleph",
        "FALL - Gimel",
        "SPRI - Aleph",
        "SUMM - Bet",
    ]


def test_missing_periods_keep_relative_canonical_order():
    from src.domain.period_order import sort_periods_canonically

    ordered = sort_periods_canonically(
        [
            _period("Bet", semester="SUMM"),
            _period("Gimel", semester="FALL"),
            _period("Aleph", semester="SPRI"),
        ]
    )

    assert [period.get_key() for period in ordered] == [
        "FALL - Gimel",
        "SPRI - Aleph",
        "SUMM - Bet",
    ]


def test_result_tab_merge_uses_full_canonical_standard_order():
    from src.ui.results_panel import _merge_period_keys

    controller = _FakeController([_period("Gimel", semester="SUMM")])

    keys = _merge_period_keys(controller, {"SPRI - Gimel": []})

    assert keys[:9] == [
        "FALL - Aleph",
        "FALL - Bet",
        "FALL - Gimel",
        "SPRI - Aleph",
        "SPRI - Bet",
        "SPRI - Gimel",
        "SUMM - Aleph",
        "SUMM - Bet",
        "SUMM - Gimel",
    ]


def test_period_done_waits_for_process_exit_before_starting_pending(monkeypatch):
    periods = [_period("Aleph"), _period("Bet"), _period("Gimel")]
    counter = {"live": 0, "max_live": 0}
    poller = _new_poller(_FakeController(periods))
    created = _patch_process_spawning(monkeypatch, live_counter=counter)
    monkeypatch.setattr(gp.os, "cpu_count", lambda: 3)  # limit = 2

    poller.start(["83101"], {}, allow_unassigned=False)
    assert len(created["procs"]) == 2

    first_key = periods[0].get_key()
    state = poller._workers[first_key]
    assert poller._consume_worker_message(
        poller._active_run_id,
        state,
        GenerationDone.done({first_key}, period_key=first_key),
    ) is False

    assert len(created["procs"]) == 2, "do not start pending while old PID lives"

    state.process.finish(0)
    poller._check_workers(poller._active_run_id)

    assert len(created["procs"]) == 3
    assert counter["max_live"] == 2
    poller.stop()


def test_period_done_retires_after_exit_and_finalises_once():
    controller = _FakeController()
    poller = _new_poller(controller)
    succeeded = _collect(poller.generation_succeeded)
    run_id, state = _arm_worker(poller, alive=False, exitcode=0)
    poller._got_first_partial = True

    assert poller._consume_worker_message(
        run_id,
        state,
        GenerationDone.done({"FALL - Aleph"}, period_key="FALL - Aleph"),
    ) is True

    assert controller.succeeded_with == {"FALL - Aleph"}
    assert len(succeeded) == 1
    assert poller._workers == {}
    assert poller._queue is None


def test_done_alive_is_cleaned_after_grace_and_result_is_accepted(monkeypatch):
    poller = _new_poller()
    succeeded = _collect(poller.generation_succeeded)
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(poller, alive=True)
    queue_obj = state.queue

    assert poller._consume_worker_message(
        run_id,
        state,
        GenerationDone.done({"FALL - Aleph"}, period_key="FALL - Aleph"),
    ) is False
    assert state.period_key in poller._workers

    done_at = state.done_received_at
    assert done_at is not None
    monkeypatch.setattr(
        gp.time,
        "monotonic",
        lambda: done_at + gp._DONE_EXIT_GRACE_SECS + 0.01,
    )

    poller._check_workers(run_id)

    assert state.process.terminated == 1
    assert state.process.killed == 0
    assert queue_obj.closed is True
    assert failed == []
    assert len(succeeded) == 1
    assert poller._workers == {}


def test_done_stubborn_process_is_killed_after_grace(monkeypatch):
    poller = _new_poller()
    run_id, state = _arm_worker(poller, alive=True)
    state.process.stubborn = True

    poller._consume_worker_message(
        run_id,
        state,
        GenerationDone.done(set(), period_key="FALL - Aleph"),
    )
    done_at = state.done_received_at
    assert done_at is not None
    monkeypatch.setattr(
        gp.time,
        "monotonic",
        lambda: done_at + gp._DONE_EXIT_GRACE_SECS + 0.01,
    )

    poller._check_workers(run_id)

    assert state.process.terminated == 1
    assert state.process.killed == 1
    assert poller._workers == {}


def test_done_forced_cleanup_does_not_emit_duplicate_terminal(monkeypatch):
    poller = _new_poller()
    succeeded = _collect(poller.generation_succeeded)
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(poller, alive=True)

    poller._consume_worker_message(
        run_id,
        state,
        GenerationDone.done(set(), period_key="FALL - Aleph"),
    )
    done_at = state.done_received_at
    assert done_at is not None
    monkeypatch.setattr(
        gp.time,
        "monotonic",
        lambda: done_at + gp._DONE_EXIT_GRACE_SECS + 0.01,
    )

    poller._check_workers(run_id)
    poller._check_workers(run_id)

    assert len(succeeded) == 1
    assert failed == []


def test_lingering_done_worker_does_not_exceed_worker_limit(monkeypatch):
    periods = [_period("Aleph"), _period("Bet"), _period("Gimel")]
    counter = {"live": 0, "max_live": 0}
    poller = _new_poller(_FakeController(periods))
    created = _patch_process_spawning(monkeypatch, live_counter=counter)
    monkeypatch.setattr(gp.os, "cpu_count", lambda: 2)  # limit = 1

    poller.start(["83101"], {}, allow_unassigned=False)
    first_state = poller._workers[periods[0].get_key()]
    poller._consume_worker_message(
        poller._active_run_id,
        first_state,
        GenerationDone.done(set(), period_key=periods[0].get_key()),
    )
    assert len(created["procs"]) == 1

    done_at = first_state.done_received_at
    assert done_at is not None
    monkeypatch.setattr(
        gp.time,
        "monotonic",
        lambda: done_at + gp._DONE_EXIT_GRACE_SECS + 0.01,
    )
    poller._check_workers(poller._active_run_id)

    assert len(created["procs"]) == 2
    assert counter["max_live"] == 1
    poller.stop()


def test_zero_period_finish_emits_empty_scaffold():
    poller = _new_poller()
    ready = _collect(poller.period_ready)
    succeeded = _collect(poller.generation_succeeded)
    poller._run_sequence += 1
    run_id = poller._run_sequence
    poller._active_run_id = run_id

    poller._finish(run_id, set())

    assert poller._controller.begin_calls == 1
    assert len(ready) == 1
    _selected, schedules, _courses, _color_map, _truncated = ready[0]
    assert schedules == {}
    assert len(succeeded) == 1


@pytest.mark.parametrize(
    "fail_kwargs",
    [
        {"fail_start_at": 1},
        {"fail_start_at": 2},
        {"fail_construct_at": 1},
    ],
)
def test_process_startup_failures_roll_back(monkeypatch, fail_kwargs):
    periods = [_period("Aleph"), _period("Bet"), _period("Gimel")]
    poller = _new_poller(_FakeController(periods))
    failed = _collect(poller.generation_failed)
    created = _patch_process_spawning(monkeypatch, **fail_kwargs)
    monkeypatch.setattr(gp.os, "cpu_count", lambda: 8)

    poller.start(["83101"], {}, allow_unassigned=False)

    assert len(failed) == 1
    assert poller._active_run_id is None
    assert poller._workers == {}
    assert poller._pending_periods == []
    assert poller._timer is None
    assert poller._queue is None
    assert all(q.closed for q in created["queues"])
    assert not any(proc.is_alive() for proc in created["procs"])


def test_queue_construction_failure_rolls_back_and_future_run_works(monkeypatch):
    periods = [_period("Aleph")]
    poller = _new_poller(_FakeController(periods))
    failed = _collect(poller.generation_failed)
    should_fail = {"queue": True}
    created = {"queues": [], "procs": []}

    def fake_queue(maxsize=0):
        if should_fail["queue"]:
            raise RuntimeError("queue failed")
        q = _FakeMpQueue(maxsize=maxsize)
        created["queues"].append(q)
        return q

    def fake_process(*args, **kwargs):
        proc = _RecordingProcess(*args, **kwargs)
        created["procs"].append(proc)
        return proc

    monkeypatch.setattr(
        gp,
        "worker_context",
        lambda: types.SimpleNamespace(Queue=fake_queue, Process=fake_process),
    )

    poller.start(["83101"], {}, allow_unassigned=False)
    assert len(failed) == 1
    assert poller._active_run_id is None

    should_fail["queue"] = False
    poller.start(["83101"], {}, allow_unassigned=False)

    assert len(created["procs"]) == 1
    assert created["procs"][0].started is True
    poller.stop()


def test_input_snapshot_survives_controller_mutation_before_pending_start(monkeypatch):
    first = _period("Aleph", 5)
    second = _period("Bet", 6)
    controller = _FakeController([first, second])
    poller = _new_poller(controller)
    created = _patch_process_spawning(monkeypatch)
    monkeypatch.setattr(gp.os, "cpu_count", lambda: 2)  # limit = 1

    poller.start(["83101"], {}, allow_unassigned=False)
    controller._periods[1].moed = "Mutated"

    first_state = poller._workers[first.get_key()]
    first_state.process.finish(0)
    poller._consume_worker_message(
        poller._active_run_id,
        first_state,
        GenerationDone.done(set(), period_key=first.get_key()),
    )

    assert len(created["procs"]) == 2
    _queue, _courses, worker_periods, _selected = created["procs"][1].construct_kwargs["args"]
    assert worker_periods[0].moed == "Bet"
    poller.stop()


def test_unpicklable_worker_payload_fails_without_hanging(monkeypatch):
    poller = _new_poller(_FakeController([_period("Aleph")], courses=[_Unpicklable()]))
    failed = _collect(poller.generation_failed)
    created = _patch_process_spawning(monkeypatch)

    poller.start(["83101"], {}, allow_unassigned=False)

    assert len(failed) == 1
    assert poller._active_run_id is None
    assert created["procs"] == []
    assert created["queues"][0].closed is True


def test_stale_poll_callback_after_restart_is_ignored(monkeypatch):
    poller = _new_poller(_FakeController([_period("Aleph")]))
    _patch_process_spawning(monkeypatch)

    poller.start(["83101"], {}, allow_unassigned=False)
    old_run_id = poller._active_run_id
    poller.stop()
    poller.start(["83101"], {}, allow_unassigned=False)
    new_run_id = poller._active_run_id

    poller._poll(old_run_id)

    assert poller._active_run_id == new_run_id
    assert poller.is_running()
    poller.stop()


def test_late_old_run_messages_do_not_mutate_new_run(monkeypatch):
    poller = _new_poller(_FakeController([_period("Aleph")]))
    ready = _collect(poller.period_ready)
    _patch_process_spawning(monkeypatch)

    poller.start(["83101"], {}, allow_unassigned=False)
    old_run_id = poller._active_run_id
    old_state = next(iter(poller._workers.values()))
    poller.stop()
    poller.start(["83101"], {}, allow_unassigned=False)

    result = GenerationResult.ok({old_state.period_key: []}, {}, set())
    poller._consume_worker_message(old_run_id, old_state, result)
    poller._consume_worker_message(
        old_run_id,
        old_state,
        GenerationDone.done(set(), period_key=old_state.period_key),
    )

    assert ready == []
    assert poller._active_run_id != old_run_id
    poller.stop()


def test_partial_caches_and_emits_period_ready():
    poller = _new_poller()
    ready = _collect(poller.period_ready)
    run_id, state = _arm_worker(poller)
    batch = {"FALL - Aleph": []}

    terminal = poller._consume_worker_message(
        run_id,
        state,
        GenerationResult.ok(batch, {}, set()),
    )

    assert terminal is False
    assert poller._controller.begin_calls == 1
    assert poller._controller.incremental_batches == [batch]
    assert len(ready) == 1


def test_begin_streaming_called_once_across_distinct_period_batches():
    poller = _new_poller()
    run_id, state_a = _arm_worker(poller, "A")
    _run_id, state_b = _arm_worker(poller, "B")

    poller._consume_worker_message(run_id, state_a, GenerationResult.ok({"A": []}, {}, set()))
    poller._consume_worker_message(run_id, state_b, GenerationResult.ok({"B": []}, {}, set()))

    assert poller._controller.begin_calls == 1
    assert poller._got_first_partial is True


def test_period_ready_handler_can_stop_without_later_success():
    poller = _new_poller()
    succeeded = _collect(poller.generation_succeeded)
    run_id, state = _arm_worker(poller)
    poller.period_ready.connect(lambda _payload: poller.stop())

    poller._consume_worker_message(
        run_id,
        state,
        GenerationResult.ok({"FALL - Aleph": []}, {}, set()),
    )

    assert poller._active_run_id is None
    assert succeeded == []
    assert poller._controller.stale_count == 1


def test_period_ready_handler_can_start_new_run(monkeypatch):
    controller = _FakeController([_period("Bet")])
    poller = _new_poller(controller)
    _patch_process_spawning(monkeypatch)
    old_run_id, state = _arm_worker(poller, "FALL - Aleph")
    poller.period_ready.connect(lambda _payload: poller.start(["83101"], {}, False))

    poller._consume_worker_message(
        old_run_id,
        state,
        GenerationResult.ok({"FALL - Aleph": []}, {}, set()),
    )

    assert poller._active_run_id != old_run_id
    assert list(poller._workers) == ["FALL - Bet"]
    poller.stop()


def test_progress_reset_handler_can_start_new_run_before_cache_mutation(monkeypatch):
    controller = _FakeController([_period("Bet")])
    poller = _new_poller(controller)
    _patch_process_spawning(monkeypatch)
    old_run_id, state = _arm_worker(poller, "FALL - Aleph")
    poller.progress_reset.connect(lambda: poller.start(["83101"], {}, False))

    poller._consume_worker_message(
        old_run_id,
        state,
        GenerationResult.ok({"FALL - Aleph": []}, {}, set()),
    )

    assert controller.begin_calls == 0
    assert poller._active_run_id != old_run_id
    poller.stop()


def test_generation_warning_handler_can_stop_before_queue_drain():
    poller = _new_poller()
    ready = _collect(poller.period_ready)
    run_id, state = _arm_worker(poller, alive=True)
    state.queue.put(GenerationResult.ok({"FALL - Aleph": []}, {}, set()))
    poller._start_time = time.monotonic() - (gp._WARN_GEN_SECS + 5)
    poller.generation_warning.connect(lambda _msg: poller.stop())

    poller._poll(run_id)

    assert ready == []
    assert poller._active_run_id is None


def test_generation_succeeded_handler_can_start_new_run(monkeypatch):
    controller = _FakeController([_period("Bet")])
    poller = _new_poller(controller)
    _patch_process_spawning(monkeypatch)
    old_run_id, state = _arm_worker(poller, "FALL - Aleph", alive=False, exitcode=0)
    poller._got_first_partial = True
    poller.generation_succeeded.connect(lambda _payload: poller.start(["83101"], {}, False))

    poller._consume_worker_message(
        old_run_id,
        state,
        GenerationDone.done(set(), period_key="FALL - Aleph"),
    )

    assert poller._active_run_id != old_run_id
    assert list(poller._workers) == ["FALL - Bet"]
    poller.stop()


def test_generation_failed_handler_can_start_new_run(monkeypatch):
    controller = _FakeController([_period("Bet")])
    poller = _new_poller(controller)
    _patch_process_spawning(monkeypatch)
    old_run_id, state = _arm_worker(poller, "FALL - Aleph")
    poller.generation_failed.connect(lambda _msg: poller.start(["83101"], {}, False))

    poller._consume_worker_message(old_run_id, state, object())

    assert poller._active_run_id != old_run_id
    assert list(poller._workers) == ["FALL - Bet"]
    poller.stop()


def test_soft_warning_fires_once_and_does_not_kill():
    poller = _new_poller()
    warnings = _collect(poller.generation_warning)
    run_id, state = _arm_worker(poller, alive=True)
    poller._start_time = time.monotonic() - (gp._WARN_GEN_SECS + 5)

    poller._poll(run_id)
    poller._poll(run_id)

    assert len(warnings) == 1
    assert state.process.killed == 0
    poller.stop()


def test_worker_hard_timeout_terminates_all_workers():
    # Each poll handles one timeout; two polls are needed for two timed-out workers.
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    now = time.monotonic()
    run_id, state_a = _arm_worker(
        poller,
        "A",
        alive=True,
        started_at=now - (gp._HARD_KILL_GEN_SECS + 5),
    )
    _run_id, state_b = _arm_worker(
        poller,
        "B",
        alive=True,
        started_at=now - (gp._HARD_KILL_GEN_SECS + 5),
    )

    poller._poll(run_id)  # drops first timed-out period
    assert failed == []   # run still alive after first drop

    poller._poll(run_id)  # drops second; all periods timed out → fail

    assert len(failed) == 1
    assert state_a.process.terminated == 1
    assert state_b.process.terminated == 1
    assert poller._workers == {}


def test_pending_worker_does_not_consume_timeout_before_start(monkeypatch):
    now = {"value": 0.0}
    monkeypatch.setattr(gp.time, "monotonic", lambda: now["value"])
    monkeypatch.setattr(gp.os, "cpu_count", lambda: 2)  # one worker slot

    first = _period("Aleph")
    second = _period("Bet")
    poller = _new_poller(_FakeController([first, second]))
    created = _patch_process_spawning(monkeypatch)
    failed = _collect(poller.generation_failed)

    poller.start(["83101"], {}, allow_unassigned=False)
    first_state = poller._workers[first.get_key()]

    now["value"] = gp._HARD_KILL_GEN_SECS + 100.0
    first_state.process.finish(0)
    poller._consume_worker_message(
        poller._active_run_id,
        first_state,
        GenerationDone.done(set(), period_key=first.get_key()),
    )

    second_state = poller._workers[second.get_key()]
    assert len(created["procs"]) == 2
    assert second_state.started_at == now["value"]

    poller._poll(poller._active_run_id)

    assert failed == []
    assert second_state.process.terminated == 0
    poller.stop()


def test_late_started_worker_receives_full_hard_timeout(monkeypatch):
    now = {"value": gp._HARD_KILL_GEN_SECS * 3.0}
    monkeypatch.setattr(gp.time, "monotonic", lambda: now["value"])
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(
        poller,
        "FALL - Bet",
        alive=True,
        started_at=now["value"],
    )

    now["value"] += gp._HARD_KILL_GEN_SECS - 1
    poller._poll(run_id)

    assert failed == []
    assert state.process.terminated == 0

    now["value"] += 2
    poller._poll(run_id)

    assert len(failed) == 1
    assert state.process.terminated == 1


def test_timed_out_worker_dropped_while_other_has_budget(monkeypatch):
    # The old worker times out and is dropped; the new worker still has its full
    # budget and the run continues — no failure is emitted.
    now = gp._HARD_KILL_GEN_SECS + 1.0
    monkeypatch.setattr(gp.time, "monotonic", lambda: now)
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    run_id, old_state = _arm_worker(poller, "A", alive=True, started_at=0.0)
    _run_id, new_state = _arm_worker(
        poller,
        "B",
        alive=True,
        started_at=gp._HARD_KILL_GEN_SECS,
    )

    poller._poll(run_id)

    assert failed == []
    assert old_state.process.terminated == 1  # old worker killed
    assert new_state.process.terminated == 0  # new worker untouched
    assert "A" not in poller._workers         # old period retired
    assert "B" in poller._workers             # new period still running
    poller.stop()


def test_multiple_worker_timeouts_emit_one_failure(monkeypatch):
    # Each poll drops one period; all three time out → exactly one failure total.
    now = gp._HARD_KILL_GEN_SECS + 10.0
    monkeypatch.setattr(gp.time, "monotonic", lambda: now)
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    run_id, _state_a = _arm_worker(poller, "A", alive=True, started_at=0.0)
    _run_id, _state_b = _arm_worker(poller, "B", alive=True, started_at=0.0)
    _run_id, _state_c = _arm_worker(poller, "C", alive=True, started_at=0.0)

    poller._poll(run_id)   # drops A
    poller._poll(run_id)   # drops B
    poller._poll(run_id)   # drops C → all timed out → fail

    assert len(failed) == 1
    assert poller._active_run_id is None


def test_timed_out_period_is_dropped_and_run_continues():
    """SCRUM-450 acceptance test: one worker times out, remaining worker finishes,
    success is emitted once, a warning naming the timed-out period is emitted,
    no duplicate terminal signal is produced."""
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    succeeded = _collect(poller.generation_succeeded)
    warnings = _collect(poller.generation_warning)
    now = time.monotonic()

    run_id, slow_state = _arm_worker(
        poller,
        "FALL - Aleph",
        alive=True,
        started_at=now - (gp._HARD_KILL_GEN_SECS + 5),
    )
    _run_id, fast_state = _arm_worker(poller, "FALL - Bet", alive=True)
    fast_state.queue.put(GenerationResult.ok({"FALL - Bet": []}, {}, set()))
    fast_state.queue.put(GenerationDone.done(set(), period_key="FALL - Bet"))
    fast_state.process.finish(0)

    # First poll drains the fast worker's partial and detects the slow timeout.
    poller._poll(run_id)
    assert failed == []
    assert succeeded == []
    assert slow_state.process.terminated == 1

    # Second poll drains the fast worker's Done marker and finalises the run.
    poller._poll(run_id)

    assert failed == []
    assert len(succeeded) == 1
    assert any("FALL - Aleph" in w for w in warnings)
    assert poller._active_run_id is None        # run closed cleanly


def test_all_periods_timed_out_fails_run():
    """When every period times out and no results were produced, fail the run."""
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    succeeded = _collect(poller.generation_succeeded)
    now = time.monotonic()

    run_id, state_a = _arm_worker(
        poller,
        "FALL - Aleph",
        alive=True,
        started_at=now - (gp._HARD_KILL_GEN_SECS + 5),
    )
    _run_id, state_b = _arm_worker(
        poller,
        "FALL - Bet",
        alive=True,
        started_at=now - (gp._HARD_KILL_GEN_SECS + 5),
    )

    poller._poll(run_id)  # drops first period
    poller._poll(run_id)  # drops second → all timed out → fail

    assert succeeded == []
    assert len(failed) == 1
    assert "timed out" in failed[0].lower()
    assert poller._active_run_id is None


def test_draining_is_bounded_per_tick():
    poller = _new_poller()
    ready = _collect(poller.period_ready)
    run_id = None
    total_messages = gp._MAX_DRAIN_PER_TICK + 3
    for i in range(total_messages):
        run_id, state = _arm_worker(poller, f"P{i}", alive=True)
        state.queue.put(GenerationResult.ok({f"P{i}": []}, {}, set()))

    for expected_ready in range(1, total_messages + 1):
        poller._poll(run_id)
        assert len(ready) == expected_ready
    poller.stop()


def test_round_robin_polling_rotates_starting_worker(monkeypatch):
    monkeypatch.setattr(gp, "_MAX_DRAIN_PER_TICK", 1)
    poller = _new_poller()
    ready = _collect(poller.period_ready)
    failed = _collect(poller.generation_failed)
    run_id, state_a = _arm_worker(poller, "A", alive=True)
    _run_id, state_b = _arm_worker(poller, "B", alive=True)
    state_a.queue.put(GenerationResult.ok({"A": []}, {}, set()))
    state_a.queue.put(GenerationDone.done(set(), period_key="A"))
    state_b.queue.put(GenerationResult.ok({"B": []}, {}, set()))

    poller._poll(run_id)
    poller._poll(run_id)

    assert [next(iter(payload[1])) for payload in ready] == ["A", "B"]
    assert failed == []
    poller.stop()


def test_busy_and_quiet_queues_are_both_serviced_before_repeat(monkeypatch):
    monkeypatch.setattr(gp, "_MAX_DRAIN_PER_TICK", 2)
    poller = _new_poller()
    ready = _collect(poller.period_ready)
    run_id, state_a = _arm_worker(poller, "A", alive=True)
    _run_id, state_b = _arm_worker(poller, "B", alive=True)
    state_a.queue.put(GenerationResult.ok({"A": []}, {}, set()))
    state_a.queue.put(GenerationDone.done(set(), period_key="A"))
    state_b.queue.put(GenerationResult.ok({"B": []}, {}, set()))

    poller._poll(run_id)

    assert [next(iter(payload[1])) for payload in ready] == ["A", "B"]
    assert state_a.done_seen is False
    poller.stop()


def test_pending_worker_added_after_retirement_keeps_poll_cursor_valid(monkeypatch):
    monkeypatch.setattr(gp, "_MAX_DRAIN_PER_TICK", 1)
    periods = [_period("Aleph"), _period("Bet")]
    poller = _new_poller(_FakeController(periods))
    _patch_process_spawning(monkeypatch)
    monkeypatch.setattr(gp.os, "cpu_count", lambda: 2)  # limit = 1
    ready = _collect(poller.period_ready)

    poller.start(["83101"], {}, allow_unassigned=False)
    first_state = poller._workers[periods[0].get_key()]
    first_state.process.finish(0)
    first_state.queue.put(
        GenerationDone.done(set(), period_key=periods[0].get_key())
    )

    poller._poll(poller._active_run_id)
    second_state = poller._workers[periods[1].get_key()]
    second_state.queue.put(
        GenerationResult.ok({periods[1].get_key(): []}, {}, set())
    )

    poller._poll(poller._active_run_id)

    assert [next(iter(payload[1])) for payload in ready] == [periods[1].get_key()]
    poller.stop()


@pytest.mark.parametrize("exc", [BrokenPipeError(), EOFError(), OSError(), ValueError()])
def test_queue_polling_errors_fail_safely(exc):
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    run_id, _state = _arm_worker(
        poller,
        queue_obj=_RaisingPollQueue(exc),
        alive=True,
    )

    poller._poll(run_id)

    assert len(failed) == 1
    assert poller._workers == {}
    assert poller._poll_cursor == 0


def test_terminal_marker_in_transit_avoids_false_failure(monkeypatch):
    monkeypatch.setattr(gp, "_FINAL_DRAIN_SECS", 0.01)
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    succeeded = _collect(poller.generation_succeeded)
    run_id, state = _arm_worker(
        poller,
        alive=False,
        exitcode=0,
        queue_obj=_LateQueue([GenerationDone.done(set(), period_key="FALL - Aleph")]),
    )
    poller._got_first_partial = True
    state.dead_ticks = gp._DEAD_TICKS_BEFORE_FAIL - 1

    poller._poll(run_id)

    assert failed == []
    assert len(succeeded) == 1


def test_silent_dead_worker_fails(monkeypatch):
    monkeypatch.setattr(gp, "_FINAL_DRAIN_SECS", 0.01)
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(poller, alive=False, exitcode=0)
    state.dead_ticks = gp._DEAD_TICKS_BEFORE_FAIL - 1

    poller._poll(run_id)

    assert len(failed) == 1
    assert "exited unexpectedly" in failed[0]


def test_partial_without_terminal_marker_fails(monkeypatch):
    monkeypatch.setattr(gp, "_FINAL_DRAIN_SECS", 0.01)
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(poller, alive=True)
    poller._consume_worker_message(
        run_id,
        state,
        GenerationResult.ok({"FALL - Aleph": []}, {}, set()),
    )
    state.process.finish(0)
    state.dead_ticks = gp._DEAD_TICKS_BEFORE_FAIL - 1

    poller._poll(run_id)

    assert len(failed) == 1


def test_nonzero_exit_without_done_fails(monkeypatch):
    monkeypatch.setattr(gp, "_FINAL_DRAIN_SECS", 0.01)
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(poller, alive=False, exitcode=2)
    state.dead_ticks = gp._DEAD_TICKS_BEFORE_FAIL - 1

    poller._poll(run_id)

    assert len(failed) == 1


def test_done_then_nonzero_exit_fails():
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(poller, alive=False, exitcode=7)

    poller._consume_worker_message(
        run_id,
        state,
        GenerationDone.done(set(), period_key="FALL - Aleph"),
    )

    assert len(failed) == 1
    assert poller._workers == {}


@pytest.mark.parametrize(
    "message",
    [
        GenerationResult.ok({"FALL - Aleph": [], "FALL - Bet": []}, {}, set()),
        GenerationResult.ok({"FALL - Bet": []}, {}, set()),
        GenerationResult.ok({"FALL - Aleph": []}, {}, {"FALL - Bet"}),
        GenerationResult(True, schedules_by_period=[], courses_by_id={}, truncated_periods=set()),
        "not-a-dto",
    ],
)
def test_invalid_protocol_messages_fail(message):
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(poller)

    poller._consume_worker_message(run_id, state, message)

    assert len(failed) == 1
    assert poller._workers == {}


def test_duplicate_partial_fails():
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(poller)

    poller._consume_worker_message(
        run_id,
        state,
        GenerationResult.ok({"FALL - Aleph": []}, {}, set()),
    )
    poller._consume_worker_message(
        run_id,
        state,
        GenerationResult.ok({"FALL - Aleph": []}, {}, set()),
    )

    assert len(failed) == 1


def test_done_before_partial_then_partial_fails():
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(poller, alive=True)

    poller._consume_worker_message(
        run_id,
        state,
        GenerationDone.done(set(), period_key="FALL - Aleph"),
    )
    poller._consume_worker_message(
        run_id,
        state,
        GenerationResult.ok({"FALL - Aleph": []}, {}, set()),
    )

    assert len(failed) == 1


def test_duplicate_done_fails():
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(poller, alive=True)

    done = GenerationDone.done(set(), period_key="FALL - Aleph")
    poller._consume_worker_message(run_id, state, done)
    poller._consume_worker_message(run_id, state, done)

    assert len(failed) == 1


def test_failure_after_done_before_exit_is_rejected():
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(poller, alive=True)

    poller._consume_worker_message(
        run_id,
        state,
        GenerationDone.done(set(), period_key="FALL - Aleph"),
    )
    poller._consume_worker_message(
        run_id,
        state,
        GenerationResult.failure("late failure"),
    )

    assert len(failed) == 1


def test_missing_period_key_done_fails():
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(poller)

    poller._consume_worker_message(run_id, state, GenerationDone.done(set()))

    assert len(failed) == 1


def test_old_failure_after_success_does_not_change_new_terminal_result():
    poller = _new_poller()
    succeeded = _collect(poller.generation_succeeded)
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(poller, alive=False, exitcode=0)
    poller._got_first_partial = True

    poller._consume_worker_message(
        run_id,
        state,
        GenerationDone.done(set(), period_key="FALL - Aleph"),
    )
    poller._consume_worker_message(
        run_id,
        state,
        GenerationResult.failure("too late"),
    )

    assert len(succeeded) == 1
    assert failed == []


def test_cache_update_exception_fails_and_cleans_run():
    controller = _FakeController()
    controller.raise_on_cache = True
    poller = _new_poller(controller)
    failed = _collect(poller.generation_failed)
    run_id, state = _arm_worker(poller)

    poller._consume_worker_message(
        run_id,
        state,
        GenerationResult.ok({"FALL - Aleph": []}, {}, set()),
    )

    assert len(failed) == 1
    assert poller._workers == {}
    assert controller.stale_count == 1


def test_failed_run_partials_are_marked_stale_and_next_run_resets_cache(monkeypatch):
    controller = _FakeController([_period("Bet")])
    poller = _new_poller(controller)
    _patch_process_spawning(monkeypatch)
    run_id, state = _arm_worker(poller, "FALL - Aleph")

    poller._consume_worker_message(
        run_id,
        state,
        GenerationResult.ok({"FALL - Aleph": []}, {}, set()),
    )
    poller._consume_worker_message(run_id, state, GenerationResult.failure("boom"))

    assert controller.stale_count == 1
    assert controller.incremental_batches == []

    poller.start(["83101"], {}, allow_unassigned=False)
    new_state = next(iter(poller._workers.values()))
    poller._consume_worker_message(
        poller._active_run_id,
        new_state,
        GenerationResult.ok({"FALL - Bet": []}, {}, set()),
    )

    assert controller.incremental_batches == [{"FALL - Bet": []}]
    poller.stop()


def test_stop_terminates_blocked_or_alive_producer():
    poller = _new_poller()
    _run_id, state = _arm_worker(poller, alive=True)
    state.process.stubborn = True
    queue_obj = state.queue

    poller.stop()

    assert state.process.terminated == 1
    assert state.process.killed == 1
    assert queue_obj.closed is True


def test_complete_run_cleanup_uses_phased_shared_deadline():
    poller = _new_poller()
    events: list[tuple] = []
    processes = []
    queues = []

    for label in ["A", "B", "C", "D"]:
        proc = _EventProcess(label, events, alive=True)
        proc.stubborn = True
        _run_id, state = _arm_worker(
            poller,
            label,
            process_obj=proc,
            queue_obj=_FakeMpQueue(maxsize=2),
        )
        processes.append(proc)
        queues.append(state.queue)

    poller.stop()

    first_kill = next(index for index, event in enumerate(events) if event[0] == "kill")
    assert [event for event in events[:first_kill] if event[0] == "terminate"] == [
        ("terminate", "A"),
        ("terminate", "B"),
        ("terminate", "C"),
        ("terminate", "D"),
    ]
    positive_join_budget = sum(
        timeout or 0
        for proc in processes
        for timeout in proc.join_timeouts
        if timeout
    )
    assert positive_join_budget <= (2 * gp._PROCESS_JOIN_TIMEOUT_SECS) + 0.05
    assert all(queue_obj.closed for queue_obj in queues)


def test_cleanup_kills_only_workers_still_alive_after_terminate():
    poller = _new_poller()
    events: list[tuple] = []
    exiting = _EventProcess("exiting", events, alive=True)
    stubborn = _EventProcess("stubborn", events, alive=True)
    stubborn.stubborn = True
    _arm_worker(poller, "exiting", process_obj=exiting)
    _arm_worker(poller, "stubborn", process_obj=stubborn)

    poller.stop()

    assert exiting.killed == 0
    assert stubborn.killed == 1


def test_timed_out_worker_queue_closes_and_other_queue_stays_open():
    # A times out and is dropped (its queue closed); B still has budget and runs on.
    poller = _new_poller()
    failed = _collect(poller.generation_failed)
    now = time.monotonic()
    run_id, state_a = _arm_worker(
        poller,
        "A",
        alive=True,
        started_at=now - gp._HARD_KILL_GEN_SECS - 1,
    )
    _run_id, state_b = _arm_worker(
        poller,
        "B",
        alive=True,
        started_at=now,
    )
    queue_a = state_a.queue
    queue_b = state_b.queue

    poller._poll(run_id)

    assert failed == []          # run still alive — B is still working
    assert queue_a.closed is True   # timed-out worker's queue released
    assert queue_b.closed is False  # continuing worker's queue intact
    poller.stop()


def test_every_queue_closes_after_restart(monkeypatch):
    poller = _new_poller(_FakeController([_period("Aleph")]))
    _patch_process_spawning(monkeypatch)

    poller.start(["83101"], {}, allow_unassigned=False)
    old_state = next(iter(poller._workers.values()))
    old_queue = old_state.queue

    poller.start(["83101"], {}, allow_unassigned=False)

    assert old_queue.closed is True
    poller.stop()


def test_repeated_cleanup_is_idempotent():
    poller = _new_poller()
    _run_id, state = _arm_worker(poller, alive=True)
    queue_obj = state.queue

    poller.stop()
    poller.stop()
    poller._cleanup_run_resources(terminate=True)

    assert queue_obj.closed is True
    assert poller._workers == {}


def test_cleanup_exceptions_do_not_prevent_remaining_cleanup():
    poller = _new_poller()
    run_id, state_a = _arm_worker(
        poller,
        "A",
        queue_obj=_ExplodingQueue(maxsize=2),
        alive=True,
    )
    state_a.process = _ExplodingProcess(alive=True)
    _run_id, state_b = _arm_worker(poller, "B", alive=True)
    queue_b = state_b.queue

    poller._fail(run_id, "forced failure")

    assert poller._workers == {}
    assert queue_b.closed is True
    assert state_b.process.terminated == 1


def test_repeated_lifecycle_leaves_no_tracked_resources(monkeypatch):
    periods = [_period("Aleph")]
    poller = _new_poller(_FakeController(periods))
    created = _patch_process_spawning(monkeypatch)

    poller.start(["83101"], {}, allow_unassigned=False)
    first_state = next(iter(poller._workers.values()))
    first_state.process.finish(0)
    poller._consume_worker_message(
        poller._active_run_id,
        first_state,
        GenerationDone.done(set(), period_key=first_state.period_key),
    )
    assert poller._workers == {}
    assert poller._pending_periods == []
    assert poller._queue is None

    poller.start(["83101"], {}, allow_unassigned=False)
    poller.stop()
    assert poller._workers == {}
    assert poller._pending_periods == []
    assert poller._queue is None

    created["procs"].clear()
    created["queues"].clear()
    fake_queue = gp.worker_context().Queue
    monkeypatch.setattr(
        gp,
        "worker_context",
        lambda: types.SimpleNamespace(
            Queue=fake_queue,
            Process=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        ),
    )
    failed = _collect(poller.generation_failed)
    poller.start(["83101"], {}, allow_unassigned=False)

    assert len(failed) == 1
    assert poller._workers == {}
    assert poller._pending_periods == []
    assert poller._queue is None


def test_input_screen_shutdown_hook_stops_generation_and_load_workers():
    from src.ui.input_screen import InputScreen

    calls: list[str] = []

    class _Config:
        def shutdown_background_workers(self):
            calls.append("generation")

    class _Controller:
        def shutdown_load_workers(self):
            calls.append("load_more")

    screen = type(
        "_InputScreenDouble",
        (),
        {"_config": _Config(), "_controller": _Controller()},
    )()

    InputScreen.shutdown_background_workers(screen)

    assert calls == ["generation", "load_more"]
