"""
Widget: _ResultsPanel — Schedule Results Tab
--------------------------------------------------------------
Shows one exam-period card per period with independent Prev/Next navigation.
Each card has a "Load More" button when more schedules exist beyond the initial
LOAD_BATCH_SIZE batch — clicking it spawns a background subprocess to fetch
only the next batch.

Public API:
    load(
        schedules_by_period,
        courses_by_id,
        prog_color_map,
        truncated_periods,
        read_only_import=False,
    )
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolButton,
    QWidget,
)

# _group_exams_by_slot is re-exported here for input_screen / tests.
from src.ui.calendar_cell_delegate import (
    _group_exams_by_slot,
)
from src.controller import DesktopController, LOAD_BATCH_SIZE
from src.adapters.sqlite_schedule_store import (
    SQLiteScheduleStore,
    StoredScheduleList,
)
from src.domain.course import Course
from src.domain.period_order import canonical_period_key
from src.domain.schedule import Schedule
from src.domain.semester import display_semester
from src.domain.sorting import SortingConfig
from src.domain.threshold import ThresholdSettings
from src.engine.generation_workers import ABSOLUTE_MAX_IN_MEMORY_SCHEDULES
from src.engine.mp_context import worker_context
from src.ui.active_limits_panel import ActiveLimitsPanel
from src.ui.favorite_schedules import FavoriteSchedule
from src.ui.result_ranking_controller import ResultRankingController
from src.ui.results_card_refresh_controller import ResultsCardRefreshController
from src.ui.navigation_model import NavigationModel, DateSignature as _DateSignature
from src.ui.period_card import PeriodCardWidgets
from src.ui.period_utils import STANDARD_PERIOD_ORDER as _STANDARD_PERIOD_ORDER
from src.ui.load_more_controller import LoadMoreController
from src.ui.period_navigator import PeriodNavigator
from src.ui.results_export_controller import ResultsExportController
from src.ui.results_layout_controller import ResultsLayoutController
from src.ui.results_lifecycle_controller import ResultsLifecycleController
from src.ui.results_shortlist_controller import (
    ResultsShortlistController,
)
from src.ui.results_status_controller import ResultsStatusController
from src.ui.results_period_selector_controller import ResultsPeriodSelectorController
from src.ui.results_proctor_report_controller import ResultsProctorReportController
from src.ui.result_summary_presenter import ResultSummaryPresenter
from src.ui.widgets.calendar_view import CalendarRenderer
from src.ui.widgets.period_card_builder import (
    build_period_card,
    _make_data_table,  # re-exported for input_screen / programme_courses_dialog
)

logger = logging.getLogger(__name__)
_RANKING_BUTTON_TEXT = "⇅  Result Ranking"

def _standard_period_keys() -> list[str]:
    return [
        f"{semester} - {moed}"
        for semester, moed in _STANDARD_PERIOD_ORDER
    ]



def _merge_period_keys(
    controller: DesktopController,
    schedules_by_period: dict[str, list[Schedule]],
) -> list[str]:
    """
    Return the period tabs that should be shown in the results screen.

    The standard semester/moed tabs are always shown for UI completeness, even
    when there are no schedules and even when the controller has no loaded
    periods. Controller periods and generated schedule keys are appended without
    duplicates.
    """
    keys: list[str] = []

    for key in _standard_period_keys():
        if key not in keys:
            keys.append(key)

    for period in sorted(
        controller.get_exam_periods(),
        key=lambda period: canonical_period_key(period.get_key()),
    ):
        key = period.get_key()
        if key not in keys:
            keys.append(key)

    for key in sorted(schedules_by_period, key=canonical_period_key):
        if key not in keys:
            keys.append(key)

    return keys


def _display_period_key(period_key: str) -> str:
    # TODO: team decision — tab label format (current: "FALL — Aleph"; alternatives: Hebrew convention)
    if " - " not in period_key:
        return period_key

    semester, moed = period_key.split(" - ", 1)
    return f"{display_semester(semester.strip())} — {moed.strip()}"


class _ResultsPanel(QWidget):
    """
    Tab 3 — Schedule Results.

    Each exam period is a card with its own Prev/Next navigator and an optional
    "Load More" button that fires a background subprocess to fetch the full set.

    When results are loaded from an exported schedule file, the panel switches
    into read-only imported mode. In that mode, users can browse the imported
    options, but Load More / Auto Load controls are hidden and no additional
    schedules are fetched.
    """

    heavy_task_state_changed = pyqtSignal(str, bool)

    def __init__(self, controller: DesktopController, parent=None):
        super().__init__(parent)

        self._controller = controller

        self._schedules_by_period: dict[str, list[Schedule]] = {}
        self._courses_by_id: dict[str, Course] = {}
        self._prog_color_map: dict[str, str] = {}
        self._period_indices: dict[str, int] = {}
        self._truncated_periods: set[str] = set()
        self._is_imported_schedule: bool = False
        self._generation_thresholds: ThresholdSettings | None = None
        self._schedule_store: SQLiteScheduleStore | None = None

        # Date/variant navigation indexing lives in a plain-Python model that
        # reads the panel's live schedules dict, so button clicks stay O(1)
        # without rescanning thousands of loaded schedules.
        self._nav_model = NavigationModel(lambda: self._schedules_by_period)
        self._calendar = CalendarRenderer(controller)

        # All per-period widgets (date/variant nav, calendar, loading buttons,
        # empty-state label) are bundled per period instead of in ~14 parallel
        # dicts. See src/ui/period_card.py.
        self._cards: dict[str, PeriodCardWidgets] = {}

        # Background load-more / Auto Dates / Auto Variants orchestration and all
        # its worker-state lives in a dedicated controller. See
        # src/ui/load_more_controller.py.
        self._lm = LoadMoreController(self)
        self._lm.messageRequested.connect(self._show_message)
        self._lm.cardRefreshRequested.connect(self._refresh_period_card)
        self._lm.cardCountersRefreshRequested.connect(
            self._refresh_period_card_counters
        )

        self._ranking_controller = ResultRankingController(
            self,
            worker_context_provider=lambda: worker_context(),
            ranking_button_text=_RANKING_BUTTON_TEXT,
        )
        self._ranking_dirty = False
        self._ranking_dirty_message: str | None = None
        self._summary_presenter = ResultSummaryPresenter()
        self._status = ResultsStatusController(self)
        self._lifecycle = ResultsLifecycleController(
            self,
            merge_period_keys=_merge_period_keys,
            display_period_key=_display_period_key,
        )
        self._layout = ResultsLayoutController(
            self,
            ranking_button_text=_RANKING_BUTTON_TEXT,
        )
        self._favorite_schedules: list[FavoriteSchedule] = []
        self._shortlist = ResultsShortlistController(
            self,
            display_period_key=_display_period_key,
        )
        self._export_controller = ResultsExportController(self, self._shortlist)
        self._shortlist.set_export_shortlisted(
            self._export_controller.export_shortlisted_schedules
        )
        self._proctor_report_controller = ResultsProctorReportController(
            self,
            display_period_key=_display_period_key,
        )
        self._period_selector_controller = ResultsPeriodSelectorController(
            self,
            display_period_key=_display_period_key,
        )
        self._card_refresh = ResultsCardRefreshController(
            self,
            display_period_key=_display_period_key,
        )

        self._navigator = PeriodNavigator(
            self._nav_model,
            self._cards,
            get_schedules=lambda: self._schedules_by_period,
            get_indices=lambda: self._period_indices,
            has_more=lambda period_key: (
                False
                if self._is_imported_schedule
                else self._controller.has_more_schedules(period_key)
            ),
            parent=self,
        )
        self._navigator.navigationRequested.connect(self._on_navigation_requested)
        self._navigator.messageRequested.connect(self._show_message)
        self._navigator.loadMoreDatesRequested.connect(
            self._on_navigator_load_more_dates
        )

        self._total_by_period: dict[str, int] = {}
        self._cell_data: dict[str, dict[tuple[int, int], tuple]] = {}

        self._has_stale_results: bool = False

        # True once the first streamed period of the current run has built the
        # tab scaffold. Reset by begin_streaming() at the start of each run.
        self._streaming_run_active: bool = False

        # Per-period Auto Load is user-controlled. It loads one batch, waits an
        # adaptive delay, then requests the next batch until there is no more data
        # or the user presses Stop Auto Load. Never use a blocking while-loop.
        self._stale_banner: QLabel = QLabel()
        self._limits_panel: ActiveLimitsPanel = ActiveLimitsPanel()
        self._limits_toggle: QToolButton = QToolButton()
        self._limits_details: QLabel = QLabel()
        self._save_favorite_btn: QPushButton = QPushButton()
        self._favorites_btn: QPushButton = QPushButton()
        self._period_selector: QWidget = QWidget()
        self._period_tip_btn: QToolButton = QToolButton()
        self._period_tip_bubble: QLabel = QLabel()
        self._semester_combo: QComboBox = QComboBox()
        self._moed_combo: QComboBox = QComboBox()
        self._save_btn: QPushButton = QPushButton()

        self._setup_ui()

    @property
    def _ranking_proc(self):
        return self._ranking_controller.proc

    @_ranking_proc.setter
    def _ranking_proc(self, value) -> None:
        self._ranking_controller.proc = value

    @property
    def _ranking_queue(self):
        return self._ranking_controller.queue

    @_ranking_queue.setter
    def _ranking_queue(self, value) -> None:
        self._ranking_controller.queue = value

    @property
    def _ranking_timer(self):
        return self._ranking_controller.timer

    @_ranking_timer.setter
    def _ranking_timer(self, value) -> None:
        self._ranking_controller.timer = value

    @property
    def _ranking_config(self) -> SortingConfig | None:
        return self._ranking_controller.config

    @_ranking_config.setter
    def _ranking_config(self, value: SortingConfig | None) -> None:
        self._ranking_controller.config = value

    @property
    def _ranking_button_text(self) -> str | None:
        return self._ranking_controller.button_text

    @_ranking_button_text.setter
    def _ranking_button_text(self, value: str | None) -> None:
        self._ranking_controller.button_text = value

    @property
    def _ranking_empty_after_exit_ticks(self) -> int:
        return self._ranking_controller.empty_after_exit_ticks

    @_ranking_empty_after_exit_ticks.setter
    def _ranking_empty_after_exit_ticks(self, value: int) -> None:
        self._ranking_controller.empty_after_exit_ticks = value

    def mark_stale(self) -> None:
        self._status.mark_stale()

    def clear_stale(self) -> None:
        self._status.clear_stale()

    def _is_stale(self) -> bool:
        return self._status.is_stale()

    def load(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        truncated_periods: set[str] | None = None,
        read_only_import: bool = False,
    ) -> None:
        self._lifecycle.load(
            schedules_by_period,
            courses_by_id,
            prog_color_map,
            truncated_periods,
            read_only_import,
        )

    def begin_streaming(self) -> None:
        self._lifecycle.begin_streaming()

    def append_period(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        truncated_periods: set[str] | None = None,
    ) -> None:
        self._lifecycle.append_period(
            schedules_by_period,
            courses_by_id,
            prog_color_map,
            truncated_periods,
        )

    def _init_streaming_scaffold(
        self,
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        truncated_periods: set[str],
    ) -> None:
        self._lifecycle.init_streaming_scaffold(
            courses_by_id,
            prog_color_map,
            truncated_periods,
        )

    def _on_navigation_requested(self, period_key: str, index: int) -> None:
        """Slot: apply a navigator-requested schedule index to own state."""
        self._period_indices[period_key] = index
        self._refresh_period_card(period_key)

    def _on_navigator_load_more_dates(self, period_key: str) -> None:
        """Slot: load the next date-options batch and advance once it arrives."""
        if self._is_imported_schedule:
            return

        self._lm.advance_after_load.add(period_key)
        self._lm.on_load_more(period_key)

    def append_loaded_schedules(
        self,
        period_key: str,
        extra: list[Schedule],
    ) -> dict[str, float]:
        """Merge a freshly loaded batch into this period's own schedule state.

        Owned by the panel so the load-more controller never mutates the panel's
        private dicts directly. Keeps the navigation cache and the controller's
        cached results in sync (so a later re-sort includes the appended batch).
        """
        timings = {
            "sqlite_insert_seconds": 0.0,
            "navigation_update_seconds": 0.0,
            "summary_update_seconds": 0.0,
        }
        if self._is_imported_schedule:
            return timings

        prev_len = len(self._schedules_by_period[period_key])
        insert_started_at = time.perf_counter()
        self._schedules_by_period[period_key].extend(extra)
        insert_seconds = time.perf_counter() - insert_started_at
        if self._schedule_store is not None:
            timings["sqlite_insert_seconds"] = insert_seconds

        # Keep the appended schedules cached, but do not re-sort the whole
        # result set on every Load More / Auto Load batch. Surface that the
        # displayed order may now be partially unsorted until the user re-ranks.
        self._schedules_by_period = self._controller.cache_loaded_results_without_reranking(
            dict(self._schedules_by_period)
        )
        self._period_indices[period_key] = min(
            self._period_indices.get(period_key, 0),
            max(0, len(self._schedules_by_period[period_key]) - 1),
        )
        nav_started_at = time.perf_counter()
        self._append_navigation_cache(period_key, prev_len, len(extra))
        timings["navigation_update_seconds"] = time.perf_counter() - nav_started_at

        summary_started_at = time.perf_counter()
        self.mark_ranking_dirty("New results loaded. Re-rank to apply sorting.")
        timings["summary_update_seconds"] = time.perf_counter() - summary_started_at

        logger.info(
            "Load batch merge timings: period=%s batch_size=%s "
            "sqlite_insert_seconds=%.3fs navigation_update_seconds=%.3fs "
            "summary_update_seconds=%.3fs",
            period_key,
            len(extra),
            timings["sqlite_insert_seconds"],
            timings["navigation_update_seconds"],
            timings["summary_update_seconds"],
        )
        return timings

    def advance_to_next_date_option(self, period_key: str, prev_len: int) -> None:
        """Move the displayed index to the next date option after a load.

        ``prev_len`` is the schedule count before the batch was merged; it is the
        index of the first newly appended schedule when no navigation position is
        available yet.
        """
        if self._is_imported_schedule:
            return

        options = self._date_options_for_period(period_key)
        current_idx = self._period_indices.get(period_key, 0)
        nav_pos = self._nav_position_for_index(period_key, current_idx)

        if nav_pos is not None:
            date_pos, _variant_pos = nav_pos
            if date_pos < len(options) - 1:
                self._period_indices[period_key] = options[date_pos + 1][1][0]
        elif prev_len < len(self._schedules_by_period[period_key]):
            self._period_indices[period_key] = prev_len

    def set_period_truncated(self, period_key: str, still_more: bool) -> None:
        """Record whether more date options remain for a period after a load."""
        if self._is_imported_schedule:
            self._controller.set_has_more_for_period(period_key, False)
            self._truncated_periods.discard(period_key)
            return

        self._controller.set_has_more_for_period(period_key, still_more)
        if still_more:
            self._truncated_periods.add(period_key)
        else:
            self._truncated_periods.discard(period_key)
            self._total_by_period[period_key] = len(
                self._schedules_by_period[period_key]
            )

    # ------------------------------------------------------------------
    # Public accessors for collaborators (e.g. LoadMoreController).
    #
    # These let the load-more controller query the panel's live schedule and
    # navigation state without reaching into its private dicts (no Feature Envy /
    # tight coupling). Each one is a thin, read-only delegate.
    # ------------------------------------------------------------------
    @property
    def controller(self) -> DesktopController:
        """The DesktopController backing this panel."""
        return self._controller

    def active_schedule_store_path(self) -> Path | None:
        """Return the active SQLite DB path used for resource checks."""
        if self._schedule_store is not None:
            return self._schedule_store.path
        for schedules in self._schedules_by_period.values():
            if isinstance(schedules, StoredScheduleList):
                return schedules.store.path
        return None

    def has_period(self, period_key: str) -> bool:
        """Return True if *period_key* is a known period even if empty."""
        return period_key in self._schedules_by_period

    def get_schedules(self, period_key: str) -> list[Schedule]:
        """Return the loaded schedules for *period_key* or an empty list."""
        return self._schedules_by_period.get(period_key, [])

    def has_results(self) -> bool:
        """Return True when at least one displayed period has schedules."""
        return any(bool(schedules) for schedules in self._schedules_by_period.values())

    def mark_ranking_dirty(self, message: str) -> None:
        self._status.mark_ranking_dirty(message)

    def show_workload_status(self, message: str) -> None:
        self._status.show_workload_status(message)

    def _on_limits_toggled(self, expanded: bool) -> None:
        self._status.on_limits_toggled(expanded)

    def _refresh_active_limits_panel(self) -> None:
        self._status.refresh_active_limits_panel()

    def _clear_ranking_dirty(self) -> None:
        self._status.clear_ranking_dirty()

    def _sync_ranking_dirty_state(self) -> None:
        self._status.sync_ranking_dirty_state()

    def total_in_memory_schedule_count(self) -> int:
        """Return loaded schedule count kept by the active result container.

        With the SQLite-backed store this is a stored-count, not a count of
        Schedule objects resident in RAM.  The name is kept for compatibility
        with LoadMoreController/tests.
        """
        return sum(len(scheds) for scheds in self._schedules_by_period.values())

    def is_at_memory_cap(self) -> bool:
        """Return True if a legacy in-memory result container reaches its cap."""
        if ABSOLUTE_MAX_IN_MEMORY_SCHEDULES is None:
            return False
        return self.total_in_memory_schedule_count() >= ABSOLUTE_MAX_IN_MEMORY_SCHEDULES

    def get_current_index(self, period_key: str) -> int:
        """Return the currently displayed schedule index for *period_key*."""
        return self._period_indices.get(period_key, 0)

    def get_card(self, period_key: str) -> PeriodCardWidgets | None:
        """Return the period card widgets for *period_key*, if built."""
        return self._cards.get(period_key)

    def _clear_favorites(self) -> None:
        self._shortlist.clear_favorites()

    def _refresh_shortlist_labels(self) -> None:
        self._shortlist.refresh_shortlist_labels()

    def _favorite_label(self, period_key: str, index: int) -> str:
        return self._shortlist.favorite_label(period_key, index)

    def _current_shortlist_row(self) -> int | None:
        return self._shortlist.current_shortlist_row()

    def _toggle_current_favorite(self, period_key: str) -> None:
        self._shortlist.toggle_current_favorite(period_key)

    def _save_current_favorite(self, period_key: str) -> None:
        self._shortlist.save_current_favorite(period_key)

    def _save_visible_favorite(self) -> None:
        self._shortlist.save_visible_favorite()

    def _toggle_visible_favorite(self) -> None:
        self._shortlist.toggle_visible_favorite()

    def _delete_favorite_at(self, row: int) -> bool:
        return self._shortlist.delete_favorite_at(row)

    def _refresh_favorite_buttons(self, saved_period_key: str | None = None) -> None:
        self._shortlist.refresh_favorite_buttons(saved_period_key)

    def _show_favorites_dialog(self) -> None:
        self._shortlist.show_favorites_dialog()

    def _open_favorite_at(self, row: int, close_dialog=None) -> bool:
        return self._shortlist.open_favorite_at(row, close_dialog=close_dialog)

    def _schedule_for_shortlist_row(self, row: int) -> tuple[FavoriteSchedule, Schedule] | None:
        return self._shortlist.schedule_for_shortlist_row(row)

    def _shortlisted_schedule_selection(self) -> dict[str, list[Schedule]] | None:
        return self._shortlist.shortlisted_schedule_selection()

    def _export_shortlisted_schedules(self, close_dialog=None) -> bool:
        return self._export_controller.export_shortlisted_schedules(
            close_dialog=close_dialog
        )

    def _export_favorite_at(self, row: int, close_dialog=None) -> bool:
        return self._export_controller.export_favorite_at(
            row,
            close_dialog=close_dialog,
        )

    def _show_missing_favorite_message(self) -> None:
        self._shortlist.show_missing_favorite_message()

    def get_truncated_periods(self) -> set[str]:
        """Return a copy of the periods that still have more schedules to load."""
        return set(self._truncated_periods)

    def is_imported_schedule_view(self) -> bool:
        """Return True when results came from Load Schedule, not Generate."""
        return self._is_imported_schedule

    def has_classroom_results(self, period_key: str) -> bool:
        """Return True if the loaded period contains Feature 4 classroom data."""
        return self._has_classroom_feature_results(period_key)

    def signature_of(self, schedule: Schedule) -> _DateSignature:
        """Return the date-only signature of *schedule*."""
        return self._date_signature(schedule)

    def get_current_signature(self, period_key: str) -> _DateSignature | None:
        """Return the date signature of the currently displayed schedule.

        Returns ``None`` when the period has no schedules or the current index
        is out of range.
        """
        schedules = self._schedules_by_period.get(period_key, [])
        if not schedules:
            return None

        idx = self._period_indices.get(period_key, 0)
        if 0 <= idx < len(schedules):
            return self._date_signature(schedules[idx])

        return None

    def get_date_option_count(self, period_key: str) -> int:
        """Return how many distinct date options are currently loaded."""
        return len(self._date_options_for_period(period_key))

    def get_variant_index_count(
        self,
        period_key: str,
        signature: _DateSignature,
    ) -> int:
        """Return how many loaded variants share *signature* in *period_key*."""
        return len(self._indices_for_signature(period_key, signature))

    def release_results(self, *, delete_db: bool = True) -> None:
        self._lifecycle.release_results(delete_db=delete_db)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override name
        self.release_results(delete_db=True)
        super().closeEvent(event)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt override name
        if obj is self._period_tip_btn:
            if event.type() == QEvent.Type.Enter:
                self._show_period_tip()
            elif event.type() in (
                QEvent.Type.Leave,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.Hide,
            ):
                self._period_tip_bubble.hide()

        return super().eventFilter(obj, event)

    def _show_period_tip(self) -> None:
        self._layout.show_period_tip()

    def _setup_ui(self) -> None:
        self._layout.setup_ui()

    def _build_period_card(self, period_key: str) -> QWidget:
        return build_period_card(self, period_key)

    @staticmethod
    def _date_signature(schedule: Schedule) -> _DateSignature:
        """Date-only identity of a schedule, ignoring Feature 4 variants."""
        return NavigationModel.date_signature(schedule)

    @staticmethod
    def _schedule_has_classroom_data(schedule: Schedule) -> bool:
        """Return True when Feature 4 classroom data exists on this schedule."""
        return bool(
            getattr(schedule, "classroom_assignments", None)
            or getattr(schedule, "unassigned_classroom_exams", None)
        )

    def _has_classroom_feature_results(self, period_key: str) -> bool:
        """Return True if the loaded period contains classroom-assignment data.

        For SQLite-backed periods this uses a metadata query instead of scanning
        and unpickling every stored Schedule.
        """
        schedules = self._schedules_by_period.get(period_key, [])
        if isinstance(schedules, StoredScheduleList):
            return schedules.has_classroom_data()
        return any(self._schedule_has_classroom_data(schedule) for schedule in schedules)

    def _rebuild_navigation_cache(self, period_key: str | None = None) -> None:
        """Rebuild navigation indexes through NavigationModel."""
        self._nav_model.rebuild(period_key)

    def _append_navigation_cache(
        self,
        period_key: str,
        start_index: int,
        count: int,
    ) -> None:
        """Append navigation indexes through NavigationModel."""
        self._nav_model.append_entries(period_key, start_index, count)

    def _date_options_for_period(
        self,
        period_key: str,
    ) -> list[tuple[_DateSignature, list[int]]]:
        """Return cached date options through NavigationModel."""
        return self._nav_model.date_options(period_key)

    def _period_key_at_tab_index(self, index: int) -> str | None:
        return self._period_selector_controller.period_key_at_tab_index(index)

    @staticmethod
    def _period_parts(period_key: str) -> tuple[str, str]:
        return ResultsPeriodSelectorController.period_parts(period_key)

    def _period_keys_for_semester(self, semester: str) -> list[str]:
        return self._period_selector_controller.period_keys_for_semester(semester)

    def _period_keys_for_selector(self) -> list[str]:
        return self._period_selector_controller.period_keys_for_selector()

    def _first_period_with_results(self) -> str | None:
        return self._period_selector_controller.first_period_with_results()

    def _refresh_period_selector(self, preferred_key: str | None = None) -> None:
        self._period_selector_controller.refresh_period_selector(preferred_key)

    def _populate_moed_selector(
        self,
        semester: str,
        preferred_key: str | None = None,
    ) -> None:
        self._period_selector_controller.populate_moed_selector(
            semester,
            preferred_key,
        )

    def _select_period_key(self, period_key: str) -> None:
        self._period_selector_controller.select_period_key(period_key)

    def _on_period_semester_changed(self, _index: int) -> None:
        self._period_selector_controller.on_period_semester_changed(_index)

    def _on_period_moed_changed(self, _index: int) -> None:
        self._period_selector_controller.on_period_moed_changed(_index)

    def _current_period_key(self) -> str | None:
        return self._period_selector_controller.current_period_key()

    def _on_period_tab_changed(self, index: int) -> None:
        self._period_selector_controller.on_period_tab_changed(index)

    def _nav_position_for_index(
        self,
        period_key: str,
        idx: int,
    ) -> tuple[int, int] | None:
        """Return (date option position, variant position) for a schedule index."""
        return self._nav_model.nav_position(period_key, idx)

    def _ordered_date_signatures(self, period_key: str) -> list[_DateSignature]:
        """Return loaded date-level schedule options in first-seen order."""
        return self._nav_model.ordered_signatures(period_key)

    def _indices_for_signature(
        self,
        period_key: str,
        signature: _DateSignature,
    ) -> list[int]:
        """Return loaded schedule indexes that share the same exam dates."""
        return self._nav_model.indices_for_signature(period_key, signature)

    def _refresh_period_card(self, period_key: str) -> None:
        self._card_refresh.refresh_period_card(period_key)

    def _refresh_period_card_counters(self, period_key: str) -> None:
        self._card_refresh.refresh_period_card_counters(period_key)

    def _refresh_period_card_ui(
        self,
        period_key: str,
        *,
        repaint_calendar: bool,
    ) -> None:
        self._card_refresh.refresh_period_card_ui(
            period_key,
            repaint_calendar=repaint_calendar,
        )

    def _update_summary(self) -> None:
        self._status.update_summary()

    def _on_cell_clicked(
        self,
        period_key: str,
        row: int,
        col: int,
        click_pos: QPoint | None = None,
    ) -> None:
        self._card_refresh.on_cell_clicked(period_key, row, col, click_pos)

    def _slot_filter_for_click(
        self,
        period_key: str,
        row: int,
        col: int,
        groups: "list[dict] | None",
        click_pos: QPoint | None = None,
    ) -> "list[str] | None":
        return self._card_refresh.slot_filter_for_click(
            period_key,
            row,
            col,
            groups,
            click_pos,
        )

    def _show_message(
        self,
        title: str,
        text: str,
        icon: QMessageBox.Icon,
    ) -> None:
        """Show a readable dark-themed message box."""
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setIcon(icon)
        msg.setText(text)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #111827;
            }

            QMessageBox QLabel {
                color: #FFFFFF;
                font-size: 13px;
                background: transparent;
            }

            QMessageBox QPushButton {
                background-color: transparent;
                color: #FFFFFF;
                border: 1px solid #2563EB;
                border-radius: 8px;
                padding: 6px 18px;
                min-width: 72px;
                min-height: 28px;
            }

            QMessageBox QPushButton:hover {
                background-color: #2563EB;
                color: #FFFFFF;
            }
        """)
        msg.exec()

    def _selected_schedules(self) -> dict[str, Schedule]:
        """Currently displayed schedule per period, one each.

        Guards the per-period index against missing keys and out-of-range
        values so a stale or unset index can never raise IndexError/KeyError;
        such a period is simply skipped.
        """
        selected: dict[str, Schedule] = {}

        for key, schedules in self._schedules_by_period.items():
            if not schedules:
                continue

            idx = self._period_indices.get(key, 0)
            if 0 <= idx < len(schedules):
                selected[key] = schedules[idx]

        return selected

    def _on_result_ranking(self) -> None:
        self._ranking_controller.on_result_ranking()

    def _apply_ranking(self, config: "SortingConfig") -> None:
        self._ranking_controller.apply_ranking(config)

    def _poll_ranking_worker(self) -> None:
        self._ranking_controller.poll_ranking_worker()

    def _finish_ranking_success(
        self,
        resorted: dict[str, list[Schedule]],
    ) -> None:
        self._ranking_controller.finish_ranking_success(resorted)

    def _set_ranking_busy(self, busy: bool) -> None:
        self._ranking_controller.set_ranking_busy(busy)

    def _cleanup_ranking_worker(self, terminate: bool = False) -> None:
        self._ranking_controller.cleanup_ranking_worker(terminate=terminate)

    def is_ranking_active(self) -> bool:
        return self._ranking_controller.is_ranking_active()

    def _begin_heavy_task(self, kind: str) -> bool:
        """Reserve the shared heavy-task slot and refresh visible controls."""
        if not self._controller.begin_heavy_task(kind):
            return False
        if kind == "ranking":
            self._controller.performance_metrics.start_ranking()
        self.heavy_task_state_changed.emit(kind, True)
        self._refresh_heavy_task_controls()
        return True

    def _end_heavy_task(self, kind: str, *, repaint_calendar: bool = True) -> None:
        """Release the shared heavy-task slot and refresh visible controls."""
        if self._controller.end_heavy_task(kind):
            if kind == "ranking":
                self._finish_ranking_metrics()
            self.heavy_task_state_changed.emit(kind, False)
        self._refresh_heavy_task_controls(repaint_calendar=repaint_calendar)

    def _finish_ranking_metrics(self) -> None:
        self._ranking_controller.finish_ranking_metrics()

    def _refresh_heavy_task_controls(self, *, repaint_calendar: bool = True) -> None:
        """Refresh ranking/load controls after heavy-task state changes."""
        self._set_ranking_busy(self._ranking_proc is not None)
        current = self._current_period_key()
        if current is not None and current in self._cards:
            if repaint_calendar:
                self._refresh_period_card(current)
            else:
                self._refresh_period_card_counters(current)

    def sync_heavy_task_state(self) -> None:
        """Public hook for the parent screen to refresh controls after generation."""
        self._refresh_heavy_task_controls()

    def _on_proctor_report(self) -> None:
        self._proctor_report_controller.on_proctor_report()

    def _export_schedule_selection(self, selected_by_period: dict[str, list[Schedule]]) -> bool:
        return self._export_controller.export_schedule_selection(selected_by_period)

    def _on_save(self) -> None:
        self._export_controller.on_save()
