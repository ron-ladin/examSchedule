"""Result Ranking worker orchestration extracted from the Results panel."""

from __future__ import annotations

import logging
import multiprocessing
from queue import Empty as QueueEmpty
from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox

from src.domain.schedule import Schedule
from src.domain.sorting import SortingConfig
from src.engine.ranking_worker import RankingWorkerResult, run_ranking_worker
from src.ui.focus_utils import restore_focus_on_macos

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers.
    from multiprocessing.context import BaseContext

    from src.ui.results_panel import _ResultsPanel

logger = logging.getLogger(__name__)
_RANKING_EXIT_QUEUE_GRACE_TICKS = 3


class ResultRankingController:
    """Own and poll the background Result Ranking worker."""

    def __init__(
        self,
        panel: "_ResultsPanel",
        *,
        worker_context_provider: Callable[[], "BaseContext"],
        ranking_button_text: str,
    ) -> None:
        self._panel = panel
        self._worker_context_provider = worker_context_provider
        self._ranking_button_text_default = ranking_button_text

        self._proc: multiprocessing.Process | None = None
        self._queue: multiprocessing.Queue | None = None
        self._timer: QTimer | None = None
        self._config: SortingConfig | None = None
        self._button_text: str | None = None
        self._empty_after_exit_ticks = 0

    @property
    def proc(self) -> multiprocessing.Process | None:
        return self._proc

    @proc.setter
    def proc(self, value: multiprocessing.Process | None) -> None:
        self._proc = value

    @property
    def queue(self) -> multiprocessing.Queue | None:
        return self._queue

    @queue.setter
    def queue(self, value: multiprocessing.Queue | None) -> None:
        self._queue = value

    @property
    def timer(self) -> QTimer | None:
        return self._timer

    @timer.setter
    def timer(self, value: QTimer | None) -> None:
        self._timer = value

    @property
    def config(self) -> SortingConfig | None:
        return self._config

    @config.setter
    def config(self, value: SortingConfig | None) -> None:
        self._config = value

    @property
    def button_text(self) -> str | None:
        return self._button_text

    @button_text.setter
    def button_text(self, value: str | None) -> None:
        self._button_text = value

    @property
    def empty_after_exit_ticks(self) -> int:
        return self._empty_after_exit_ticks

    @empty_after_exit_ticks.setter
    def empty_after_exit_ticks(self, value: int) -> None:
        self._empty_after_exit_ticks = value

    def on_result_ranking(self) -> None:
        """Open the Result Ranking dialog and re-rank cached results in place."""
        panel = self._panel
        if panel._is_stale():
            panel._show_message(
                "Stale Schedules",
                "Settings have changed since the last generation.\n\n"
                "Please click  ▶  Generate again before re-ranking results.",
                QMessageBox.Icon.Warning,
            )
            return

        if not any(panel._schedules_by_period.values()):
            panel._show_message(
                "No Schedules",
                "Generate or load schedules before changing the result ranking.",
                QMessageBox.Icon.Warning,
            )
            return

        from src.ui.ranking_dialog import RankingDialog

        dialog = RankingDialog(panel._controller.settings.sorting, parent=panel)
        dialog.ranking_applied.connect(panel._apply_ranking)
        dialog.exec()

    def apply_ranking(self, config: SortingConfig) -> None:
        """Start asynchronous re-ranking of cached schedules."""
        panel = self._panel
        if self._proc is not None:
            panel._show_message(
                "Ranking In Progress",
                "Result Ranking is already running. Please wait for it to finish.",
                QMessageBox.Icon.Information,
            )
            return

        if not panel._begin_heavy_task("ranking"):
            panel._show_message(
                "Ranking Unavailable",
                "Result Ranking is available after generation/loading finishes.",
                QMessageBox.Icon.Information,
            )
            panel._refresh_heavy_task_controls()
            return

        try:
            job = panel._controller.build_ranking_job(config)
        except ValueError:
            panel._controller.apply_sort(config)
            panel._end_heavy_task("ranking")
            return

        ctx = self._worker_context_provider()
        queue = ctx.Queue()
        proc = ctx.Process(
            target=run_ranking_worker,
            args=(queue, job),
            daemon=True,
        )

        self._queue = queue
        self._proc = proc
        self._config = config
        self._empty_after_exit_ticks = 0
        self.set_ranking_busy(True)

        try:
            proc.start()
            restore_focus_on_macos(panel)
        except Exception as exc:
            self.cleanup_ranking_worker(terminate=True)
            self._config = None
            panel._end_heavy_task("ranking")
            self.set_ranking_busy(False)
            panel._show_message(
                "Ranking Failed",
                f"Could not start Result Ranking.\n\n{exc}",
                QMessageBox.Icon.Warning,
            )
            return

        timer = QTimer(panel)
        timer.timeout.connect(self.poll_ranking_worker)
        timer.start(100)
        self._timer = timer

    def poll_ranking_worker(self) -> None:
        """Poll the background ranking worker without blocking the UI thread."""
        panel = self._panel
        queue = self._queue
        proc = self._proc
        if queue is None:
            self.cleanup_ranking_worker(terminate=True)
            self.set_ranking_busy(False)
            return

        try:
            result = queue.get_nowait()
        except QueueEmpty:
            if proc is not None and not proc.is_alive() and proc.exitcode is not None:
                self._empty_after_exit_ticks += 1
                if self._empty_after_exit_ticks <= _RANKING_EXIT_QUEUE_GRACE_TICKS:
                    return
                exitcode = proc.exitcode
                self.cleanup_ranking_worker(terminate=False)
                self._config = None
                panel._end_heavy_task("ranking")
                self.set_ranking_busy(False)
                panel._show_message(
                    "Ranking Failed",
                    f"Result Ranking stopped before returning a result (exit code {exitcode}).",
                    QMessageBox.Icon.Warning,
                )
            return

        self._empty_after_exit_ticks = 0
        config = self._config
        self.cleanup_ranking_worker(terminate=False)
        self._config = None

        if not isinstance(result, RankingWorkerResult):
            panel._end_heavy_task("ranking")
            self.set_ranking_busy(False)
            panel._show_message(
                "Ranking Failed",
                "Result Ranking returned an unexpected response.",
                QMessageBox.Icon.Warning,
            )
            return

        if not result.success:
            panel._end_heavy_task("ranking")
            self.set_ranking_busy(False)
            panel._show_message(
                "Ranking Failed",
                result.error or "Result Ranking failed.",
                QMessageBox.Icon.Warning,
            )
            return

        if config is None:
            panel._end_heavy_task("ranking")
            self.set_ranking_busy(False)
            panel._show_message(
                "Ranking Failed",
                "Result Ranking finished after the ranking state was cleared.",
                QMessageBox.Icon.Warning,
            )
            return

        try:
            resorted = panel._controller.apply_ranked_results(
                config,
                result.schedules_by_period,
            )
        except Exception as exc:
            panel._end_heavy_task("ranking")
            self.set_ranking_busy(False)
            panel._show_message(
                "Ranking Failed",
                str(exc),
                QMessageBox.Icon.Warning,
            )
            return

        self.finish_ranking_success(resorted)
        panel._end_heavy_task("ranking")
        self.set_ranking_busy(False)

    def finish_ranking_success(
        self,
        resorted: dict[str, list[Schedule]],
    ) -> None:
        """Apply ranked results to the panel and refresh only the visible card."""
        panel = self._panel
        for period_key, schedules in resorted.items():
            panel._schedules_by_period[period_key] = schedules
            panel._period_indices[period_key] = 0

        panel._nav_model.clear()
        for period_key in resorted:
            panel._rebuild_navigation_cache(period_key)
        panel._refresh_shortlist_labels()
        panel._clear_ranking_dirty()

        has_proctor_report = any(
            panel._has_classroom_feature_results(period_key)
            for period_key, schedules in panel._schedules_by_period.items()
            if schedules
        )
        panel._proctor_btn.setVisible(has_proctor_report)

        visible_period_key = panel._current_period_key()
        if visible_period_key is not None and visible_period_key in panel._cards:
            panel._refresh_period_card(visible_period_key)
        else:
            panel._update_summary()

    def set_ranking_busy(self, busy: bool) -> None:
        """Update ranking button state while a background ranking job runs."""
        panel = self._panel
        if not hasattr(panel, "_ranking_btn"):
            return

        heavy_kind = panel._controller.heavy_task_kind
        if busy or heavy_kind == "ranking":
            current_text = panel._ranking_btn.text()
            if current_text not in {
                "Ranking results...",
                "Ranking available after loading finishes",
            }:
                self._button_text = current_text
            elif self._button_text is None:
                self._button_text = self._ranking_button_text_default
            panel._ranking_btn.setEnabled(False)
            panel._ranking_btn.setText("Ranking results...")
            panel._summary_lbl.setText("Ranking results...")
            return

        if heavy_kind in {"generation", "loading"}:
            panel._ranking_btn.setEnabled(False)
            panel._ranking_btn.setText("Ranking available after loading finishes")
            panel._update_summary()
            return

        panel._ranking_btn.setEnabled(True)
        panel._ranking_btn.setText(
            self._button_text or self._ranking_button_text_default
        )
        self._button_text = None
        panel._update_summary()

    def cleanup_ranking_worker(self, terminate: bool = False) -> None:
        """Stop timers/processes for the ranking worker and release handles."""
        panel = self._panel
        timer = self._timer
        self._timer = None
        if timer is not None:
            timer.stop()

        proc = self._proc
        self._proc = None
        self._empty_after_exit_ticks = 0
        if proc is not None:
            try:
                if terminate and proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=0.2)
                    if proc.is_alive():
                        proc.kill()
                        proc.join(timeout=0.2)
                else:
                    if not proc.is_alive():
                        proc.join(timeout=0.2)
            except Exception:
                logger.debug("Failed cleaning up ranking process", exc_info=True)

        queue = self._queue
        self._queue = None
        if queue is not None:
            close = getattr(queue, "close", None)
            if callable(close):
                close()

        if terminate and panel._controller.end_heavy_task("ranking"):
            self.finish_ranking_metrics()
            panel.heavy_task_state_changed.emit("ranking", False)

    def is_ranking_active(self) -> bool:
        """Return True while the Result Ranking worker owns the heavy slot."""
        return self._panel._controller.heavy_task_kind == "ranking"

    def finish_ranking_metrics(self) -> None:
        """Finalize ranking timing metrics."""
        panel = self._panel
        try:
            snapshot = panel._controller.performance_metrics.finish_ranking()
            logger.info(
                "Ranking performance summary: elapsed=%.3fs schedules=%s sqlite_rows=%s",
                snapshot.ranking_seconds,
                panel._controller.cached_schedule_count(),
                snapshot.sqlite_stored_row_count,
            )
        except Exception:
            logger.debug("Failed recording ranking metrics", exc_info=True)
