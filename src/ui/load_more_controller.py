"""
LoadMoreController — background load-more / auto-load orchestration.

Owns every ``_lm_*`` worker-state dict plus the per-period Auto Dates / Auto
Variants lifecycle, so _ResultsPanel can stay focused on layout, navigation,
and rendering. The controller holds a back-reference to the panel and reads its
live schedule/navigation state through it.
"""

import logging
import multiprocessing
from queue import Empty as _QueueEmpty

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QPushButton

from src.controller import LOAD_BATCH_SIZE
from src.domain.generation_result import GenerationResult
from src.ui.navigation_model import DateSignature as _DateSignature

logger = logging.getLogger(__name__)

_SPINNER_CHARS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

AUTO_LOAD_DELAY_MS = 500

_AUTO_MODE_DATES = "dates"
_AUTO_MODE_VARIANTS = "variants"

_INFO = QMessageBox.Icon.Information


class LoadMoreController(QObject):
    """Manage background batch-loading workers for the results panel.

    Emits PyQt signals for user-facing messages and card refreshes instead of
    calling the panel's private methods directly. The panel connects its own
    slots and applies the effect to its own widgets/state.

    Signals
    -------
    messageRequested(title: str, text: str, icon: object)
        A user-facing message box should be shown.
    cardRefreshRequested(period_key: str)
        The period card for ``period_key`` should be re-rendered.
    """

    messageRequested = pyqtSignal(str, str, object)
    cardRefreshRequested = pyqtSignal(str)

    def __init__(self, panel) -> None:
        super().__init__(panel)
        self._panel = panel
        self._controller = panel.controller

        self.auto_load_periods: set[str] = set()
        self.auto_load_modes: dict[str, str] = {}
        # If the user clicks the other Auto button while a batch is already
        # running, finish the current batch, then start the requested mode.
        self.pending_auto_modes: dict[str, str] = {}
        self.variant_more_by_signature: dict[tuple[str, _DateSignature], bool] = {}

        self.queues: dict[str, multiprocessing.Queue] = {}
        self.chunk_sizes: dict[str, int | None] = {}
        self.modes: dict[str, str] = {}
        self.procs: dict[str, multiprocessing.Process] = {}
        self.timers: dict[str, QTimer] = {}
        self.ticks: dict[str, int] = {}
        self.advance_after_load: set[str] = set()

    def reset(self) -> None:
        """Stop all in-flight workers and clear per-result-set auto state."""
        for key in set(self.procs) | set(self.timers) | set(self.queues):
            self.cleanup_load_more_state(key, terminate=True)
        self.auto_load_periods.clear()
        self.auto_load_modes.clear()
        self.pending_auto_modes.clear()
        self.variant_more_by_signature.clear()

    def start_automatic_loads(self) -> None:
        """Start automatic loading for all currently truncated periods.

        Kept for compatibility with existing tests and older auto-load behavior.
        The current UI uses per-period Auto Load buttons, but tests can call this
        directly to start loading every truncated period.
        """
        if self._panel.is_ranking_active():
            self.messageRequested.emit(
                "Ranking In Progress",
                "Load More is available after Result Ranking finishes.",
                _INFO,
            )
            return

        for period_key in self._panel.get_truncated_periods():
            if period_key in self.procs:
                continue

            self.auto_load_periods.add(period_key)
            self.auto_load_modes[period_key] = _AUTO_MODE_DATES
            self.update_auto_load_button(period_key)
            self.on_load_more(period_key)

    def toggle_auto_load(self, period_key: str) -> None:
        """Backward-compatible alias for date auto loading."""
        self.toggle_auto_load_dates(period_key)

    def toggle_auto_load_dates(self, period_key: str) -> None:
        """Start/stop automatic loading of different date options."""
        if self.auto_load_modes.get(period_key) == _AUTO_MODE_DATES:
            self.stop_auto_load(period_key)
            return

        if not self._controller.has_more_schedules(period_key):
            self.messageRequested.emit(
                "No More Date Options",
                "There are no more date options to load for this period.",
                _INFO,
            )
            return

        self._switch_or_start_auto_load(period_key, _AUTO_MODE_DATES)

    def toggle_auto_load_variants(self, period_key: str) -> None:
        """Start/stop automatic loading of variants for the current dates."""
        if self.auto_load_modes.get(period_key) == _AUTO_MODE_VARIANTS:
            self.stop_auto_load(period_key)
            return

        panel = self._panel
        if not panel.get_schedules(period_key):
            return

        if not panel.has_classroom_results(period_key):
            self.messageRequested.emit(
                "No Classroom Variants",
                "Generate schedules with Feature 4 enabled before loading classroom variants.",
                _INFO,
            )
            return

        signature = panel.get_current_signature(period_key)
        if signature is None:
            return
        maybe_more = self.variant_more_by_signature.get((period_key, signature), True)
        if not maybe_more:
            self.messageRequested.emit(
                "No More Variants",
                "No additional variants are known for the current date option.",
                _INFO,
            )
            return

        self._switch_or_start_auto_load(period_key, _AUTO_MODE_VARIANTS)

    def _switch_or_start_auto_load(self, period_key: str, target_mode: str) -> None:
        """Start an Auto mode, or queue it after the current batch finishes.

        Only one background process may write into a period at a time. When the
        user clicks the other Auto button while a batch is running, do not start
        a second process immediately. Instead, stop scheduling the current Auto
        mode, remember the requested mode, and launch it as soon as the current
        batch returns.
        """
        current_mode = self.auto_load_modes.get(period_key)

        if current_mode == target_mode:
            self.stop_auto_load(period_key)
            return

        if self._panel.is_ranking_active():
            self.messageRequested.emit(
                "Ranking In Progress",
                "Auto Load is available after Result Ranking finishes.",
                _INFO,
            )
            self.update_auto_load_button(period_key)
            self.cardRefreshRequested.emit(period_key)
            return

        if period_key in self.procs:
            self.pending_auto_modes[period_key] = target_mode
            self.auto_load_periods.discard(period_key)
            self.auto_load_modes.pop(period_key, None)
            self.update_auto_load_button(period_key)
            self.cardRefreshRequested.emit(period_key)
            return

        self.stop_auto_load(period_key, refresh=False)
        self.start_auto_load(period_key, target_mode)

    def start_auto_load(self, period_key: str, mode: str) -> None:
        """Start one scoped auto-load mode for a period."""
        if period_key in self.auto_load_periods:
            self.stop_auto_load(period_key, refresh=False)

        self.pending_auto_modes.pop(period_key, None)
        self.auto_load_periods.add(period_key)
        self.auto_load_modes[period_key] = mode
        self.update_auto_load_button(period_key)
        self.cardRefreshRequested.emit(period_key)
        self._auto_load_next_batch(period_key)

    def stop_auto_load(self, period_key: str, refresh: bool = True) -> None:
        """Stop scheduling additional auto-load batches for a period."""
        self.auto_load_periods.discard(period_key)
        self.auto_load_modes.pop(period_key, None)
        self.pending_auto_modes.pop(period_key, None)
        self.update_auto_load_button(period_key)
        if refresh and self._panel.has_period(period_key):
            self.cardRefreshRequested.emit(period_key)

    def _auto_load_next_batch(self, period_key: str) -> None:
        """Request the next batch for the active scoped Auto mode."""
        if period_key not in self.auto_load_periods:
            self.update_auto_load_button(period_key)
            return

        if self._panel.is_ranking_active():
            self.stop_auto_load(period_key)
            return

        if period_key in self.procs:
            return

        mode = self.auto_load_modes.get(period_key)
        if mode == _AUTO_MODE_DATES:
            if not self._controller.has_more_schedules(period_key):
                self.stop_auto_load(period_key)
                return
            self.on_load_more_dates(period_key)
            return

        if mode == _AUTO_MODE_VARIANTS:
            self.on_load_more_variants(period_key)
            return

        self.stop_auto_load(period_key)

    def _style_auto_button(
        self,
        button: QPushButton,
        color: str,
        background: str,
        enabled: bool,
    ) -> None:
        button.setStyleSheet(
            "QPushButton {"
            f"color: {color}; border: 2px solid {color}; border-radius: 8px;"
            "padding: 6px 12px; font-size: 11px; font-weight: 700;"
            f"background: {background};"
            "}"
            f"QPushButton:hover {{ background: {background}; }}"
            "QPushButton:disabled { color: #94A3B8; background: #F8FAFC;"
            "border-color: #CBD5E1; }"
        )
        button.setEnabled(enabled)

    def update_auto_load_button(self, period_key: str) -> None:
        """Refresh Auto Dates / Auto Variants button text and state."""
        panel = self._panel
        card = panel.get_card(period_key)
        date_btn = card.auto_date_btn if card else None
        variant_btn = card.auto_variant_btn if card else None

        mode = self.auto_load_modes.get(period_key)
        pending_mode = self.pending_auto_modes.get(period_key)
        is_loading = period_key in self.procs
        ranking_active = panel.is_ranking_active()
        has_more_dates = self._controller.has_more_schedules(period_key)
        has_classroom = panel.has_classroom_results(period_key)
        variant_maybe_more = True
        signature = panel.get_current_signature(period_key)
        if signature is not None:
            variant_maybe_more = self.variant_more_by_signature.get(
                (period_key, signature),
                True,
            )

        if date_btn is not None:
            if pending_mode == _AUTO_MODE_DATES:
                date_btn.setText("Dates queued")
                self._style_auto_button(
                    date_btn, "#475569", "#F1F5F9", False
                )
            elif mode == _AUTO_MODE_DATES:
                date_btn.setText("Stop Dates")
                self._style_auto_button(
                    date_btn, "#7F1D1D", "#FEF2F2", True
                )
            else:
                date_btn.setText("Auto Dates")
                self._style_auto_button(
                    date_btn,
                    "#047857",
                    "rgba(4, 120, 87, 0.07)",
                    has_more_dates
                    and not ranking_active
                    and pending_mode is None
                    and (not is_loading or mode == _AUTO_MODE_VARIANTS),
                )

        if variant_btn is not None:
            if pending_mode == _AUTO_MODE_VARIANTS:
                variant_btn.setText("Variants queued")
                self._style_auto_button(
                    variant_btn, "#475569", "#F1F5F9", False
                )
            elif mode == _AUTO_MODE_VARIANTS:
                variant_btn.setText("Stop Variants")
                self._style_auto_button(
                    variant_btn, "#7F1D1D", "#FEF2F2", True
                )
            else:
                variant_btn.setText("Auto Variants")
                self._style_auto_button(
                    variant_btn,
                    "#7C3AED",
                    "rgba(124, 58, 237, 0.07)",
                    has_classroom
                    and variant_maybe_more
                    and not ranking_active
                    and pending_mode is None
                    and (not is_loading or mode == _AUTO_MODE_DATES),
                )

    def _start_load_more_process(
        self,
        period_key: str,
        queue: multiprocessing.Queue,
        proc: multiprocessing.Process,
        mode: str,
    ) -> None:
        """Register a background load-more process and start polling it."""
        self.queues[period_key] = queue
        self.procs[period_key] = proc
        self.modes[period_key] = mode
        self.ticks[period_key] = 0
        self.chunk_sizes[period_key] = LOAD_BATCH_SIZE

        card = self._panel.get_card(period_key)
        btn = card.load_more_btn if card else None
        if btn is not None:
            btn.setEnabled(False)
            if period_key not in self.auto_load_periods:
                label = "date options" if mode == _AUTO_MODE_DATES else "variants"
                btn.setText(f"⠋  Loading {label}…")

        self.update_auto_load_button(period_key)

        timer = QTimer(self._panel)
        timer.timeout.connect(lambda: self.poll_load_more(period_key))
        timer.start(150)

        self.timers[period_key] = timer

    def on_load_more(self, period_key: str, chunk_size: int | None = None) -> None:
        """Backward-compatible manual action: load more date options."""
        self.on_load_more_dates(period_key, chunk_size)

    def on_load_more_dates(
        self,
        period_key: str,
        chunk_size: int | None = None,
    ) -> None:
        """Load one batch of different date options."""
        if period_key in self.procs:
            return
        if not self._begin_loading_task(period_key):
            return
        self._panel.show_workload_status(
            f"Loading {LOAD_BATCH_SIZE:,} more date options..."
        )

        try:
            already_date_options = self._panel.get_date_option_count(period_key)
            queue, proc = self._controller.start_load_more_date_options_for_period(
                period_key,
                already_date_options,
            )
            self._start_load_more_process(period_key, queue, proc, _AUTO_MODE_DATES)
        except Exception:
            self._finish_load_metrics()
            self._panel._end_heavy_task("loading")
            raise

    def on_load_more_variants(
        self,
        period_key: str,
        chunk_size: int | None = None,
    ) -> None:
        """Load one batch of variants for the currently displayed date option."""
        if period_key in self.procs:
            return
        if not self._begin_loading_task(period_key):
            return
        self._panel.show_workload_status("Loading classroom variants...")

        panel = self._panel
        schedules = panel.get_schedules(period_key)
        if not schedules:
            self._finish_load_metrics()
            panel._end_heavy_task("loading")
            self.stop_auto_load(period_key)
            return

        current_idx = panel.get_current_index(period_key)
        current_schedule = schedules[current_idx]
        signature = panel.signature_of(current_schedule)
        existing_variants = panel.get_variant_index_count(period_key, signature)

        try:
            queue, proc = self._controller.start_load_variants_for_schedule(
                period_key,
                current_schedule,
                existing_variants,
            )
            self._start_load_more_process(period_key, queue, proc, _AUTO_MODE_VARIANTS)
        except Exception:
            self._finish_load_metrics()
            panel._end_heavy_task("loading")
            raise

    def _begin_loading_task(self, period_key: str) -> bool:
        """Reserve the shared heavy-task slot for one load-more batch."""
        if self._panel.is_ranking_active():
            self.messageRequested.emit(
                "Ranking In Progress",
                "Load More is available after Result Ranking finishes.",
                _INFO,
            )
            self.update_auto_load_button(period_key)
            self.cardRefreshRequested.emit(period_key)
            return False

        if not self._panel._begin_heavy_task("loading"):
            self.messageRequested.emit(
                "Busy",
                "Another heavy task is already running. Please wait for it to finish.",
                _INFO,
            )
            self.update_auto_load_button(period_key)
            self.cardRefreshRequested.emit(period_key)
            return False

        self._controller.performance_metrics.start_load_batch(
            batch_size=LOAD_BATCH_SIZE,
            auto_load=period_key in self.auto_load_periods,
        )
        return True

    def poll_load_more(self, period_key: str) -> None:
        try:
            self._poll_load_more_inner(period_key)
        except Exception:
            logger.exception("Unexpected error in poll_load_more for %s", period_key)
            card = self._panel.get_card(period_key)
            btn = card.load_more_btn if card else None
            if btn:
                btn.setEnabled(True)
                btn.setText("⚠  Load failed — retry")
            self.stop_auto_load(period_key, refresh=False)
            self.cleanup_load_more_state(period_key, terminate=True)

    def _poll_load_more_inner(self, period_key: str) -> None:
        panel = self._panel
        queue = self.queues.get(period_key)
        if queue is None:
            # The results were rebuilt while this timer callback was already queued.
            # Exit safely instead of raising KeyError on stale state.
            self.cleanup_load_more_state(period_key, terminate=True)
            return

        mode = self.modes.get(period_key, _AUTO_MODE_DATES)
        tick = self.ticks.get(period_key, 0)
        spinner = _SPINNER_CHARS[tick % len(_SPINNER_CHARS)]
        self.ticks[period_key] = tick + 1

        card = panel.get_card(period_key)
        btn = card.load_more_btn if card else None
        if btn and period_key not in self.auto_load_periods:
            label = "date options" if mode == _AUTO_MODE_DATES else "variants"
            btn.setText(f"{spinner}  Loading {label}…")

        try:
            result = queue.get_nowait()
        except _QueueEmpty:
            proc = self.procs.get(period_key)

            # If the subprocess already ended and no result arrived, recover the UI
            # instead of leaving the button disabled forever.
            if proc is not None and not proc.is_alive() and tick > 2:
                if btn:
                    btn.setEnabled(True)
                    btn.setText("⚠  Load failed — retry")

                self.stop_auto_load(period_key, refresh=False)

                logger.error(
                    "Load more process ended without returning a result for %s",
                    period_key,
                )
                self.cleanup_load_more_state(period_key, terminate=False)

            return
        except OSError as exc:
            if btn:
                btn.setEnabled(True)
                btn.setText("⚠  Load failed — retry")

            self.stop_auto_load(period_key, refresh=False)

            logger.error("Load more queue failed for %s: %s", period_key, exc)
            self.cleanup_load_more_state(period_key, terminate=True)
            return

        # The persistent worker tags every result with its kind ("date_options"
        # or "variants") because one worker/result queue serves both. If a result
        # for a different kind than the batch we are currently waiting for shows
        # up (e.g. a stopped Auto Dates batch finishing after the user switched to
        # Auto Variants), it is stale: drain it and keep polling for the right
        # one instead of merging it into the wrong cache.
        if (
            isinstance(result, tuple)
            and len(result) == 2
            and isinstance(result[0], str)
        ):
            result_kind, payload = result
            expected_kind = (
                "variants" if mode == _AUTO_MODE_VARIANTS else "date_options"
            )
            # "error" results (malformed/unknown task) are always surfaced; only
            # a mismatched data kind is treated as a stale leftover.
            if result_kind not in (expected_kind, "error"):
                logger.debug(
                    "Discarding stale %s result while awaiting %s for %s",
                    result_kind,
                    expected_kind,
                    period_key,
                )
                return
            result = payload

        timer = self.timers.pop(period_key, None)
        if timer:
            timer.stop()

        if not (isinstance(result, GenerationResult) and result.success):
            error_details = (
                result.error if isinstance(result, GenerationResult) else result
            )

            if btn:
                btn.setEnabled(True)
                btn.setText("⚠  Load failed — retry")

            self.stop_auto_load(period_key, refresh=False)

            logger.error("Load more failed for %s: %s", period_key, error_details)
            self.cleanup_load_more_state(period_key, terminate=True)
            return

        all_by_period = result.schedules_by_period
        truncated_periods = result.truncated_periods

        old_len = len(panel.get_schedules(period_key))
        extra = all_by_period.get(period_key, [])
        still_more = period_key in truncated_periods
        active_auto_mode = self.auto_load_modes.get(period_key)
        should_continue_auto = False

        current_signature: _DateSignature | None = None
        if mode == _AUTO_MODE_VARIANTS:
            current_signature = panel.get_current_signature(period_key)

        should_advance_to_next_date = period_key in self.advance_after_load

        if extra:
            # The panel owns its schedule/nav state; ask it to merge the batch
            # rather than reaching into its private dicts (Tell, Don't Ask).
            panel.append_loaded_schedules(period_key, extra)

        if mode == _AUTO_MODE_DATES:
            if should_advance_to_next_date:
                self.advance_after_load.discard(period_key)
                # Explicit "advance after load" moves to the freshly loaded next
                # date option once the batch has merged.
                panel.advance_to_next_date_option(period_key, old_len)

            # Otherwise Auto Dates appends date options in the background without
            # moving the displayed option: the visible counter grows and the user
            # decides when to move with Next Dates or the Go input.

            panel.set_period_truncated(period_key, still_more)

            should_continue_auto = (
                active_auto_mode == _AUTO_MODE_DATES and still_more and bool(extra)
            )

        elif mode == _AUTO_MODE_VARIANTS:
            signature = current_signature
            if signature is None and extra:
                signature = panel.signature_of(extra[0])

            if signature is not None:
                self.variant_more_by_signature[(period_key, signature)] = still_more

            # Keep the currently displayed variant fixed while Auto Variants
            # appends more options in the background. The user can see the total
            # variant count grow and then choose when to move with Next Variant
            # or by using the variant Go input.

            # Do not update controller.has_more_schedules here: variant loading is
            # separate from date-option loading.
            should_continue_auto = (
                active_auto_mode == _AUTO_MODE_VARIANTS and still_more and bool(extra)
            )

        else:
            should_continue_auto = False

        self.cleanup_load_more_state(period_key)
        self.cardRefreshRequested.emit(period_key)

        if mode == _AUTO_MODE_DATES and still_more and btn:
            btn.setEnabled(period_key not in self.auto_load_periods)
            btn.setText(f"⟳  +{LOAD_BATCH_SIZE:,} more date options")

        pending_mode = self.pending_auto_modes.pop(period_key, None)
        if pending_mode is not None:
            # The user clicked the other Auto button while this batch was still
            # running. The current batch is now finished and merged, so start
            # the requested mode.
            self.auto_load_periods.discard(period_key)
            self.auto_load_modes.pop(period_key, None)
            self.start_auto_load(period_key, pending_mode)
            return

        if should_continue_auto:
            QTimer.singleShot(
                AUTO_LOAD_DELAY_MS,
                lambda k=period_key: self._auto_load_next_batch(k),
            )
        elif active_auto_mode == mode:
            self.stop_auto_load(period_key, refresh=False)

        self.update_auto_load_button(period_key)

    def cleanup_load_more_state(
        self,
        period_key: str,
        terminate: bool = False,
    ) -> None:
        timer = self.timers.pop(period_key, None)
        if timer is not None:
            timer.stop()

        self.queues.pop(period_key, None)
        self.chunk_sizes.pop(period_key, None)
        self.modes.pop(period_key, None)
        self.ticks.pop(period_key, None)
        self.advance_after_load.discard(period_key)

        proc = self.procs.pop(period_key, None)
        if proc is not None:
            try:
                if terminate and proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=0)

                    if proc.is_alive():
                        proc.kill()
                        proc.join(timeout=0)
                else:
                    # Non-blocking reap if the process already finished.
                    proc.join(timeout=0)
            except Exception:
                logger.debug("Failed cleaning up load-more process", exc_info=True)

        if not self.procs:
            self._finish_load_metrics()
            self._panel._end_heavy_task("loading")

    def _finish_load_metrics(self) -> None:
        """Finalize the current load-batch metrics snapshot, if one is active."""
        try:
            snapshot = self._controller.performance_metrics.finish_load_batch(
                sqlite_stored_row_count=self._panel.total_in_memory_schedule_count(),
            )
            logger.info(
                "Load batch performance summary: load_more=%.3fs auto_load=%.3fs "
                "sqlite_rows=%s batch_size=%s",
                snapshot.load_more_batch_seconds,
                snapshot.auto_load_batch_seconds,
                snapshot.sqlite_stored_row_count,
                snapshot.active_batch_size,
            )
        except Exception:
            logger.debug("Failed recording load batch metrics", exc_info=True)
