"""
GenerationPoller — background generation process lifecycle.

Owns the subprocess, result queue, and QTimer so ConfigScreen stays
focused on UI construction and state changes only.
"""

import logging
import multiprocessing
import time
from queue import Empty as _QueueEmpty

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from src.controller import DesktopController, LOAD_BATCH_SIZE, _run_generation_process
from src.domain.generation_result import GenerationDone, GenerationResult

logger = logging.getLogger(__name__)

# Soft threshold: after this many seconds the user is warned once that
# generation is taking a while. It does NOT kill the process — generation
# continues until it finishes on its own (see SCRUM-393).
_WARN_GEN_SECS = 180


class GenerationPoller(QObject):
    """Manages a single generation subprocess and emits result/failure signals."""

    period_ready = pyqtSignal(object)           # one streamed period batch tuple
    generation_succeeded = pyqtSignal(object)   # terminal: generation finished
    generation_failed = pyqtSignal(str)         # error message
    generation_warning = pyqtSignal(str)        # non-fatal slow-generation notice
    progress_reset = pyqtSignal()               # tell parent to hide progress bar

    def __init__(self, controller: DesktopController, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._process: multiprocessing.Process | None = None
        self._timer: QTimer | None = None
        self._queue: multiprocessing.Queue | None = None
        self._start_time: float = 0.0
        self._dead_ticks: int = 0
        self._warned: bool = False
        self._got_first_partial: bool = False
        self._pending_selected: list[str] = []
        self._pending_color_map: dict[str, str] = {}

    def is_running(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def start(
        self,
        selected: list[str],
        color_map: dict[str, str],
        allow_unassigned: bool,
    ) -> None:
        self._pending_selected = selected
        self._pending_color_map = color_map

        if self._process is not None and self._process.is_alive():
            self._process.kill()

        if self._timer is not None:
            self._timer.stop()

        if self._queue is not None:
            self._queue.cancel_join_thread()
            self._queue.close()

        self._start_time = time.monotonic()
        self._dead_ticks = 0
        self._warned = False
        self._got_first_partial = False
        self._queue = multiprocessing.Queue()

        self._process = multiprocessing.Process(
            target=_run_generation_process,
            args=(
                self._queue,
                self._controller.courses,
                self._controller.get_exam_periods(),
                selected,
            ),
            kwargs={
                "settings": self._controller.settings,
                "cap": LOAD_BATCH_SIZE,
                "classrooms": self._controller.engine_classrooms(),
                "time_slots": self._controller.engine_time_slots(),
                "proctor_config": self._controller.engine_proctor_config(),
                "allow_unassigned_classrooms": allow_unassigned,
                "stream": True,
            },
            daemon=True,
        )
        self._process.start()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(150)

    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
        if self._process and self._process.is_alive():
            self._process.kill()

    def _poll(self) -> None:
        # Soft timeout: warn once, but keep generating (SCRUM-393). The process
        # is never killed here.
        elapsed = int(time.monotonic() - self._start_time)
        if elapsed > _WARN_GEN_SECS and not self._warned:
            self._warned = True
            logger.warning("Generation exceeded %ss; still running.", _WARN_GEN_SECS)
            self.generation_warning.emit(
                f"Generation is taking longer than {_WARN_GEN_SECS // 60} minutes — "
                "still working…"
            )

        # Drain every message queued since the last tick. Several periods may
        # arrive between two 150 ms ticks, so a single get_nowait() is not
        # enough for smooth streaming.
        while True:
            try:
                result = self._queue.get_nowait()
            except (_QueueEmpty, OSError):
                self._check_process_alive()
                return

            self._dead_ticks = 0
            if self._consume(result):
                # Terminal message handled (done or failure) — stop polling.
                return

    def _check_process_alive(self) -> None:
        """Detect a worker that died without sending a terminal message."""
        if self._process is not None and not self._process.is_alive():
            self._dead_ticks += 1
            if self._dead_ticks >= 5:
                self._dead_ticks = 0
                if self._timer:
                    self._timer.stop()
                self._fail("Generation process exited unexpectedly.")
        else:
            self._dead_ticks = 0

    def _consume(self, result: object) -> bool:
        """Handle one queue message. Return True if it was terminal."""
        try:
            if isinstance(result, GenerationDone):
                self._finish(result.truncated_periods)
                return True

            if isinstance(result, GenerationResult) and result.success:
                self._handle_partial(result)
                return False

            logger.error("Generation failed or returned invalid result: %s", result)
            self._fail("Generation failed. Please check the input files and try again.")
            return True
        except Exception:
            logger.exception("Unexpected error processing generation result")
            self._fail("An unexpected error occurred processing the generation result.")
            return True

    def _handle_partial(self, result: GenerationResult) -> None:
        """Cache and emit one streamed period batch for incremental display."""
        if not self._got_first_partial:
            self._got_first_partial = True
            self.progress_reset.emit()
            self._controller.begin_streaming_cache()

        sorted_partial = self._controller.cache_generated_results_incremental(
            result.schedules_by_period
        )

        self.period_ready.emit(
            (
                self._pending_selected,
                sorted_partial,
                result.courses_by_id,
                self._pending_color_map,
                result.truncated_periods,
            )
        )

    def _finish(self, truncated_periods: set[str]) -> None:
        """Finalise a completed streaming run (no full rebuild)."""
        if self._timer:
            self._timer.stop()
        self.progress_reset.emit()

        self._controller.on_generation_succeeded(truncated_periods)

        # Zero-period runs stream nothing, so make sure the panel still leaves the
        # loading state and renders its empty scaffold.
        if not self._got_first_partial:
            self._got_first_partial = True
            self._controller.begin_streaming_cache()
            self.period_ready.emit(
                (
                    self._pending_selected,
                    {},
                    {},
                    self._pending_color_map,
                    set(),
                )
            )

        self.generation_succeeded.emit(
            (
                self._pending_selected,
                self._pending_color_map,
                truncated_periods,
            )
        )

    def _fail(self, msg: str) -> None:
        self.progress_reset.emit()
        if self._timer:
            self._timer.stop()
        logger.error("Generation failed: %s", msg)
        self.generation_failed.emit(msg)
