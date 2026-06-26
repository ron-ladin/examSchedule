"""
GenerationPoller - background generation process lifecycle.

Owns the subprocesses, per-worker result queues, and QTimer so ConfigScreen
stays focused on UI construction and state changes only.
"""

from __future__ import annotations

import copy
import logging
import multiprocessing
import os
import pickle
import time
from dataclasses import dataclass
from queue import Empty as _QueueEmpty
from typing import Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from src.controller import (
    DesktopController,
    LOAD_BATCH_SIZE,
    _run_generation_process,
)
from src.domain.generation_result import GenerationDone, GenerationResult
from src.domain.period_order import sort_periods_canonically
from src.engine.app_controller import CLASSROOM_VARIANT_MODE_FIRST

logger = logging.getLogger(__name__)

# Soft threshold: after this many seconds the user is warned once that
# generation is taking a while. It does NOT kill the process - generation
# continues until it finishes on its own (see SCRUM-393).
_WARN_GEN_SECS = 180

# Hard backstop: the soft warning never kills the worker, but a genuinely hung
# or runaway process (deadlock, infinite loop) would otherwise keep the UI in
# the "still working..." state forever. After this much longer ceiling we stop
# every worker so the UI can recover.
_HARD_KILL_GEN_SECS = 15 * 60

# Cap how many queued messages a single timer tick drains. A fast producer can
# enqueue several period messages between 150 ms ticks; processing them all in
# one callback (each triggers a sort + card rebuild) can freeze the Qt event
# loop. Remaining messages are picked up on the next tick.
_MAX_DRAIN_PER_TICK = 5

# Consecutive ticks with a worker not alive and its queue empty before we
# declare an unexpected exit.
_DEAD_TICKS_BEFORE_FAIL = 5

# When a worker has exited but the queue looks empty, block this long for a
# terminal marker still in transit through the queue feeder thread before
# reporting a false unexpected exit.
_FINAL_DRAIN_SECS = 0.5

_MAX_PARALLEL_GENERATION_WORKERS = 4

# Per-period streaming workers normally produce either:
#   GenerationResult.ok(period P), GenerationDone(period P)
# or:
#   GenerationDone(period P)
# or:
#   GenerationResult.failure(...)
# A maxsize of two admits the normal success protocol without unbounded IPC RAM.
_PER_WORKER_QUEUE_MAXSIZE = 2

_PROCESS_JOIN_TIMEOUT_SECS = 0.2

# A worker that has sent a valid GenerationDone has completed the protocol from
# the parent's perspective. Give it a short chance to exit normally, then accept
# the period result and forcibly clean the lingering process so it cannot hold a
# worker slot until the hard timeout.
_DONE_EXIT_GRACE_SECS = 1.0


def _compute_worker_limit(period_count: int) -> int:
    if period_count <= 0:
        return 0

    logical_cpu_count = os.cpu_count()
    if logical_cpu_count is None:
        logical_cpu_count = 2

    cpu_worker_budget = max(1, logical_cpu_count - 1)

    return min(
        period_count,
        _MAX_PARALLEL_GENERATION_WORKERS,
        cpu_worker_budget,
    )


@dataclass
class _WorkerState:
    """Main-process state for one exam-period worker."""

    run_id: int
    period_key: str
    queue: Any
    process: Any | None = None
    started_at: float = 0.0
    partial_seen: bool = False
    done_seen: bool = False
    done_received_at: float | None = None
    dead_ticks: int = 0


