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
from src.domain.generation_result import GenerationResult

logger = logging.getLogger(__name__)

_MAX_GEN_SECS = 180


class GenerationPoller(QObject):
    """Manages a single generation subprocess and emits result/failure signals."""

    generation_succeeded = pyqtSignal(object)   # full result tuple
    generation_failed = pyqtSignal(str)         # error message
    progress_reset = pyqtSignal()               # tell parent to hide progress bar

    def __init__(self, controller: DesktopController, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._process: multiprocessing.Process | None = None
        self._timer: QTimer | None = None
        self._queue: multiprocessing.Queue | None = None
        self._start_time: float = 0.0
        self._dead_ticks: int = 0
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
        elapsed = int(time.monotonic() - self._start_time)

        if elapsed > _MAX_GEN_SECS:
            if self._timer:
                self._timer.stop()
            if self._process:
                self._process.kill()
            self._fail(f"Generation timed out after {_MAX_GEN_SECS}s.")
            return

        try:
            result = self._queue.get_nowait()
        except (_QueueEmpty, OSError):
            if self._process is not None and not self._process.is_alive():
                self._dead_ticks += 1
                if self._dead_ticks >= 5:
                    self._dead_ticks = 0
                    if self._timer:
                        self._timer.stop()
                    self._fail("Generation process exited unexpectedly.")
            else:
                self._dead_ticks = 0
            return

        self._dead_ticks = 0
        if self._timer:
            self._timer.stop()
        self.progress_reset.emit()

        try:
            if isinstance(result, GenerationResult) and result.success:
                schedules_by_period = result.schedules_by_period
                courses_by_id = result.courses_by_id
                truncated_periods = result.truncated_periods

                self._controller.on_generation_succeeded(truncated_periods)
                schedules_by_period = self._controller.cache_generated_results(
                    schedules_by_period
                )

                self.generation_succeeded.emit(
                    (
                        self._pending_selected,
                        schedules_by_period,
                        courses_by_id,
                        self._pending_color_map,
                        truncated_periods,
                    )
                )
            else:
                logger.error("Generation failed or returned invalid result: %s", result)
                self._fail("Generation failed. Please check the input files and try again.")
        except Exception:
            logger.exception("Unexpected error processing generation result")
            self._fail("An unexpected error occurred processing the generation result.")

    def _fail(self, msg: str) -> None:
        self.progress_reset.emit()
        if self._timer:
            self._timer.stop()
        logger.error("Generation failed: %s", msg)
        self.generation_failed.emit(msg)
