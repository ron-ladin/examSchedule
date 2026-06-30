"""Result-set load, streaming, and cleanup flow for the results panel."""

from __future__ import annotations

import gc
import logging
import sqlite3
from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMessageBox

from src.adapters.sqlite_schedule_store import SQLiteScheduleStore, StoredScheduleList
from src.controller import DesktopController
from src.domain.course import Course
from src.domain.schedule import Schedule

if TYPE_CHECKING:
    from src.ui.results_panel import _ResultsPanel


logger = logging.getLogger(__name__)


class ResultsLifecycleController:
    """Own result-set loading, streaming scaffolds, and cleanup."""

    def __init__(
        self,
        panel: "_ResultsPanel",
        *,
        merge_period_keys: Callable[
            [DesktopController, dict[str, list[Schedule]]],
            list[str],
        ],
        display_period_key: Callable[[str], str],
    ) -> None:
        self._panel = panel
        self._merge_period_keys = merge_period_keys
        self._display_period_key = display_period_key

    def load(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        truncated_periods: set[str] | None = None,
        read_only_import: bool = False,
    ) -> None:
        panel = self._panel
        panel.clear_stale()
        panel._is_imported_schedule = read_only_import
        panel._clear_favorites()
        panel._generation_thresholds = (
            None if read_only_import else panel._controller.settings.thresholds
        )

        # Stop in-flight work before cards/widgets are rebuilt.
        panel._lm.reset()
        panel._cleanup_ranking_worker(terminate=True)
        panel._set_ranking_busy(False)
        panel._clear_ranking_dirty()
        panel._streaming_run_active = False
        panel._streaming_auto_selected_period = False

        panel._controller.shutdown_load_workers()

        if read_only_import:
            panel._controller.reset_generation_state()

        courses_for_scoring = list(courses_by_id.values())
        selected_programs = panel._controller.selected_programs
        incoming_stores = {
            schedules.store
            for schedules in schedules_by_period.values()
            if isinstance(schedules, StoredScheduleList)
        }

        if incoming_stores:
            stored_by_period = self._adopt_stored_schedules(
                schedules_by_period,
                incoming_stores,
                courses_for_scoring,
                selected_programs,
            )
        elif read_only_import:
            stored_by_period = self._adopt_imported_schedules(schedules_by_period)
        else:
            stored_by_period = self._store_generated_schedules(
                schedules_by_period,
                courses_for_scoring,
                selected_programs,
            )

        panel._schedules_by_period = stored_by_period
        panel._courses_by_id = courses_by_id
        panel._prog_color_map = prog_color_map
        panel._truncated_periods = (
            set() if read_only_import else (truncated_periods or set())
        )
        panel._period_indices = {key: 0 for key in stored_by_period}
        panel._total_by_period = {}

        for key, schedules in stored_by_period.items():
            if key not in panel._truncated_periods:
                panel._total_by_period[key] = len(schedules)

        all_period_keys = self._merge_period_keys(
            panel._controller,
            stored_by_period,
        )
        merged: dict[str, list[Schedule]] = {key: [] for key in all_period_keys}
        merged.update(stored_by_period)

        panel._schedules_by_period = merged
        panel._period_indices = {key: 0 for key in merged}
        panel._nav_model.clear()
        panel._rebuild_navigation_cache()

        self._rebuild_period_tabs(merged)
        panel._refresh_period_selector(preferred_key=panel._first_period_with_results())

        has_proctor_report = any(
            panel._has_classroom_feature_results(period_key)
            for period_key, schedules in merged.items()
            if schedules
        )
        panel._proctor_btn.setVisible(has_proctor_report)

        panel._update_summary()
        panel._refresh_active_limits_panel()
        panel._placeholder.setVisible(False)
        panel._content.setVisible(True)
        panel._content.setGraphicsEffect(None)

    def begin_streaming(self) -> None:
        """Arm the panel for a fresh streaming run."""
        panel = self._panel
        panel.release_results(delete_db=True)
        panel._streaming_run_active = False
        panel._streaming_auto_selected_period = False

    def append_period(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        truncated_periods: set[str] | None = None,
    ) -> None:
        """Add one streamed batch of periods without clearing existing tabs."""
        panel = self._panel
        truncated = truncated_periods or set()

        if not panel._streaming_run_active:
            self.init_streaming_scaffold(courses_by_id, prog_color_map, truncated)
            panel._streaming_run_active = True

        current_period_key = panel._current_period_key()
        selector_needs_refresh = False

        panel._courses_by_id.update(courses_by_id)
        panel._truncated_periods |= truncated
        display_schedules_by_period = schedules_by_period

        incoming_stores = {
            schedules.store
            for schedules in schedules_by_period.values()
            if isinstance(schedules, StoredScheduleList)
        }
        if incoming_stores:
            display_schedules_by_period = self._adopt_streamed_store_batch(
                schedules_by_period,
                incoming_stores,
            )
        else:
            stored_by_period = self._store_streamed_batch(schedules_by_period)
            if stored_by_period is None:
                return
            display_schedules_by_period = (
                panel._controller.cache_generated_results_incremental(
                    stored_by_period
                )
            )

        for period_key, schedules in display_schedules_by_period.items():
            if period_key not in panel._schedules_by_period:
                panel._schedules_by_period[period_key] = []
                panel._period_indices[period_key] = 0
                panel._period_tabs.addTab(
                    panel._build_period_card(period_key),
                    self._display_period_key(period_key),
                )
                selector_needs_refresh = True

            panel._schedules_by_period[period_key] = schedules
            panel._period_indices.setdefault(period_key, 0)

            still_more = period_key in truncated
            panel._controller.set_has_more_for_period(period_key, still_more)
            if not still_more:
                panel._total_by_period[period_key] = len(schedules)

            panel._rebuild_navigation_cache(period_key)
            panel._refresh_period_card(period_key)

        if not panel._streaming_auto_selected_period:
            first_ready_period = panel._first_period_with_results()
            if first_ready_period is not None:
                panel._refresh_period_selector(preferred_key=first_ready_period)
                panel._streaming_auto_selected_period = True
            elif selector_needs_refresh:
                panel._refresh_period_selector(preferred_key=current_period_key)
        elif selector_needs_refresh:
            panel._refresh_period_selector(preferred_key=current_period_key)

        has_proctor_report = any(
            bool(getattr(schedule, "classroom_assignments", None))
            for schedules in panel._schedules_by_period.values()
            for schedule in schedules
        )
        if has_proctor_report:
            panel._proctor_btn.setVisible(True)

        panel._update_summary()

    def init_streaming_scaffold(
        self,
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        truncated_periods: set[str],
    ) -> None:
        """Build empty cards for every standard/loaded period on stream start."""
        panel = self._panel
        panel.clear_stale()
        panel._is_imported_schedule = False
        panel._clear_favorites()
        panel._generation_thresholds = panel._controller.settings.thresholds
        panel._streaming_auto_selected_period = False

        panel._lm.reset()
        panel._controller.shutdown_load_workers()

        panel._courses_by_id = dict(courses_by_id)
        panel._prog_color_map = prog_color_map
        panel._truncated_periods = set(truncated_periods)

        all_period_keys = self._merge_period_keys(panel._controller, {})
        panel._schedules_by_period = {key: [] for key in all_period_keys}
        panel._period_indices = {key: 0 for key in panel._schedules_by_period}
        panel._total_by_period = {}
        panel._nav_model.clear()
        panel._rebuild_navigation_cache()

        self._rebuild_period_tabs(panel._schedules_by_period)
        panel._refresh_period_selector()

        panel._proctor_btn.setVisible(False)
        panel._update_summary()
        panel._refresh_active_limits_panel()
        panel._placeholder.setVisible(False)
        panel._content.setVisible(True)
        panel._content.setGraphicsEffect(None)

    def release_results(self, *, delete_db: bool = True) -> None:
        """Release result DBs, caches, workers and generated-result UI state."""
        panel = self._panel
        if hasattr(panel, "_period_tip_bubble"):
            panel._period_tip_bubble.hide()

        panel._lm.reset()
        panel._cleanup_ranking_worker(terminate=True)
        heavy_kind = panel._controller.heavy_task_kind
        if heavy_kind in {"loading", "ranking"}:
            panel._controller.end_heavy_task(heavy_kind)
            if heavy_kind == "ranking":
                panel._finish_ranking_metrics()
            panel.heavy_task_state_changed.emit(heavy_kind, False)

        stores: set[SQLiteScheduleStore] = set()
        if panel._schedule_store is not None:
            stores.add(panel._schedule_store)
        for schedules in panel._schedules_by_period.values():
            if isinstance(schedules, StoredScheduleList):
                stores.add(schedules.store)
        for store in stores:
            try:
                store.close(delete=delete_db)
            except Exception:
                logger.debug("Failed closing result SQLite store", exc_info=True)

        panel._schedule_store = None
        panel._schedules_by_period.clear()
        panel._period_indices.clear()
        panel._truncated_periods.clear()
        panel._total_by_period.clear()
        panel._cell_data.clear()
        panel._nav_model.clear()
        panel._clear_favorites()
        panel._clear_ranking_dirty()
        panel._has_stale_results = False
        panel._is_imported_schedule = False
        panel._generation_thresholds = None
        panel._streaming_run_active = False
        panel._streaming_auto_selected_period = False

        if hasattr(panel, "_period_tabs"):
            panel._period_tabs.clear()
        panel._cards.clear()
        if hasattr(panel, "_summary_lbl"):
            panel._summary_lbl.setText("")
        if hasattr(panel, "_period_selector"):
            panel._period_selector.setVisible(False)
        if hasattr(panel, "_save_btn"):
            panel._save_btn.setEnabled(False)
        if hasattr(panel, "_proctor_btn"):
            panel._proctor_btn.setVisible(False)
            panel._proctor_btn.setEnabled(False)
        if hasattr(panel, "_stale_banner"):
            panel._stale_banner.setVisible(False)
        if hasattr(panel, "_placeholder"):
            panel._placeholder.setVisible(True)
        if hasattr(panel, "_content"):
            panel._content.setVisible(False)
        if delete_db:
            gc.collect()

    def _adopt_stored_schedules(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        incoming_stores: set[SQLiteScheduleStore],
        courses_for_scoring: list[Course],
        selected_programs: set[str],
    ) -> dict[str, list[Schedule]]:
        panel = self._panel
        if (
            panel._schedule_store is not None
            and panel._schedule_store not in incoming_stores
        ):
            panel._schedule_store.close(delete=True)

        panel._schedule_store = (
            next(iter(incoming_stores)) if len(incoming_stores) == 1 else None
        )
        stored_by_period: dict[str, list[Schedule]] = dict(schedules_by_period)

        for schedules in stored_by_period.values():
            if isinstance(schedules, StoredScheduleList):
                schedules.set_scoring_context(courses_for_scoring, selected_programs)
                schedules.set_sorting(panel._controller.settings.sorting)

        return stored_by_period

    def _adopt_imported_schedules(
        self,
        schedules_by_period: dict[str, list[Schedule]],
    ) -> dict[str, list[Schedule]]:
        panel = self._panel
        if panel._schedule_store is not None:
            panel._schedule_store.close(delete=True)
            panel._schedule_store = None
        return dict(schedules_by_period)

    def _store_generated_schedules(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        courses_for_scoring: list[Course],
        selected_programs: set[str],
    ) -> dict[str, list[Schedule]]:
        panel = self._panel
        if panel._schedule_store is not None:
            panel._schedule_store.close(delete=True)

        panel._schedule_store = SQLiteScheduleStore()
        stored_by_period: dict[str, list[Schedule]] = {}
        for key, schedules in schedules_by_period.items():
            panel._schedule_store.replace_period(
                key,
                schedules,
                courses=courses_for_scoring,
                selected_programs=selected_programs,
            )
            stored_by_period[key] = panel._schedule_store.as_sequence(
                key,
                courses=courses_for_scoring,
                selected_programs=selected_programs,
                sorting=panel._controller.settings.sorting,
            )

        return panel._controller.cache_generated_results(stored_by_period)

    def _adopt_streamed_store_batch(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        incoming_stores: set[SQLiteScheduleStore],
    ) -> dict[str, list[Schedule]]:
        panel = self._panel
        if panel._schedule_store is None and len(incoming_stores) == 1:
            panel._schedule_store = next(iter(incoming_stores))
        for schedules in schedules_by_period.values():
            if isinstance(schedules, StoredScheduleList):
                schedules.set_scoring_context(
                    list(panel._courses_by_id.values()),
                    panel._controller.selected_programs,
                )
                schedules.set_sorting(panel._controller.settings.sorting)
        return panel._controller.cache_generated_results_incremental(
            dict(schedules_by_period)
        )

    def _store_streamed_batch(
        self,
        schedules_by_period: dict[str, list[Schedule]],
    ) -> dict[str, list[Schedule]] | None:
        panel = self._panel
        if panel._schedule_store is None:
            panel._schedule_store = SQLiteScheduleStore()
        stored_by_period: dict[str, list[Schedule]] = {}
        try:
            for key, schedules in schedules_by_period.items():
                panel._schedule_store.replace_period(
                    key,
                    schedules,
                    courses=list(panel._courses_by_id.values()),
                    selected_programs=panel._controller.selected_programs,
                )
                stored_by_period[key] = panel._schedule_store.as_sequence(
                    key,
                    courses=list(panel._courses_by_id.values()),
                    selected_programs=panel._controller.selected_programs,
                    sorting=panel._controller.settings.sorting,
                )
        except (sqlite3.DatabaseError, OSError):
            logger.exception("Could not store streamed generation results")
            panel._show_message(
                "Storage Failed",
                "Could not store generated schedules because the temporary "
                "database or disk write failed. Already loaded schedules "
                "remain available.",
                QMessageBox.Icon.Warning,
            )
            return None

        return stored_by_period

    def _rebuild_period_tabs(self, schedules_by_period: dict[str, list[Schedule]]) -> None:
        panel = self._panel
        panel._period_tabs.clear()
        panel._cards.clear()
        panel._cell_data.clear()

        for period_key in schedules_by_period:
            panel._period_tabs.addTab(
                panel._build_period_card(period_key),
                self._display_period_key(period_key),
            )