class GenerationPoller(QObject):
    """Manages bounded parallel period-generation workers."""

    period_ready = pyqtSignal(object)           # one streamed period batch tuple
    generation_succeeded = pyqtSignal(object)   # terminal: generation finished
    generation_failed = pyqtSignal(str)         # error message
    generation_warning = pyqtSignal(str)        # non-fatal slow-generation notice
    progress_reset = pyqtSignal()               # tell parent to hide progress bar

    def __init__(self, controller: DesktopController, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller

        # Backward-compatible public-ish slots used by older tests/callers.
        self._process: multiprocessing.Process | None = None
        self._processes: dict[str, multiprocessing.Process] = {}
        self._queue: multiprocessing.Queue | None = None

        self._timer: QTimer | None = None
        self._start_time: float = 0.0
        self._warned: bool = False
        self._got_first_partial: bool = False

        self._run_sequence: int = 0
        self._active_run_id: int | None = None
        self._workers: dict[str, _WorkerState] = {}

        self._pending_selected: list[str] = []
        self._pending_color_map: dict[str, str] = {}
        self._pending_periods: list = []
        self._courses_snapshot: list = []
        self._settings_snapshot = None
        self._classrooms_snapshot: list = []
        self._time_slots_snapshot: list = []
        self._proctor_config_snapshot = None
        self._allow_unassigned_snapshot: bool = False
        self._worker_limit: int = 0
        self._expected_period_keys: set[str] = set()
        self._completed_periods: set[str] = set()
        self._truncated_periods: set[str] = set()
        self._poll_cursor: int = 0

    def is_running(self) -> bool:
        if self._active_run_id is None:
            return False

        for state in list(self._workers.values()):
            alive = self._process_is_alive(state)
            if alive is not False:
                return True

        return bool(self._workers or self._pending_periods)

    def start(
        self,
        selected: list[str],
        color_map: dict[str, str],
        allow_unassigned: bool,
    ) -> None:
        """Start a new generation run, replacing any older active run."""
        replacing_active_run = self._active_run_id is not None or bool(self._workers)
        self._cleanup_existing_run(mark_stale=replacing_active_run)

        self._run_sequence += 1
        run_id = self._run_sequence
        self._active_run_id = run_id

        self._start_time = time.monotonic()
        self._warned = False
        self._got_first_partial = False
        self._pending_selected = list(selected)
        self._pending_color_map = dict(color_map)
        self._pending_periods = []
        self._workers = {}
        self._expected_period_keys = set()
        self._completed_periods = set()
        self._truncated_periods = set()
        self._poll_cursor = 0
        self._set_legacy_refs()

        try:
            periods = list(self._controller.get_exam_periods())
            period_keys: list[str] = []
            duplicate_keys: set[str] = set()
            for period in periods:
                key = period.get_key()
                if key in period_keys:
                    duplicate_keys.add(key)
                period_keys.append(key)

            if duplicate_keys:
                self._fail(
                    run_id,
                    "Duplicate exam period found: "
                    + ", ".join(sorted(duplicate_keys)),
                )
                return

            # Course and ExamPeriod objects are mutable in the UI/editor layer.
            # Snapshot them once so delayed pending workers cannot observe
            # mid-generation edits. Settings/classroom/time-slot/proctor DTOs are
            # immutable value objects in this repository, so list snapshots are
            # enough for those collections.
            self._courses_snapshot = copy.deepcopy(self._controller.courses)
            self._pending_periods = sort_periods_canonically(copy.deepcopy(periods))
            self._settings_snapshot = self._controller.settings
            self._classrooms_snapshot = list(self._controller.engine_classrooms())
            self._time_slots_snapshot = list(self._controller.engine_time_slots())
            self._proctor_config_snapshot = self._controller.engine_proctor_config()
            self._allow_unassigned_snapshot = bool(allow_unassigned)
            self._expected_period_keys = set(period_keys)
            self._worker_limit = _compute_worker_limit(len(period_keys))

            logger.info(
                "Generation run %s starting: periods=%s worker_limit=%s",
                run_id,
                len(period_keys),
                self._worker_limit,
            )

            if self._worker_limit == 0:
                self._finish(run_id, set())
                return

            if not self._start_next_workers(run_id):
                return

            if not self._is_current_run(run_id):
                return

            self._timer = QTimer(self)
            self._timer.timeout.connect(lambda run_id=run_id: self._poll(run_id))
            self._timer.start(150)
        except Exception:
            logger.exception("Generation run %s failed during startup", run_id)
            self._fail(
                run_id,
                "Generation failed to start. Please check the input files and try again.",
            )

    def stop(self) -> None:
        """Cancel the active run without emitting success or failure."""
        run_id = self._active_run_id
        if run_id is None and not self._workers:
            self._stop_timer()
            return

        logger.info("Generation run %s stopped", run_id)
        self._active_run_id = None
        self._run_sequence += 1
        self._stop_timer()
        if self._got_first_partial:
            self._mark_results_stale()
        self._cleanup_run_resources(terminate=True)
        self._clear_run_state(clear_signals=False)

    def _is_current_run(self, run_id: int | None) -> bool:
        return run_id is not None and self._active_run_id == run_id

    def _cleanup_existing_run(self, mark_stale: bool) -> None:
        if mark_stale and self._got_first_partial:
            self._mark_results_stale()
        self._active_run_id = None
        self._stop_timer()
        self._cleanup_run_resources(terminate=True)
        self._clear_run_state(clear_signals=False)

    def _clear_run_state(self, clear_signals: bool) -> None:
        self._workers.clear()
        self._pending_periods.clear()
        self._completed_periods.clear()
        self._expected_period_keys.clear()
        self._truncated_periods.clear()
        self._poll_cursor = 0
        self._courses_snapshot = []
        self._settings_snapshot = None
        self._classrooms_snapshot = []
        self._time_slots_snapshot = []
        self._proctor_config_snapshot = None
        self._worker_limit = 0
        self._set_legacy_refs()
        if clear_signals:
            self._pending_selected = []
            self._pending_color_map = {}

    def _stop_timer(self) -> None:
        timer = self._timer
        self._timer = None
        if timer is None:
            return
        try:
            timer.stop()
        except Exception:
            logger.debug("Failed stopping generation timer", exc_info=True)
        try:
            timer.deleteLater()
        except Exception:
            logger.debug("Failed deleting generation timer", exc_info=True)

    def _cleanup_run_resources(self, terminate: bool) -> None:
        states = list(self._workers.values())
        if terminate:
            self._terminate_live_workers(states)
            self._join_workers_with_shared_deadline(
                states,
                _PROCESS_JOIN_TIMEOUT_SECS,
            )
            self._kill_live_workers(states)
            self._join_workers_with_shared_deadline(
                states,
                _PROCESS_JOIN_TIMEOUT_SECS,
            )
        else:
            for state in states:
                self._join_worker_once(state, timeout=0)

        for state in states:
            self._join_worker_once(state, timeout=0)
            self._log_worker_reaped(state)
            self._close_worker_queue(state)

        self._workers.clear()
        self._poll_cursor = 0
        self._set_legacy_refs()

    def _terminate_live_workers(self, states: list[_WorkerState]) -> None:
        for state in states:
            proc = state.process
            if proc is None or not self._cleanup_process_is_alive(proc):
                continue
            try:
                logger.info(
                    "Terminating generation worker: run=%s period=%s pid=%s",
                    state.run_id,
                    state.period_key,
                    getattr(proc, "pid", None),
                )
                proc.terminate()
            except Exception:
                logger.debug("Failed terminating generation worker", exc_info=True)

    def _kill_live_workers(self, states: list[_WorkerState]) -> None:
        for state in states:
            proc = state.process
            if proc is None or not self._cleanup_process_is_alive(proc):
                continue
            try:
                logger.info(
                    "Killing generation worker: run=%s period=%s pid=%s",
                    state.run_id,
                    state.period_key,
                    getattr(proc, "pid", None),
                )
                proc.kill()
            except Exception:
                logger.debug("Failed killing generation worker", exc_info=True)

    def _join_workers_with_shared_deadline(
        self,
        states: list[_WorkerState],
        timeout: float,
    ) -> None:
        live_states = [
            state
            for state in states
            if state.process is not None
            and self._cleanup_process_is_alive(state.process)
        ]
        if not live_states:
            return

        slice_timeout = max(0.0, timeout) / len(live_states)
        for state in live_states:
            self._join_worker_once(state, timeout=slice_timeout)

    def _join_worker_once(self, state: _WorkerState, timeout: float) -> None:
        proc = state.process
        if proc is None:
            return
        try:
            proc.join(timeout=timeout)
        except Exception:
            logger.debug("Failed joining generation worker", exc_info=True)

    def _log_worker_reaped(self, state: _WorkerState) -> None:
        proc = state.process
        if proc is None:
            return
        try:
            logger.info(
                "Generation worker reaped: run=%s period=%s pid=%s exitcode=%s",
                state.run_id,
                state.period_key,
                getattr(proc, "pid", None),
                getattr(proc, "exitcode", None),
            )
        except Exception:
            logger.debug("Failed reading generation worker exitcode", exc_info=True)

    def _close_worker_queue(self, state: _WorkerState) -> None:
        queue_obj = state.queue
        if queue_obj is None:
            return
        try:
            queue_obj.cancel_join_thread()
        except Exception:
            logger.debug("Failed cancelling generation queue join thread", exc_info=True)
        try:
            queue_obj.close()
            logger.info(
                "Generation queue closed: run=%s period=%s",
                state.run_id,
                state.period_key,
            )
        except Exception:
            logger.debug("Failed closing generation queue", exc_info=True)
        state.queue = None

    def _cleanup_worker_resources(
        self,
        state: _WorkerState,
        terminate: bool,
    ) -> None:
        proc = state.process
        if proc is not None:
            alive = self._cleanup_process_is_alive(proc)

            if terminate and alive:
                try:
                    logger.info(
                        "Terminating generation worker: run=%s period=%s pid=%s",
                        state.run_id,
                        state.period_key,
                        getattr(proc, "pid", None),
                    )
                    proc.terminate()
                except Exception:
                    logger.debug("Failed terminating generation worker", exc_info=True)

            self._join_worker_once(
                state,
                timeout=_PROCESS_JOIN_TIMEOUT_SECS if terminate else 0,
            )

            alive = self._cleanup_process_is_alive(proc)
            if terminate and alive:
                try:
                    logger.info(
                        "Killing generation worker: run=%s period=%s pid=%s",
                        state.run_id,
                        state.period_key,
                        getattr(proc, "pid", None),
                    )
                    proc.kill()
                except Exception:
                    logger.debug("Failed killing generation worker", exc_info=True)
                self._join_worker_once(state, timeout=_PROCESS_JOIN_TIMEOUT_SECS)

            self._log_worker_reaped(state)

        self._close_worker_queue(state)

    def _cleanup_process_is_alive(self, proc) -> bool:
        try:
            return bool(proc.is_alive())
        except Exception:
            logger.debug("Failed checking generation worker liveness", exc_info=True)
            # Try terminate/kill anyway when cleanup requested.
            return True

    def _process_is_alive(self, state: _WorkerState) -> bool | None:
        if state.process is None:
            return False
        try:
            return bool(state.process.is_alive())
        except Exception:
            logger.exception(
                "Could not inspect generation worker liveness: run=%s period=%s",
                state.run_id,
                state.period_key,
            )
            return None

    def _set_legacy_refs(self) -> None:
        self._processes = {
            period_key: state.process
            for period_key, state in self._workers.items()
            if state.process is not None
        }
        self._process = next(iter(self._processes.values()), None)
        self._queue = next(
            (state.queue for state in self._workers.values() if state.queue is not None),
            None,
        )

    def _start_next_workers(self, run_id: int) -> bool:
        if not self._is_current_run(run_id):
            return False

        while (
            self._pending_periods
            and len(self._workers) < self._worker_limit
            and self._is_current_run(run_id)
        ):
            period = self._pending_periods.pop(0)
            try:
                state = self._start_worker(run_id, period)
            except Exception:
                logger.exception("Generation worker startup failed: run=%s", run_id)
                self._fail(
                    run_id,
                    "Generation worker failed to start. Please try again.",
                )
                return False

            self._workers[state.period_key] = state
            self._set_legacy_refs()

        return self._is_current_run(run_id)

    def _start_worker(self, run_id: int, period) -> _WorkerState:
        period_key = period.get_key()
        queue_obj = None
        process = None
        state: _WorkerState | None = None

        try:
            logger.info(
                "Creating generation worker: run=%s period=%s",
                run_id,
                period_key,
            )
            queue_obj = multiprocessing.Queue(maxsize=_PER_WORKER_QUEUE_MAXSIZE)

            args = (
                queue_obj,
                list(self._courses_snapshot),
                [period],
                list(self._pending_selected),
            )
            kwargs = {
                "settings": self._settings_snapshot,
                "cap": LOAD_BATCH_SIZE,
                "classrooms": list(self._classrooms_snapshot),
                "time_slots": list(self._time_slots_snapshot),
                "proctor_config": self._proctor_config_snapshot,
                "allow_unassigned_classrooms": self._allow_unassigned_snapshot,
                "classroom_variant_mode": CLASSROOM_VARIANT_MODE_FIRST,
                "stream": True,
            }
            self._assert_worker_payload_picklable(period_key, args[1:], kwargs)

            process = multiprocessing.Process(
                target=_run_generation_process,
                args=args,
                kwargs=kwargs,
                daemon=True,
            )
            state = _WorkerState(
                run_id=run_id,
                period_key=period_key,
                queue=queue_obj,
                process=process,
            )
            process.start()
            # Timeout budget starts only after the OS accepts this worker start;
            # pending periods do not consume any hard-timeout budget.
            state.started_at = time.monotonic()

            logger.info(
                "Generation worker started: run=%s period=%s pid=%s",
                run_id,
                period_key,
                getattr(process, "pid", None),
            )
            return state
        except Exception:
            if state is None:
                state = _WorkerState(
                    run_id=run_id,
                    period_key=period_key,
                    queue=queue_obj,
                    process=process,
                )
            self._cleanup_worker_resources(state, terminate=True)
            raise

    def _assert_worker_payload_picklable(
        self,
        period_key: str,
        worker_args_without_queue,
        worker_kwargs: dict,
    ) -> None:
        try:
            pickle.dumps((worker_args_without_queue, worker_kwargs))
        except Exception as exc:
            raise TypeError(
                f"Generation worker payload for {period_key} is not picklable."
            ) from exc

    def _poll(self, run_id: int | None = None) -> None:
        if run_id is None:
            run_id = self._active_run_id
        if not self._is_current_run(run_id):
            logger.debug("Ignoring stale generation poll callback: run=%s", run_id)
            return

        now = time.monotonic()
        elapsed = int(now - self._start_time)

        if elapsed > _WARN_GEN_SECS and not self._warned:
            self._warned = True
            logger.warning("Generation run %s exceeded %ss", run_id, _WARN_GEN_SECS)
            self.generation_warning.emit(
                f"Generation is taking longer than {_WARN_GEN_SECS // 60} minutes - "
                "still working..."
            )
            if not self._is_current_run(run_id):
                return

        if self._drain_worker_queues(run_id):
            return

        if self._check_worker_timeouts(run_id, time.monotonic()):
            return

        self._check_workers(run_id)

    def _drain_worker_queues(self, run_id: int) -> bool:
        drained = 0

        try:
            while drained < _MAX_DRAIN_PER_TICK and self._is_current_run(run_id):
                got_message = False

                for state in self._worker_states_for_poll():
                    if drained >= _MAX_DRAIN_PER_TICK:
                        break
                    if state.run_id != run_id or state.queue is None:
                        continue

                    try:
                        result = state.queue.get_nowait()
                    except _QueueEmpty:
                        continue
                    except (BrokenPipeError, EOFError, OSError, ValueError):
                        logger.exception(
                            "Generation queue failed while polling: run=%s period=%s",
                            run_id,
                            state.period_key,
                        )
                        self._fail(
                            run_id,
                            "Generation communication failed. Please try again.",
                        )
                        return True

                    got_message = True
                    drained += 1
                    state.dead_ticks = 0

                    if self._consume_worker_message(run_id, state, result):
                        return True

                if not got_message:
                    return False

            return not self._is_current_run(run_id)
        finally:
            self._advance_poll_cursor()

    def _worker_states_for_poll(self) -> list[_WorkerState]:
        states = list(self._workers.values())
        if not states:
            return []

        start = self._poll_cursor % len(states)
        return states[start:] + states[:start]

    def _advance_poll_cursor(self) -> None:
        if self._workers:
            self._poll_cursor = (self._poll_cursor + 1) % len(self._workers)
        else:
            self._poll_cursor = 0

    def _check_worker_timeouts(self, run_id: int, now: float) -> bool:
        for state in list(self._workers.values()):
            if state.run_id != run_id or state.done_seen:
                continue

            worker_elapsed = now - state.started_at
            if worker_elapsed <= _HARD_KILL_GEN_SECS:
                continue

            logger.error(
                "Generation worker timed out: run=%s period=%s elapsed=%.1fs",
                run_id,
                state.period_key,
                worker_elapsed,
            )
            self._fail(
                run_id,
                f"Generation timed out after {_HARD_KILL_GEN_SECS // 60} minutes "
                "and was stopped.",
            )
            return True

        return False

    def _consume_worker_message(
        self,
        run_id: int,
        state: _WorkerState,
        result: object,
    ) -> bool:
        """Handle one queue message. Return True if polling should stop."""
        if not self._is_current_run(run_id):
            return True

        try:
            if isinstance(result, GenerationDone):
                return self._handle_done(run_id, state, result)

            if isinstance(result, GenerationResult):
                if result.success:
                    return self._handle_success(run_id, state, result)

                if state.done_seen:
                    return self._protocol_fail(
                        run_id,
                        state,
                        "worker sent failure after Done",
                    )

                logger.error(
                    "Generation worker failed: run=%s period=%s error=%s",
                    run_id,
                    state.period_key,
                    result.error,
                )
                self._fail(
                    run_id,
                    "Generation failed. Please check the input files and try again.",
                )
                return True

            return self._protocol_fail(
                run_id,
                state,
                f"unknown message type {type(result).__name__}",
            )
        except Exception:
            logger.exception(
                "Unexpected error processing generation result: run=%s period=%s",
                run_id,
                state.period_key,
            )
            self._fail(
                run_id,
                "An unexpected error occurred processing the generation result.",
            )
            return True

    def _handle_success(
        self,
        run_id: int,
        state: _WorkerState,
        result: GenerationResult,
    ) -> bool:
        if state.done_seen:
            return self._protocol_fail(run_id, state, "worker sent partial after Done")
        if state.partial_seen:
            return self._protocol_fail(run_id, state, "worker sent duplicate partial")
        if not self._valid_success_payload(state, result):
            return self._protocol_fail(run_id, state, "worker sent malformed partial")

        state.partial_seen = True
        logger.info(
            "Generation partial received: run=%s period=%s",
            run_id,
            state.period_key,
        )
        self._handle_partial(run_id, result)
        return not self._is_current_run(run_id)

    def _valid_success_payload(
        self,
        state: _WorkerState,
        result: GenerationResult,
    ) -> bool:
        if not isinstance(result.schedules_by_period, dict):
            return False
        if set(result.schedules_by_period) != {state.period_key}:
            return False
        if not isinstance(result.courses_by_id, dict):
            return False
        if not isinstance(result.truncated_periods, set):
            return False
        if not result.truncated_periods <= {state.period_key}:
            return False
        return all(
            isinstance(schedules, list)
            for schedules in result.schedules_by_period.values()
        )

    def _handle_done(
        self,
        run_id: int,
        state: _WorkerState,
        result: GenerationDone,
    ) -> bool:
        if state.done_seen:
            return self._protocol_fail(run_id, state, "worker sent duplicate Done")
        if result.period_key != state.period_key:
            return self._protocol_fail(
                run_id,
                state,
                "worker sent Done for the wrong period",
            )
        if not isinstance(result.truncated_periods, set):
            return self._protocol_fail(run_id, state, "worker sent malformed Done")
        if not result.truncated_periods <= {state.period_key}:
            return self._protocol_fail(
                run_id,
                state,
                "worker sent Done with another period's truncation flag",
            )

        state.done_seen = True
        state.done_received_at = time.monotonic()
        self._truncated_periods.update(result.truncated_periods)
        logger.info(
            "Generation terminal marker received: run=%s period=%s",
            run_id,
            state.period_key,
        )
        return self._retire_done_worker_if_exited(run_id, state)

    def _protocol_fail(
        self,
        run_id: int,
        state: _WorkerState,
        reason: str,
    ) -> bool:
        logger.error(
            "Generation worker protocol error: run=%s period=%s reason=%s",
            run_id,
            state.period_key,
            reason,
        )
        self._fail(
            run_id,
            "Generation worker protocol error. Please try again.",
        )
        return True

    def _handle_partial(self, run_id: int, result: GenerationResult) -> None:
        """Cache and emit one streamed period batch for incremental display."""
        if not self._got_first_partial:
            self._got_first_partial = True
            self.progress_reset.emit()
            if not self._is_current_run(run_id):
                return
            self._controller.begin_streaming_cache()

        sorted_partial = self._controller.cache_generated_results_incremental(
            result.schedules_by_period
        )

        self.period_ready.emit(
            (
                list(self._pending_selected),
                sorted_partial,
                result.courses_by_id,
                dict(self._pending_color_map),
                set(result.truncated_periods),
            )
        )

    def _retire_done_worker_if_exited(
        self,
        run_id: int,
        state: _WorkerState,
    ) -> bool:
        alive = self._process_is_alive(state)
        if alive is None:
            self._fail(
                run_id,
                "Generation worker state could not be inspected. Please try again.",
            )
            return True
        if alive:
            return False

        exitcode = self._join_and_exitcode(state)
        if exitcode not in (None, 0):
            logger.error(
                "Generation worker exited non-zero after Done: run=%s period=%s "
                "exitcode=%s",
                run_id,
                state.period_key,
                exitcode,
            )
            self._fail(
                run_id,
                "Generation process exited unexpectedly.",
            )
            return True

        self._retire_worker_state(run_id, state)
        if not self._is_current_run(run_id):
            return True

        if len(self._completed_periods) >= len(self._expected_period_keys):
            self._finish(run_id, set(self._truncated_periods))
            return True

        return not self._start_next_workers(run_id)

    def _retire_worker_state(
        self,
        run_id: int,
        state: _WorkerState,
        *,
        cleanup: bool = True,
    ) -> None:
        current = self._workers.get(state.period_key)
        if current is not state:
            return

        self._workers.pop(state.period_key, None)
        self._completed_periods.add(state.period_key)
        if cleanup:
            self._cleanup_worker_resources(state, terminate=False)
        self._set_legacy_refs()
        logger.info(
            "Generation worker retired: run=%s period=%s completed=%s/%s",
            run_id,
            state.period_key,
            len(self._completed_periods),
            len(self._expected_period_keys),
        )

    def _join_and_exitcode(self, state: _WorkerState) -> int | None:
        proc = state.process
        if proc is None:
            return 0
        try:
            proc.join(timeout=0)
        except Exception:
            logger.debug("Failed joining completed generation worker", exc_info=True)
        try:
            return proc.exitcode
        except Exception:
            logger.debug("Failed reading completed worker exitcode", exc_info=True)
            return None

    def _check_workers(self, run_id: int) -> None:
        if not self._is_current_run(run_id):
            return

        now = time.monotonic()

        for state in list(self._workers.values()):
            alive = self._process_is_alive(state)

            if alive is None:
                self._fail(
                    run_id,
                    "Generation worker state could not be inspected. Please try again.",
                )
                return

            if alive:
                if self._cleanup_lingering_done_worker_if_needed(
                    run_id,
                    state,
                    now,
                ):
                    return
                continue

            if state.done_seen:
                if self._retire_done_worker_if_exited(run_id, state):
                    return
                continue

            state.dead_ticks += 1
            logger.info(
                "Generation worker exit detected: run=%s period=%s ticks=%s",
                run_id,
                state.period_key,
                state.dead_ticks,
            )

            if state.dead_ticks < _DEAD_TICKS_BEFORE_FAIL:
                continue

            if self._drain_after_exit(run_id, state):
                if not self._is_current_run(run_id):
                    return
                continue

            exitcode = self._join_and_exitcode(state)
            if exitcode not in (None, 0):
                logger.error(
                    "Generation worker exited non-zero without Done: run=%s "
                    "period=%s exitcode=%s",
                    run_id,
                    state.period_key,
                    exitcode,
                )

            self._fail(run_id, "Generation process exited unexpectedly.")
            return

    def _cleanup_lingering_done_worker_if_needed(
        self,
        run_id: int,
        state: _WorkerState,
        now: float,
    ) -> bool:
        if not state.done_seen:
            return False

        if state.done_received_at is None:
            state.done_received_at = now
            return False

        if now - state.done_received_at <= _DONE_EXIT_GRACE_SECS:
            return False

        logger.warning(
            "Generation worker stayed alive after Done; forcing cleanup: "
            "run=%s period=%s grace=%.1fs",
            run_id,
            state.period_key,
            _DONE_EXIT_GRACE_SECS,
        )
        self._cleanup_worker_resources(state, terminate=True)
        self._retire_worker_state(run_id, state, cleanup=False)
        if not self._is_current_run(run_id):
            return True

        if len(self._completed_periods) >= len(self._expected_period_keys):
            self._finish(run_id, set(self._truncated_periods))
            return True

        return not self._start_next_workers(run_id)

    def _drain_after_exit(self, run_id: int, state: _WorkerState) -> bool:
        """Blocking-drain residual messages after a worker exits."""
        deadline = time.monotonic() + _FINAL_DRAIN_SECS
        while self._is_current_run(run_id):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False

            try:
                result = state.queue.get(timeout=remaining)
            except _QueueEmpty:
                return False
            except (BrokenPipeError, EOFError, OSError, ValueError):
                logger.exception(
                    "Generation queue failed during final drain: run=%s period=%s",
                    run_id,
                    state.period_key,
                )
                self._fail(
                    run_id,
                    "Generation communication failed. Please try again.",
                )
                return True

            if self._consume_worker_message(run_id, state, result):
                return True
            if state.done_seen or state.period_key not in self._workers:
                return True

        return True

    def _finish(self, run_id: int, truncated_periods: set[str]) -> None:
        """Finalise a completed streaming run."""
        if not self._is_current_run(run_id):
            return

        logger.info(
            "Generation run %s succeeded: truncated_periods=%s",
            run_id,
            sorted(truncated_periods),
        )
        self._stop_timer()

        self.progress_reset.emit()
        if not self._is_current_run(run_id):
            return

        try:
            self._controller.on_generation_succeeded(truncated_periods)
        except Exception:
            logger.exception("Controller success hook failed")
            self._fail(
                run_id,
                "An unexpected error occurred finalising generation results.",
            )
            return

        if not self._got_first_partial:
            self._got_first_partial = True
            try:
                self._controller.begin_streaming_cache()
            except Exception:
                logger.exception("Controller streaming-cache initialisation failed")
                self._fail(
                    run_id,
                    "An unexpected error occurred finalising generation results.",
                )
                return

            self.period_ready.emit(
                (
                    list(self._pending_selected),
                    {},
                    {},
                    dict(self._pending_color_map),
                    set(),
                )
            )
            if not self._is_current_run(run_id):
                return

        self.generation_succeeded.emit(
            (
                list(self._pending_selected),
                dict(self._pending_color_map),
                set(truncated_periods),
            )
        )
        if not self._is_current_run(run_id):
            return

        self._active_run_id = None
        self._cleanup_run_resources(terminate=False)
        self._clear_run_state(clear_signals=False)

    def _fail(self, run_id: int | None, msg: str) -> None:
        if not self._is_current_run(run_id):
            return

        logger.error("Generation run %s failed: %s", run_id, msg)
        self._stop_timer()
        self._cleanup_run_resources(terminate=True)
        self._pending_periods.clear()
        self._mark_results_stale()

        self.generation_failed.emit(msg)
        if not self._is_current_run(run_id):
            return

        self.progress_reset.emit()
        if not self._is_current_run(run_id):
            return

        self._active_run_id = None
        self._clear_run_state(clear_signals=False)

    def _mark_results_stale(self) -> None:
        try:
            mark = getattr(self._controller, "mark_results_stale", None)
            if mark is not None:
                mark()
        except Exception:
            logger.debug("Failed marking generation results stale", exc_info=True)
