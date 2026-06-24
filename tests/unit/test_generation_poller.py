"""
Unit tests for GenerationPoller (SCRUM-393 streaming generation).

These exercise the message-draining state machine WITHOUT spawning a real
subprocess: a plain in-process queue stands in for the multiprocessing queue and
a tiny fake controller/process capture the calls the poller makes. Covered:

- terminal ``GenerationDone`` finalises the run and emits the 3-tuple succeeded
  signal;
- a successful partial caches + emits ``period_ready`` and gates
  ``begin_streaming_cache`` to the first batch only;
- an unexpected/invalid message reports a failure;
- the zero-period finish path still emits an empty scaffold and succeeds;
- the soft 180s warning fires exactly once and never kills the process;
- the hard backstop kills a runaway worker and fails;
- per-tick draining is bounded (fast producer cannot block the event loop);
- a terminal marker still in transit after the worker exits is drained instead
  of being reported as an unexpected exit, while a truly silent exit fails.

GUI-only (QObject/pyqtSignal), so skipped when PyQt6 is not installed.
"""

import os
import queue
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtCore", exc_type=ImportError)

from PyQt6.QtWidgets import QApplication  # noqa: E402

import src.ui.generation_poller as gp  # noqa: E402
from src.domain.generation_result import GenerationDone, GenerationResult  # noqa: E402
from src.ui.generation_poller import GenerationPoller  # noqa: E402


def _get_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class _FakeController:
    """Minimal controller capturing the calls the poller makes on it."""

    def __init__(self) -> None:
        self.begin_calls = 0
        self.incremental_batches: list[dict] = []
        self.succeeded_with = None

    def begin_streaming_cache(self) -> None:
        self.begin_calls += 1

    def cache_generated_results_incremental(self, partial: dict) -> dict:
        self.incremental_batches.append(partial)
        return partial  # echo back as the "sorted" batch

    def on_generation_succeeded(self, truncated) -> None:
        self.succeeded_with = truncated


class _FakeProcess:
    """Stand-in for multiprocessing.Process with controllable liveness."""

    def __init__(self, alive: bool = True) -> None:
        self._alive = alive
        self.kill_count = 0

    def is_alive(self) -> bool:
        return self._alive

    def kill(self) -> None:
        self.kill_count += 1
        self._alive = False


class _LateQueue:
    """get_nowait() always raises Empty; get(timeout) returns queued items.

    Simulates a terminal marker still being flushed by the queue feeder thread:
    visible only to the blocking get, not to a non-blocking get_nowait.
    """

    def __init__(self, items) -> None:
        self._items = list(items)

    def get_nowait(self):
        raise queue.Empty

    def get(self, timeout=None):
        if self._items:
            return self._items.pop(0)
        raise queue.Empty


@pytest.fixture
def poller() -> GenerationPoller:
    _get_qapp()
    p = GenerationPoller(_FakeController())
    p._queue = queue.Queue()
    p._start_time = time.monotonic()  # fresh run; tests opt into timeouts explicitly
    return p


def _collect(signal) -> list:
    received: list = []
    signal.connect(lambda payload: received.append(payload))
    return received


def test_done_marker_finalises_run(poller):
    succeeded = _collect(poller.generation_succeeded)
    poller._got_first_partial = True  # partials already streamed

    terminal = poller._consume(GenerationDone.done({"FALL - Aleph"}))

    assert terminal is True
    assert poller._controller.succeeded_with == {"FALL - Aleph"}
    assert len(succeeded) == 1
    _selected, _color_map, truncated = succeeded[0]
    assert truncated == {"FALL - Aleph"}


def test_partial_caches_and_emits_period_ready(poller):
    ready = _collect(poller.period_ready)
    batch = {"FALL - Aleph": []}

    terminal = poller._consume(GenerationResult.ok(batch, {}, set()))

    assert terminal is False
    assert poller._controller.begin_calls == 1
    assert poller._controller.incremental_batches == [batch]
    assert len(ready) == 1


def test_begin_streaming_called_once_across_batches(poller):
    poller._handle_partial(GenerationResult.ok({"A": []}, {}, set()))
    poller._handle_partial(GenerationResult.ok({"B": []}, {}, set()))

    assert poller._controller.begin_calls == 1
    assert poller._got_first_partial is True


def test_unexpected_message_reports_failure(poller):
    failed = _collect(poller.generation_failed)

    terminal = poller._consume("garbage-not-a-result")

    assert terminal is True
    assert len(failed) == 1


def test_zero_period_finish_emits_empty_scaffold(poller):
    ready = _collect(poller.period_ready)
    succeeded = _collect(poller.generation_succeeded)
    assert poller._got_first_partial is False

    poller._finish(set())

    assert poller._got_first_partial is True
    assert poller._controller.begin_calls == 1
    assert len(ready) == 1
    _selected, schedules, _courses, _color_map, _truncated = ready[0]
    assert schedules == {}
    assert len(succeeded) == 1


def test_soft_warning_fires_once_and_does_not_kill(poller):
    warnings = _collect(poller.generation_warning)
    proc = _FakeProcess(alive=True)
    poller._process = proc
    poller._start_time = time.monotonic() - (gp._WARN_GEN_SECS + 5)

    poller._poll()
    poller._poll()

    assert len(warnings) == 1
    assert poller._warned is True
    assert proc.kill_count == 0  # soft warning never kills


def test_hard_backstop_kills_runaway_worker(poller):
    failed = _collect(poller.generation_failed)
    proc = _FakeProcess(alive=True)
    poller._process = proc
    poller._start_time = time.monotonic() - (gp._HARD_KILL_GEN_SECS + 5)

    poller._poll()

    assert proc.kill_count == 1
    assert len(failed) == 1
    assert "timed out" in failed[0]


def test_draining_is_bounded_per_tick(poller):
    ready = _collect(poller.period_ready)
    poller._process = _FakeProcess(alive=True)
    extra = 3
    for i in range(gp._MAX_DRAIN_PER_TICK + extra):
        poller._queue.put(GenerationResult.ok({f"P{i}": []}, {}, set()))

    poller._poll()
    assert len(ready) == gp._MAX_DRAIN_PER_TICK  # capped this tick

    poller._poll()
    assert len(ready) == gp._MAX_DRAIN_PER_TICK + extra  # rest on next tick


def test_terminal_marker_in_transit_avoids_false_failure(poller):
    failed = _collect(poller.generation_failed)
    succeeded = _collect(poller.generation_succeeded)
    poller._got_first_partial = True
    poller._process = _FakeProcess(alive=False)
    poller._queue = _LateQueue([GenerationDone.done(set())])
    poller._dead_ticks = gp._DEAD_TICKS_BEFORE_FAIL - 1

    poller._poll()

    assert failed == []
    assert len(succeeded) == 1


def test_silent_dead_worker_fails(poller, monkeypatch):
    monkeypatch.setattr(gp, "_FINAL_DRAIN_SECS", 0.01)  # keep the blocking drain short
    failed = _collect(poller.generation_failed)
    poller._process = _FakeProcess(alive=False)
    poller._dead_ticks = gp._DEAD_TICKS_BEFORE_FAIL - 1

    poller._poll()

    assert len(failed) == 1
    assert "exited unexpectedly" in failed[0]
