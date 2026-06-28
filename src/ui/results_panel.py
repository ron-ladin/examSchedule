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
import multiprocessing
from pathlib import Path
from queue import Empty as _QueueEmpty

from PyQt6.QtCore import QEvent, QPoint, QSignalBlocker, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.assets.animated_widgets import AnimatedPlaceholder

# _group_exams_by_slot is re-exported here for input_screen / tests.
from src.ui.calendar_cell_delegate import (
    _course_ids_for_click_position,
    _group_exams_by_slot,
)
from src.ui.tokens import PERIOD_TAB_STYLE

from src.controller import DesktopController, LOAD_BATCH_SIZE
from src.adapters.sqlite_schedule_store import (
    ABSOLUTE_MAX_STORED_SCHEDULES,
    SQLiteScheduleStore,
    StoredScheduleList,
)
from src.domain.course import Course
from src.domain.period_order import canonical_period_key
from src.domain.schedule import Schedule
from src.domain.semester import display_semester
from src.domain.sorting import SortingConfig
from src.domain.threshold import Criterion, ThresholdEntry, ThresholdSettings
from src.engine.generation_workers import ABSOLUTE_MAX_IN_MEMORY_SCHEDULES
from src.engine.ranking_worker import RankingWorkerResult, run_ranking_worker
from src.ui.navigation_model import NavigationModel, DateSignature as _DateSignature
from src.ui.period_card import PeriodCardWidgets
from src.ui.period_utils import STANDARD_PERIOD_ORDER as _STANDARD_PERIOD_ORDER
from src.ui.load_more_controller import LoadMoreController
from src.ui.period_navigator import PeriodNavigator
from src.ui.result_summary_presenter import ResultSummaryPresenter
from src.ui.widgets.calendar_view import CalendarRenderer
from src.ui.widgets.period_card_builder import (
    build_period_card,
    _make_data_table,  # re-exported for input_screen / programme_courses_dialog
)

logger = logging.getLogger(__name__)
_THRESHOLD_LABELS: dict[Criterion, tuple[str, str]] = {
    Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS: (
        "Mandatory exam gap",
        "at least {k} day(s) between mandatory exams",
    ),
    Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS: (
        "Any exam gap",
        "at least {k} day(s) between any two exams",
    ),
    Criterion.MAX_ELECTIVE_COLLISIONS: (
        "Elective collisions",
        "at most {k} same-day elective collision(s)",
    ),
    Criterion.MIN_DAYS_EXAM_PERIOD_SPREAD: (
        "Exam-period spread",
        "at least {k} day(s) from first to last mandatory exam",
    ),
    Criterion.MAX_EXAMS_PER_DAY: (
        "Exams per day",
        "at most {k} exam(s) on one day",
    ),
}
_RANKING_EXIT_QUEUE_GRACE_TICKS = 3
_RANKING_BUTTON_TEXT = "⇅  Result Ranking"


def _standard_period_keys() -> list[str]:
    return [
        f"{semester} - {moed}"
        for semester, moed in _STANDARD_PERIOD_ORDER
    ]


def _active_threshold_entries(
    thresholds: ThresholdSettings,
) -> list[ThresholdEntry]:
    """Return enabled threshold entries in the domain enum order."""
    by_criterion = {entry.criterion: entry for entry in thresholds.entries}
    return [
        by_criterion[criterion]
        for criterion in Criterion
        if criterion in by_criterion and by_criterion[criterion].enabled
    ]


def _format_threshold_entry(entry: ThresholdEntry) -> str:
    """Human-readable summary for one active scheduling limit."""
    title, detail_template = _THRESHOLD_LABELS[entry.criterion]
    return f"{title}: {detail_template.format(k=entry.k)}"


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


_AUTO_MODE_DATES = "dates"
_AUTO_MODE_VARIANTS = "variants"


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
    into read-only imported mode. In that mode, navigation/load-more controls are
    hidden by the period-card builder and no additional schedules are fetched.
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

        self._ranking_proc: multiprocessing.Process | None = None
        self._ranking_queue: multiprocessing.Queue | None = None
        self._ranking_timer: QTimer | None = None
        self._ranking_config: SortingConfig | None = None
        self._ranking_button_text: str | None = None
        self._ranking_empty_after_exit_ticks = 0
        self._ranking_dirty = False
        self._ranking_dirty_message: str | None = None
        self._summary_presenter = ResultSummaryPresenter()
        self._favorite_schedules: list[dict[str, int | str]] = []

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

        # Per-period Auto Load is user-controlled. It loads one batch, waits
        # AUTO_LOAD_DELAY_MS, then requests the next batch until there is no more
        # data or the user presses Stop Auto Load. Never use a blocking while-loop.
        self._stale_banner: QLabel = QLabel()
        self._limits_panel: QWidget = QWidget()
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

    def mark_stale(self) -> None:
        """Show the stale-data warning and disable schedule/report exports."""
        self._has_stale_results = True
        self._stale_banner.setVisible(True)
        self._save_btn.setEnabled(False)
        self._proctor_btn.setEnabled(False)
        self._update_summary()

    def clear_stale(self) -> None:
        """Hide the stale-data warning and re-enable Export."""
        self._has_stale_results = False
        self._stale_banner.setVisible(False)
        self._save_btn.setEnabled(True)
        self._proctor_btn.setEnabled(True)
        self._update_summary()

    def _is_stale(self) -> bool:
        """True if displayed results are stale per the panel OR the controller.

        The panel's own flag tracks period-date edits, but threshold changes go
        straight to the controller (apply_settings -> mark_results_stale) without
        the panel necessarily being told. Consulting the controller too ensures a
        threshold change immediately blocks every action that would otherwise act
        on the now-invalid displayed schedules.
        """
        return self._has_stale_results or self._controller.results_stale

    def load(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        truncated_periods: set[str] | None = None,
        read_only_import: bool = False,
    ) -> None:
        self.clear_stale()
        self._is_imported_schedule = read_only_import
        self._clear_favorites()
        self._generation_thresholds = (
            None if read_only_import else self._controller.settings.thresholds
        )

        # Stop any in-flight Load More operation before rebuilding the results UI.
        # A QTimer timeout may already be queued while a new generation/load starts,
        # so cleanup must happen before old cards/widgets are removed.
        self._lm.reset()
        self._cleanup_ranking_worker(terminate=True)
        self._set_ranking_busy(False)
        self._clear_ranking_dirty()

        # Stop idle persistent load-more workers from the previous result set.
        # They will be recreated lazily if the user clicks Load More / Auto again.
        self._controller.shutdown_load_workers()

        # Imported schedules are fixed read-only snapshots. Do not keep any
        # old generation/load-more state from a previous Generate run.
        if read_only_import:
            self._controller.reset_generation_state()

        courses_for_scoring = list(courses_by_id.values())
        selected_programs = self._controller.selected_programs
        incoming_stores = {
            schedules.store
            for schedules in schedules_by_period.values()
            if isinstance(schedules, StoredScheduleList)
        }

        if incoming_stores:
            # The schedules are already backed by SQLite. Adopt the existing
            # StoredScheduleList facades directly; never close/recreate the store
            # that backs them. This keeps Result Ranking and repeated Generate
            # flows from invalidating live views.
            if self._schedule_store is not None and self._schedule_store not in incoming_stores:
                self._schedule_store.close(delete=True)

            self._schedule_store = next(iter(incoming_stores)) if len(incoming_stores) == 1 else None
            stored_by_period: dict[str, list[Schedule]] = dict(schedules_by_period)

            for schedules in stored_by_period.values():
                if isinstance(schedules, StoredScheduleList):
                    schedules.set_scoring_context(courses_for_scoring, selected_programs)
                    schedules.set_sorting(self._controller.settings.sorting)

        elif read_only_import:
            # Imported files are small, fixed snapshots and should remain a simple
            # read-only in-memory view. Do not create a temporary SQLite store just
            # to display them.
            if self._schedule_store is not None:
                self._schedule_store.close(delete=True)
                self._schedule_store = None
            stored_by_period = dict(schedules_by_period)

        else:
            # Fresh subprocess generation returns bounded plain lists. Move them
            # into one panel-owned SQLite store, then cache those StoredScheduleList
            # facades in the controller so future Result Ranking does not copy the
            # data back and forth between RAM and SQLite.
            if self._schedule_store is not None:
                self._schedule_store.close(delete=True)

            self._schedule_store = SQLiteScheduleStore()
            stored_by_period = {}
            for key, scheds in schedules_by_period.items():
                self._schedule_store.replace_period(
                    key,
                    scheds,
                    courses=courses_for_scoring,
                    selected_programs=selected_programs,
                )
                stored_by_period[key] = self._schedule_store.as_sequence(
                    key,
                    courses=courses_for_scoring,
                    selected_programs=selected_programs,
                    sorting=self._controller.settings.sorting,
                )

            stored_by_period = self._controller.cache_generated_results(stored_by_period)

        self._schedules_by_period = stored_by_period
        self._courses_by_id = courses_by_id
        self._prog_color_map = prog_color_map
        self._truncated_periods = set() if read_only_import else (truncated_periods or set())
        self._period_indices = {k: 0 for k in stored_by_period}
        self._total_by_period = {}

        for key, scheds in stored_by_period.items():
            if key not in self._truncated_periods:
                self._total_by_period[key] = len(scheds)

        all_period_keys = _merge_period_keys(self._controller, stored_by_period)
        merged: dict[str, list[Schedule]] = {k: [] for k in all_period_keys}
        merged.update(stored_by_period)

        self._schedules_by_period = merged
        self._period_indices = {k: 0 for k in merged}
        self._nav_model.clear()
        self._rebuild_navigation_cache()

        self._period_tabs.clear()
        self._cards.clear()
        self._cell_data.clear()

        for period_key in merged:
            self._period_tabs.addTab(
                self._build_period_card(period_key),
                _display_period_key(period_key),
            )
        self._refresh_period_selector(preferred_key=self._first_period_with_results())

        has_proctor_report = any(
            self._has_classroom_feature_results(period_key)
            for period_key, schedules in merged.items()
            if schedules
        )
        self._proctor_btn.setVisible(has_proctor_report)

        self._update_summary()
        self._refresh_active_limits_panel()
        self._placeholder.setVisible(False)
        self._content.setVisible(True)

        # Avoid opacity effects while rebuilding result widgets.
        # QGraphicsOpacityEffect caused QPainter warnings and visual flicker.
        self._content.setGraphicsEffect(None)

    def begin_streaming(self) -> None:
        """Arm the panel for a fresh streaming run.

        The first ``append_period`` after this builds the tab scaffold from
        scratch, so a previous run's cards/state do not linger.
        """
        self._cleanup_ranking_worker(terminate=True)
        self._set_ranking_busy(False)
        self._clear_ranking_dirty()
        self._streaming_run_active = False

    def append_period(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        truncated_periods: set[str] | None = None,
    ) -> None:
        """Add one streamed batch of periods without clearing existing tabs.

        The first batch of a run builds the standard tab scaffold (all periods
        empty); each batch then fills in its own period card(s). This is the
        incremental counterpart to :meth:`load`, used for streaming generation.
        """
        truncated = truncated_periods or set()

        if not self._streaming_run_active:
            self._init_streaming_scaffold(courses_by_id, prog_color_map, truncated)
            self._streaming_run_active = True

        # Course metadata can arrive with any batch; keep the union so the
        # calendar can always resolve course names/colours.
        self._courses_by_id.update(courses_by_id)
        self._truncated_periods |= truncated

        for period_key, schedules in schedules_by_period.items():
            if period_key not in self._schedules_by_period:
                # A period outside the standard scaffold (e.g. an extra loaded
                # period): create its tab on the fly.
                self._schedules_by_period[period_key] = []
                self._period_indices[period_key] = 0
                self._period_tabs.addTab(
                    self._build_period_card(period_key),
                    _display_period_key(period_key),
                )
                self._refresh_period_selector(preferred_key=period_key)

            self._schedules_by_period[period_key] = schedules
            self._period_indices.setdefault(period_key, 0)

            # Keep the controller's has-more state in sync per batch so the
            # period's "Load More" control reflects truncation as it streams in.
            still_more = period_key in truncated
            self._controller.set_has_more_for_period(period_key, still_more)
            if not still_more:
                self._total_by_period[period_key] = len(schedules)

            self._rebuild_navigation_cache(period_key)
            self._refresh_period_card(period_key)

        first_ready_period = next(
            (key for key, schedules in schedules_by_period.items() if schedules),
            None,
        )
        if first_ready_period is not None:
            self._refresh_period_selector(preferred_key=first_ready_period)

        has_proctor_report = any(
            bool(getattr(schedule, "classroom_assignments", None))
            for schedules in self._schedules_by_period.values()
            for schedule in schedules
        )
        if has_proctor_report:
            self._proctor_btn.setVisible(True)

        self._update_summary()

    def _init_streaming_scaffold(
        self,
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        truncated_periods: set[str],
    ) -> None:
        """Build empty cards for every standard/loaded period on stream start."""
        self.clear_stale()
        self._is_imported_schedule = False
        self._clear_favorites()
        self._generation_thresholds = self._controller.settings.thresholds

        # Stop any in-flight Load More / persistent workers from a previous run
        # before rebuilding cards (mirrors load()).
        self._lm.reset()
        self._controller.shutdown_load_workers()

        self._courses_by_id = dict(courses_by_id)
        self._prog_color_map = prog_color_map
        self._truncated_periods = set(truncated_periods)

        all_period_keys = _merge_period_keys(self._controller, {})
        self._schedules_by_period = {k: [] for k in all_period_keys}
        self._period_indices = {k: 0 for k in self._schedules_by_period}
        self._total_by_period = {}
        self._nav_model.clear()
        self._rebuild_navigation_cache()

        self._period_tabs.clear()
        self._cards.clear()
        self._cell_data.clear()

        for period_key in self._schedules_by_period:
            self._period_tabs.addTab(
                self._build_period_card(period_key),
                _display_period_key(period_key),
            )
        self._refresh_period_selector()

        self._proctor_btn.setVisible(False)
        self._update_summary()
        self._refresh_active_limits_panel()
        self._placeholder.setVisible(False)
        self._content.setVisible(True)
        self._content.setGraphicsEffect(None)

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

    def append_loaded_schedules(self, period_key: str, extra: list[Schedule]) -> None:
        """Merge a freshly loaded batch into this period's own schedule state.

        Owned by the panel so the load-more controller never mutates the panel's
        private dicts directly. Keeps the navigation cache and the controller's
        cached results in sync (so a later re-sort includes the appended batch).
        """
        if self._is_imported_schedule:
            return

        # Disk-backed result storage keeps only current objects in RAM and still
        # enforces its disk-cache ceiling. Plain in-memory results append the
        # whole returned batch; there is no artificial RAM cap.
        if self._schedule_store is not None:
            headroom = ABSOLUTE_MAX_STORED_SCHEDULES - self._schedule_store.total_count()
            if headroom <= 0:
                logger.warning(
                    "SQLite schedule cache cap (%s) reached; refusing further load for %s.",
                    ABSOLUTE_MAX_STORED_SCHEDULES,
                    period_key,
                )
                return
            if len(extra) > headroom:
                logger.warning(
                    "SQLite schedule cache cap (%s) reached; truncating batch for %s "
                    "from %s to %s schedules.",
                    ABSOLUTE_MAX_STORED_SCHEDULES,
                    period_key,
                    len(extra),
                    headroom,
                )
                extra = extra[:headroom]

        self._schedules_by_period[period_key].extend(extra)

        # Keep the appended schedules cached, but do not re-sort the whole
        # result set on every Load More / Auto Load batch. Users can explicitly
        # run Result Ranking once loading settles.
        self._schedules_by_period = self._controller.cache_loaded_results_without_reranking(
            dict(self._schedules_by_period)
        )
        self._period_indices[period_key] = min(
            self._period_indices.get(period_key, 0),
            max(0, len(self._schedules_by_period[period_key]) - 1),
        )
        self._rebuild_navigation_cache(period_key)
        self._update_summary()

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
        """Show that current results need explicit async Result Ranking."""
        if not self.has_results():
            return
        self._summary_presenter.mark_ranking_dirty(message)
        self._sync_ranking_dirty_state()
        self._update_summary()

    def show_workload_status(self, message: str) -> None:
        """Show a non-popup status for normal background workload progress."""
        self._summary_lbl.setStyleSheet(
            "color: #64748B; font-weight: 600; font-size: 12px;"
        )
        self._summary_lbl.setText(message)

    def _on_limits_toggled(self, expanded: bool) -> None:
        """Expand/collapse the active generation limits details."""
        self._limits_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self._limits_details.setVisible(expanded)

    def _refresh_active_limits_panel(self) -> None:
        """Show enabled threshold rules used by the displayed generation."""
        thresholds = self._generation_thresholds
        active_entries = (
            [] if thresholds is None else _active_threshold_entries(thresholds)
        )

        if self._is_imported_schedule or not active_entries:
            self._limits_panel.setVisible(False)
            self._limits_toggle.setChecked(False)
            self._limits_details.setText("")
            return

        self._limits_toggle.setChecked(False)
        self._limits_toggle.setText(
            f"Active scheduling limits ({len(active_entries)})"
        )
        self._limits_details.setText(
            "<br>".join(
                f"<span style='color:#7C3AED;'>•</span> "
                f"{_format_threshold_entry(entry)}"
                for entry in active_entries
            )
        )
        self._limits_details.setTextFormat(Qt.TextFormat.RichText)
        self._limits_panel.setVisible(True)

    def _clear_ranking_dirty(self) -> None:
        self._summary_presenter.clear_ranking_dirty()
        self._sync_ranking_dirty_state()

    def _sync_ranking_dirty_state(self) -> None:
        self._ranking_dirty = self._summary_presenter.ranking_dirty
        self._ranking_dirty_message = self._summary_presenter.ranking_dirty_message

    def total_in_memory_schedule_count(self) -> int:
        """Return loaded schedule count kept by the active result container.

        With the SQLite-backed store this is a stored-count, not a count of
        Schedule objects resident in RAM.  The name is kept for compatibility
        with LoadMoreController/tests.
        """
        return sum(len(scheds) for scheds in self._schedules_by_period.values())

    def is_at_memory_cap(self) -> bool:
        """Return True once the active disk-backed result cache reaches its cap."""
        if self._schedule_store is not None:
            return self._schedule_store.total_count() >= ABSOLUTE_MAX_STORED_SCHEDULES
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
        self._favorite_schedules.clear()
        self._refresh_favorite_buttons()

    def _favorite_label(self, period_key: str, index: int) -> str:
        index_nav = self._nav_model.index_nav(period_key)
        nav_pos = index_nav.get(index)
        if nav_pos is None:
            self._rebuild_navigation_cache(period_key)
            nav_pos = self._nav_model.index_nav(period_key).get(index)

        if nav_pos is None:
            return f"{_display_period_key(period_key)} | Schedule {index + 1:,}"

        date_pos, variant_pos = nav_pos
        return (
            f"{_display_period_key(period_key)} | "
            f"Date option {date_pos + 1:,} | Variant {variant_pos + 1:,}"
        )

    def _save_current_favorite(self, period_key: str) -> None:
        schedules = self._schedules_by_period.get(period_key, [])
        if not schedules:
            return

        index = self._period_indices.get(period_key, 0)
        if index < 0 or index >= len(schedules):
            return

        for favorite in self._favorite_schedules:
            if favorite["period_key"] == period_key and favorite["index"] == index:
                self._refresh_favorite_buttons(saved_period_key=period_key)
                return

        self._favorite_schedules.append(
            {
                "period_key": period_key,
                "index": index,
                "label": self._favorite_label(period_key, index),
            }
        )
        self._refresh_favorite_buttons(saved_period_key=period_key)

    def _save_visible_favorite(self) -> None:
        period_key = self._current_period_key()
        if period_key is not None:
            self._save_current_favorite(period_key)

    def _delete_favorite_at(self, row: int) -> bool:
        if row < 0 or row >= len(self._favorite_schedules):
            return False
        del self._favorite_schedules[row]
        self._refresh_favorite_buttons()
        return True

    def _refresh_favorite_buttons(self, saved_period_key: str | None = None) -> None:
        count = len(self._favorite_schedules)
        current = self._current_period_key()
        has_current_schedule = bool(
            current is not None and self._schedules_by_period.get(current)
        )
        self._save_favorite_btn.setVisible(not self._is_imported_schedule)
        self._save_favorite_btn.setEnabled(has_current_schedule)
        self._favorites_btn.setEnabled(count > 0)
        self._favorites_btn.setText(f"My Favorites ({count})")
        if saved_period_key is not None and saved_period_key == current:
            self._save_favorite_btn.setText("Saved")
            QTimer.singleShot(1400, lambda: self._save_favorite_btn.setText("Save Favorite"))
        else:
            self._save_favorite_btn.setText("Save Favorite")

    def _show_favorites_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("My Favorite Schedules")
        dialog.setMinimumWidth(460)
        dialog.setStyleSheet(
            "QDialog { background: #F8FAFC; color: #172033; }"
            "QLabel { color: #0755B5; font-size: 14px; font-weight: 800; }"
            "QListWidget { background: #FFFFFF; border: 1px solid #C4B5FD;"
            " border-radius: 8px; padding: 6px; color: #172033; }"
            "QPushButton { background: #2563EB; color: #FFFFFF; border: none;"
            " border-radius: 8px; padding: 7px 16px; font-weight: 700; }"
            "QPushButton:disabled { background: #CBD5E1; color: #64748B; }"
        )

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("My favorite schedules"))

        favorites_list = QListWidget()
        for favorite in self._favorite_schedules:
            favorites_list.addItem(str(favorite["label"]))
        if self._favorite_schedules:
            favorites_list.setCurrentRow(0)
        layout.addWidget(favorites_list)

        actions = QHBoxLayout()
        open_btn = QPushButton("Open Selected")
        open_btn.setEnabled(bool(self._favorite_schedules))
        delete_btn = QPushButton("Delete Selected")
        delete_btn.setEnabled(bool(self._favorite_schedules))
        delete_btn.setStyleSheet(
            "background: #FFFFFF; color: #B91C1C; border: 1px solid #FCA5A5;"
            " border-radius: 8px; padding: 7px 16px; font-weight: 700;"
        )
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "background: #FFFFFF; color: #172033; border: 1px solid #CBD5E1;"
            " border-radius: 8px; padding: 7px 16px; font-weight: 700;"
        )
        actions.addStretch()
        actions.addWidget(delete_btn)
        actions.addWidget(close_btn)
        actions.addWidget(open_btn)
        layout.addLayout(actions)

        def open_selected() -> None:
            row = favorites_list.currentRow()
            if row < 0 or row >= len(self._favorite_schedules):
                return
            favorite = self._favorite_schedules[row]
            period_key = str(favorite["period_key"])
            index = int(favorite["index"])
            if period_key not in self._schedules_by_period:
                return
            if index >= len(self._schedules_by_period[period_key]):
                return
            self._period_indices[period_key] = index
            self._select_period_key(period_key)
            self._refresh_period_card(period_key)
            dialog.accept()

        def delete_selected() -> None:
            row = favorites_list.currentRow()
            if not self._delete_favorite_at(row):
                return
            favorites_list.takeItem(row)
            has_favorites = bool(self._favorite_schedules)
            open_btn.setEnabled(has_favorites)
            delete_btn.setEnabled(has_favorites)
            if has_favorites:
                favorites_list.setCurrentRow(min(row, len(self._favorite_schedules) - 1))

        open_btn.clicked.connect(open_selected)
        delete_btn.clicked.connect(delete_selected)
        close_btn.clicked.connect(dialog.reject)
        favorites_list.itemDoubleClicked.connect(lambda _item: open_selected())
        dialog.exec()

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

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override name
        self._period_tip_bubble.hide()
        self._cleanup_ranking_worker(terminate=True)
        if self._controller.heavy_task_kind == "ranking":
            self._controller.end_heavy_task("ranking")
            self._finish_ranking_metrics()
            self.heavy_task_state_changed.emit("ranking", False)
        if self._schedule_store is not None:
            self._schedule_store.close(delete=True)
            self._schedule_store = None
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
        """Show a styled light popover instead of the native black tooltip."""
        if not self._period_tip_btn.isVisible():
            return

        self._period_tip_bubble.adjustSize()
        pos = self._period_tip_btn.mapToGlobal(
            QPoint(0, self._period_tip_btn.height() + 8)
        )
        self._period_tip_bubble.move(pos)
        self._period_tip_bubble.show()
        self._period_tip_bubble.raise_()

    def _setup_ui(self) -> None:
        self.setStyleSheet(
            """
            _ResultsPanel { background: transparent; }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        self._placeholder = AnimatedPlaceholder(
            "No schedules generated yet.\n\n"
            "Load files, select a programme, then click  ▶  Generate Schedule."
        )
        root.addWidget(self._placeholder)

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content.setVisible(False)

        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)

        action_row = QHBoxLayout()

        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet(
            "color: #059669; font-weight: 600; font-size: 12px;"
        )
        action_row.addWidget(self._summary_lbl)
        action_row.addStretch()

        # Spec: re-rank the already-generated schedules in memory (no regenerate).
        self._ranking_btn = QPushButton(_RANKING_BUTTON_TEXT)
        self._ranking_btn.setStyleSheet(
            "QPushButton {"
            " background: #2563EB; color: #FFFFFF; font-weight: 700;"
            " border: none; border-radius: 8px; padding: 7px 18px; }"
            "QPushButton:hover { background: #1D4ED8; }"
            "QPushButton:disabled { background: #C7D2DE; color: #FFFFFF; }"
        )
        self._ranking_btn.clicked.connect(self._on_result_ranking)
        action_row.addWidget(self._ranking_btn)

        self._save_favorite_btn = QPushButton("Save Favorite")
        self._save_favorite_btn.setStyleSheet(
            "QPushButton { background: #EEF6FF; color: #0755B5;"
            " border: 1px solid #93C5FD; border-radius: 8px;"
            " padding: 7px 16px; font-weight: 700; }"
            "QPushButton:hover { background: #DBEAFE; }"
            "QPushButton:disabled { background: #F1F5F9; color: #94A3B8;"
            " border-color: #CBD5E1; }"
        )
        self._save_favorite_btn.clicked.connect(self._save_visible_favorite)
        action_row.addWidget(self._save_favorite_btn)

        self._favorites_btn = QPushButton("My Favorites (0)")
        self._favorites_btn.setStyleSheet(
            "QPushButton { background: #F5F3FF; color: #5B21B6;"
            " border: 1px solid #C4B5FD; border-radius: 8px;"
            " padding: 7px 16px; font-weight: 700; }"
            "QPushButton:hover { background: #EDE9FE; }"
            "QPushButton:disabled { background: #F1F5F9; color: #94A3B8;"
            " border-color: #CBD5E1; }"
        )
        self._favorites_btn.clicked.connect(self._show_favorites_dialog)
        action_row.addWidget(self._favorites_btn)

        self._save_btn = QPushButton("⬇  Export Schedule")
        self._save_btn.clicked.connect(self._on_save)
        action_row.addWidget(self._save_btn)

        # Spec 4.6: per-schedule proctor report (GUI view + .txt export).
        self._proctor_btn = QPushButton("🧑‍🏫  Proctor Report")
        self._proctor_btn.clicked.connect(self._on_proctor_report)
        action_row.addWidget(self._proctor_btn)

        cl.addLayout(action_row)

        self._limits_panel = QWidget()
        self._limits_panel.setStyleSheet(
            "background: #EEF6FF;"
            " border: 1px solid #BFDBFE;"
            " border-radius: 8px;"
        )
        limits_layout = QVBoxLayout(self._limits_panel)
        limits_layout.setContentsMargins(14, 10, 14, 10)
        limits_layout.setSpacing(8)

        self._limits_toggle = QToolButton()
        self._limits_toggle.setCheckable(True)
        self._limits_toggle.setChecked(False)
        self._limits_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._limits_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._limits_toggle.setText("Active scheduling limits")
        self._limits_toggle.setToolTip(
            "Show the enabled threshold settings used for this generation."
        )
        self._limits_toggle.setStyleSheet(
            "QToolButton {"
            " background: transparent; color: #0755B5; border: none;"
            " font-size: 13px; font-weight: 800; padding: 0;"
            "}"
            "QToolButton:hover { color: #7C3AED; }"
        )
        self._limits_toggle.toggled.connect(self._on_limits_toggled)
        limits_layout.addWidget(self._limits_toggle)

        self._limits_details = QLabel("")
        self._limits_details.setWordWrap(True)
        self._limits_details.setVisible(False)
        self._limits_details.setStyleSheet(
            "background: rgba(255, 255, 255, 0.62);"
            " color: #243044; border: 1px solid #DBEAFE;"
            " border-radius: 8px; padding: 8px 10px;"
            " font-size: 12px; font-weight: 600;"
        )
        limits_layout.addWidget(self._limits_details)
        self._limits_panel.setVisible(False)

        cl.addWidget(self._limits_panel)

        self._stale_banner = QLabel(
            "⚠  Exam period dates were changed after generation. "
            "The displayed schedules may contain now-excluded dates. "
            "Click  ▶  Generate again to update."
        )
        self._stale_banner.setWordWrap(True)
        self._stale_banner.setStyleSheet(
            "background: #FEF3C7; color: #92400E;"
            " border: 1px solid #F59E0B; border-radius: 8px;"
            " padding: 8px 14px; font-size: 12px; font-weight: 500;"
        )
        self._stale_banner.setVisible(False)

        cl.addWidget(self._stale_banner)

        self._period_selector = QWidget()
        self._period_selector.setStyleSheet(
            "QWidget { background: #FFFFFF; border: 1px solid #DCE5F0;"
            " border-radius: 8px; }"
        )
        selector_layout = QHBoxLayout(self._period_selector)
        selector_layout.setContentsMargins(12, 10, 12, 10)
        selector_layout.setSpacing(10)

        selector_title = QLabel("View period")
        selector_title.setStyleSheet(
            "background: transparent; border: none; color: #0755B5;"
            " font-size: 13px; font-weight: 800;"
        )
        selector_layout.addWidget(selector_title)

        self._period_tip_btn = QToolButton()
        self._period_tip_btn.setText("!")
        self._period_tip_btn.setCursor(Qt.CursorShape.WhatsThisCursor)
        self._period_tip_btn.setFixedSize(24, 24)
        self._period_tip_btn.setStyleSheet(
            "QToolButton { background: #EEF6FF; color: #0755B5;"
            " border: 1px solid #93C5FD; border-radius: 12px;"
            " font-size: 13px; font-weight: 900; }"
            "QToolButton:hover { background: #F5F3FF; color: #7C3AED;"
            " border-color: #C4B5FD; }"
        )
        self._period_tip_btn.installEventFilter(self)
        selector_layout.addWidget(self._period_tip_btn)

        self._period_tip_bubble = QLabel(
            "Click on any scheduled exam date to view full details."
        )
        self._period_tip_bubble.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
        )
        self._period_tip_bubble.setAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating, True
        )
        self._period_tip_bubble.setStyleSheet(
            "QLabel { background: #F8FAFC; color: #172033;"
            " border: 1px solid #C4B5FD; border-radius: 8px;"
            " padding: 8px 12px; font-size: 12px; font-weight: 600; }"
        )
        self._period_tip_bubble.hide()

        semester_label = QLabel("Semester")
        semester_label.setStyleSheet(
            "background: transparent; border: none; color: #64748B;"
            " font-size: 11px; font-weight: 700;"
        )
        selector_layout.addWidget(semester_label)

        combo_style = (
            "QComboBox { background: #F8FAFC; color: #172033;"
            " border: 1px solid #CBD5E1; border-radius: 8px;"
            " padding: 6px 32px 6px 10px; font-size: 12px; font-weight: 700;"
            " min-width: 140px; }"
            "QComboBox:hover { border-color: #7C3AED; }"
            "QComboBox:focus { border-color: #0755B5; }"
            "QComboBox::drop-down { border: none; width: 26px; }"
        )
        self._semester_combo = QComboBox()
        self._semester_combo.setStyleSheet(combo_style)
        self._semester_combo.currentIndexChanged.connect(
            self._on_period_semester_changed
        )
        selector_layout.addWidget(self._semester_combo)

        moed_label = QLabel("Moed")
        moed_label.setStyleSheet(
            "background: transparent; border: none; color: #64748B;"
            " font-size: 11px; font-weight: 700;"
        )
        selector_layout.addWidget(moed_label)

        self._moed_combo = QComboBox()
        self._moed_combo.setStyleSheet(combo_style)
        self._moed_combo.currentIndexChanged.connect(self._on_period_moed_changed)
        selector_layout.addWidget(self._moed_combo)
        selector_layout.addStretch()
        self._period_selector.setVisible(False)

        cl.addWidget(self._period_selector)

        self._period_tabs = QTabWidget()
        self._period_tabs.setStyleSheet(PERIOD_TAB_STYLE)
        self._period_tabs.tabBar().hide()
        self._period_tabs.tabBar().setFixedHeight(0)
        self._period_tabs.currentChanged.connect(self._on_period_tab_changed)
        cl.addWidget(self._period_tabs)

        root.addWidget(self._content)

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

    def _date_options_for_period(
        self,
        period_key: str,
    ) -> list[tuple[_DateSignature, list[int]]]:
        """Return cached date options through NavigationModel."""
        return self._nav_model.date_options(period_key)

    def _period_key_at_tab_index(self, index: int) -> str | None:
        """Return the period key displayed by tab *index*, if any."""
        period_keys = list(self._schedules_by_period)
        if 0 <= index < len(period_keys):
            return period_keys[index]
        return None

    @staticmethod
    def _period_parts(period_key: str) -> tuple[str, str]:
        """Return (semester, moed) for a period key."""
        if " - " in period_key:
            semester, moed = period_key.split(" - ", 1)
            return semester.strip(), moed.strip()
        if " — " in period_key:
            semester, moed = period_key.split(" — ", 1)
            return semester.strip(), moed.strip()
        return period_key.strip(), ""

    def _period_keys_for_semester(self, semester: str) -> list[str]:
        return [
            key
            for key in self._period_keys_for_selector()
            if self._period_parts(key)[0] == semester
        ]

    def _period_keys_for_selector(self) -> list[str]:
        """Return all periods the user can inspect, including empty ones."""
        return list(self._schedules_by_period)

    def _first_period_with_results(self) -> str | None:
        """Return the first period that currently has visible schedules."""
        for key, schedules in self._schedules_by_period.items():
            if schedules:
                return key
        return None

    def _refresh_period_selector(self, preferred_key: str | None = None) -> None:
        """Populate the compact semester/moed selector from available periods."""
        if not hasattr(self, "_semester_combo"):
            return

        period_keys = self._period_keys_for_selector()
        self._period_selector.setVisible(bool(period_keys))
        if not period_keys:
            return

        current_key = (
            preferred_key
            or self._first_period_with_results()
            or self._current_period_key()
            or period_keys[0]
        )
        current_semester, _ = self._period_parts(current_key)

        semesters: list[str] = []
        for key in period_keys:
            semester, _moed = self._period_parts(key)
            if semester not in semesters:
                semesters.append(semester)

        with QSignalBlocker(self._semester_combo):
            self._semester_combo.clear()
            for semester in semesters:
                self._semester_combo.addItem(display_semester(semester), semester)
            semester_index = max(0, self._semester_combo.findData(current_semester))
            self._semester_combo.setCurrentIndex(semester_index)
            current_semester = self._semester_combo.currentData()

        self._populate_moed_selector(current_semester, current_key)

    def _populate_moed_selector(
        self,
        semester: str,
        preferred_key: str | None = None,
    ) -> None:
        period_keys = self._period_keys_for_semester(semester)
        with QSignalBlocker(self._moed_combo):
            self._moed_combo.clear()
            for key in period_keys:
                _semester, moed = self._period_parts(key)
                self._moed_combo.addItem(moed or _display_period_key(key), key)
            preferred_index = (
                self._moed_combo.findData(preferred_key)
                if preferred_key is not None
                else -1
            )
            self._moed_combo.setCurrentIndex(max(0, preferred_index))

        selected_key = self._moed_combo.currentData()
        if selected_key:
            self._select_period_key(selected_key)

    def _select_period_key(self, period_key: str) -> None:
        period_keys = list(self._schedules_by_period)
        try:
            index = period_keys.index(period_key)
        except ValueError:
            return
        if self._period_tabs.currentIndex() != index:
            self._period_tabs.setCurrentIndex(index)
        else:
            self._on_period_tab_changed(index)

    def _on_period_semester_changed(self, _index: int) -> None:
        semester = self._semester_combo.currentData()
        if semester:
            self._populate_moed_selector(semester)

    def _on_period_moed_changed(self, _index: int) -> None:
        period_key = self._moed_combo.currentData()
        if period_key:
            self._select_period_key(period_key)

    def _current_period_key(self) -> str | None:
        """Return the period key for the currently visible tab."""
        return self._period_key_at_tab_index(self._period_tabs.currentIndex())

    def _on_period_tab_changed(self, index: int) -> None:
        """Refresh a period lazily when it becomes visible."""
        period_key = self._period_key_at_tab_index(index)
        if period_key is not None and period_key in self._cards:
            if hasattr(self, "_moed_combo") and self._moed_combo.currentData() != period_key:
                self._refresh_period_selector(preferred_key=period_key)
            self._refresh_period_card(period_key)

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
        schedules = self._schedules_by_period[period_key]
        total = len(schedules)
        has_more = (
            False
            if self._is_imported_schedule
            else self._controller.has_more_schedules(period_key)
        )
        card = self._cards.get(period_key)

        # The navigation cache should already be current after load/load-more,
        # but this keeps the method safe if tests mutate schedules directly.
        options = self._date_options_for_period(period_key)
        index_nav = self._nav_model.index_nav(period_key)

        if total > 0:
            idx = self._period_indices.get(period_key, 0)
            if idx < 0 or idx >= total:
                idx = 0
                self._period_indices[period_key] = idx

            nav_pos = index_nav.get(idx)
            if nav_pos is None:
                self._rebuild_navigation_cache(period_key)
                options = self._date_options_for_period(period_key)
                index_nav = self._nav_model.index_nav(period_key)
                nav_pos = index_nav.get(idx)
        else:
            idx = 0
            nav_pos = None

        if total == 0 or nav_pos is None or not options:
            date_nav_text = "Date option: 0 / 0"
            variant_nav_text = "Variant: 0 / 0"
            same_date_indices: list[int] = []
            date_option_pos = -1
            variant_pos = -1

            if card is not None:
                card.empty_label.setText(
                    f"No schedules were generated for {_display_period_key(period_key)}."
                )
                card.empty_label.setVisible(True)
                card.cal_table.setVisible(False)
        else:
            date_option_pos, variant_pos = nav_pos
            same_date_indices = options[date_option_pos][1]

            date_total_text = f"{len(options):,}"
            if has_more:
                date_total_text += "+"

            date_nav_text = (
                f"Date option: {date_option_pos + 1:,} / {date_total_text}"
            )
            variant_nav_text = (
                f"Variant for these dates: {variant_pos + 1:,} / {len(same_date_indices):,}"
            )

            if card is not None:
                card.empty_label.setVisible(False)
                card.cal_table.setVisible(True)

        if card is None:
            self._update_summary()
            return

        card.date_counter_label.setText(date_nav_text)
        card.counter_label.setText(variant_nav_text)

        card.date_jump_input.setEnabled(total > 0)
        card.date_jump_input.setPlaceholderText(
            str(date_option_pos + 1)
            if total > 0 and date_option_pos >= 0
            else "#"
        )

        card.variant_jump_input.setEnabled(total > 0)
        card.variant_jump_input.setPlaceholderText(
            str(variant_pos + 1)
            if total > 0 and variant_pos >= 0
            else "#"
        )

        card.prev_date_btn.setEnabled(total > 0 and date_option_pos > 0)
        card.next_date_btn.setEnabled(
            total > 0 and (date_option_pos < len(options) - 1 or has_more)
        )

        if total > 0 and same_date_indices:
            card.prev_btn.setEnabled(variant_pos > 0)
            card.next_btn.setEnabled(variant_pos < len(same_date_indices) - 1)
        else:
            card.prev_btn.setEnabled(False)
            card.next_btn.setEnabled(False)

        card.load_more_btn.setVisible(has_more)
        ranking_active = self.is_ranking_active()
        card.load_more_btn.setEnabled(
            has_more
            and period_key not in self._lm.procs
            and period_key not in self._lm.auto_load_periods
            and not ranking_active
        )
        if ranking_active and has_more:
            card.load_more_btn.setText("Ranking in progress")
        elif has_more and period_key not in self._lm.procs:
            card.load_more_btn.setText(f"⟳  +{LOAD_BATCH_SIZE:,} more options")

        active_mode = self._lm.auto_load_modes.get(period_key)
        if not has_more and active_mode == _AUTO_MODE_DATES:
            self._lm.stop_auto_load(period_key, refresh=False)

        has_classroom_variants = self._has_classroom_feature_results(period_key)
        card.variant_navigation.setVisible(
            not self._is_imported_schedule and has_classroom_variants
        )
        card.auto_date_btn.setVisible(
            not self._is_imported_schedule
            and (has_more or active_mode == _AUTO_MODE_DATES)
        )
        card.auto_variant_btn.setVisible(
            not self._is_imported_schedule
            and (has_classroom_variants or active_mode == _AUTO_MODE_VARIANTS)
        )

        if not self._is_imported_schedule:
            self._lm.update_auto_load_button(period_key)
        self._refresh_favorite_buttons()

        if schedules:
            self._cell_data[period_key] = self._calendar.populate(
                card.cal_table,
                schedules[self._period_indices[period_key]],
                self._courses_by_id,
                self._prog_color_map,
                period_key,
            )
        else:
            card.cal_table.clearContents()
            card.cal_table.setRowCount(0)

        self._update_summary()

    def _update_summary(self) -> None:
        if not self._schedules_by_period:
            return

        non_empty = {
            key: value
            for key, value in self._schedules_by_period.items()
            if value
        }

        period_schedules_total = sum(
            len(schedules)
            for schedules in non_empty.values()
        )

        has_more = any(
            self._controller.has_more_schedules(period_key)
            or period_key in self._truncated_periods
            for period_key in non_empty
        )
        summary = self._summary_presenter.build(
            has_any_periods=bool(self._schedules_by_period),
            has_results=bool(non_empty),
            is_stale=self._is_stale(),
            is_imported_schedule=self._is_imported_schedule,
            combined_options_total=self._controller.get_combined_schedule_count(non_empty),
            period_schedules_total=period_schedules_total,
            has_more=has_more,
        )
        if summary is None:
            return

        self._summary_lbl.setStyleSheet(summary.style)
        self._summary_lbl.setText(summary.text)

    def _on_cell_clicked(
        self,
        period_key: str,
        row: int,
        col: int,
        click_pos: QPoint | None = None,
    ) -> None:
        cell_info = self._cell_data.get(period_key, {}).get((row, col))

        if cell_info is None:
            return

        exam_date, course_ids, classroom_assignments, unassigned_exams, groups = (
            cell_info
        )

        if not course_ids:
            return

        all_course_ids = list(course_ids)
        all_classroom_assignments = classroom_assignments
        all_unassigned_exams = unassigned_exams

        # Spec 4.5: when the cell renders multiple side-by-side slot columns,
        # open only the exams of the column the user actually clicked.
        visible_ids = self._slot_filter_for_click(
            period_key, row, col, groups, click_pos
        )
        if visible_ids is not None:
            course_ids = visible_ids
            classroom_assignments = {
                cid: classroom_assignments.get(cid, []) for cid in course_ids
            }
            unassigned_exams = {
                cid: unassigned_exams[cid]
                for cid in course_ids
                if cid in unassigned_exams
            }

        from src.ui.exam_detail_dialog import ExamDetailDialog

        dialog = ExamDetailDialog(
            exam_date,
            course_ids,
            self._courses_by_id,
            self._prog_color_map,
            classroom_assignments,
            unassigned_exams,
            parent=self,
            all_course_ids=all_course_ids,
            all_classroom_assignments=all_classroom_assignments,
            all_unassigned_exams=all_unassigned_exams,
        )
        dialog.exec()

    def _slot_filter_for_click(
        self,
        period_key: str,
        row: int,
        col: int,
        groups: "list[dict] | None",
        click_pos: QPoint | None = None,
    ) -> "list[str] | None":
        """Return the course ids of the slot column under the cursor, or None.

        None means "no per-slot narrowing" — caller shows the whole date. When
        the cell is split into N slot columns, map the cursor's x offset within
        the cell to the matching column and return just its course ids.
        """
        if not groups or click_pos is None:
            return None

        card = self._cards.get(period_key)
        table = card.cal_table if card else None
        if table is None:
            return None

        item = table.item(row, col)
        if item is None:
            return None

        rect = table.visualItemRect(item)
        if rect.width() <= 0:
            return None

        return _course_ids_for_click_position(groups, rect, click_pos)

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
        """Open the Result Ranking dialog and re-rank cached results in place.

        Re-sorts the schedules already held in memory using the new priority
        order — it never re-runs schedule generation (spec performance rule).
        """
        if self._is_stale():
            self._show_message(
                "Stale Schedules",
                "Settings have changed since the last generation.\n\n"
                "Please click  ▶  Generate again before re-ranking results.",
                QMessageBox.Icon.Warning,
            )
            return

        if not any(self._schedules_by_period.values()):
            self._show_message(
                "No Schedules",
                "Generate or load schedules before changing the result ranking.",
                QMessageBox.Icon.Warning,
            )
            return

        from src.ui.ranking_dialog import RankingDialog

        dialog = RankingDialog(self._controller.settings.sorting, parent=self)
        dialog.ranking_applied.connect(self._apply_ranking)
        dialog.exec()

    def _apply_ranking(self, config: "SortingConfig") -> None:
        """Start asynchronous re-ranking of cached schedules."""
        if self._ranking_proc is not None:
            self._show_message(
                "Ranking In Progress",
                "Result Ranking is already running. Please wait for it to finish.",
                QMessageBox.Icon.Information,
            )
            return

        if not self._begin_heavy_task("ranking"):
            self._show_message(
                "Ranking Unavailable",
                "Result Ranking is available after generation/loading finishes.",
                QMessageBox.Icon.Information,
            )
            self._refresh_heavy_task_controls()
            return

        try:
            job = self._controller.build_ranking_job(config)
        except ValueError:
            # No cached results to re-rank; keep the new order for next generate.
            self._controller.apply_sort(config)
            self._end_heavy_task("ranking")
            return

        queue = multiprocessing.Queue()
        proc = multiprocessing.Process(
            target=run_ranking_worker,
            args=(queue, job),
            daemon=True,
        )

        self._ranking_queue = queue
        self._ranking_proc = proc
        self._ranking_config = config
        self._ranking_empty_after_exit_ticks = 0
        self._set_ranking_busy(True)

        try:
            proc.start()
        except Exception as exc:
            self._cleanup_ranking_worker(terminate=True)
            self._ranking_config = None
            self._end_heavy_task("ranking")
            self._set_ranking_busy(False)
            self._show_message(
                "Ranking Failed",
                f"Could not start Result Ranking.\n\n{exc}",
                QMessageBox.Icon.Warning,
            )
            return

        timer = QTimer(self)
        timer.timeout.connect(self._poll_ranking_worker)
        timer.start(100)
        self._ranking_timer = timer

    def _poll_ranking_worker(self) -> None:
        """Poll the background ranking worker without blocking the UI thread."""
        queue = self._ranking_queue
        proc = self._ranking_proc
        if queue is None:
            self._cleanup_ranking_worker(terminate=True)
            self._set_ranking_busy(False)
            return

        try:
            result = queue.get_nowait()
        except _QueueEmpty:
            if proc is not None and not proc.is_alive() and proc.exitcode is not None:
                self._ranking_empty_after_exit_ticks += 1
                if self._ranking_empty_after_exit_ticks <= _RANKING_EXIT_QUEUE_GRACE_TICKS:
                    return
                exitcode = proc.exitcode
                self._cleanup_ranking_worker(terminate=False)
                self._ranking_config = None
                self._end_heavy_task("ranking")
                self._set_ranking_busy(False)
                self._show_message(
                    "Ranking Failed",
                    f"Result Ranking stopped before returning a result (exit code {exitcode}).",
                    QMessageBox.Icon.Warning,
                )
            return

        self._ranking_empty_after_exit_ticks = 0
        config = self._ranking_config
        self._cleanup_ranking_worker(terminate=False)
        self._ranking_config = None

        if not isinstance(result, RankingWorkerResult):
            self._end_heavy_task("ranking")
            self._set_ranking_busy(False)
            self._show_message(
                "Ranking Failed",
                "Result Ranking returned an unexpected response.",
                QMessageBox.Icon.Warning,
            )
            return

        if not result.success:
            self._end_heavy_task("ranking")
            self._set_ranking_busy(False)
            self._show_message(
                "Ranking Failed",
                result.error or "Result Ranking failed.",
                QMessageBox.Icon.Warning,
            )
            return

        if config is None:
            self._end_heavy_task("ranking")
            self._set_ranking_busy(False)
            self._show_message(
                "Ranking Failed",
                "Result Ranking finished after the ranking state was cleared.",
                QMessageBox.Icon.Warning,
            )
            return

        try:
            resorted = self._controller.apply_ranked_results(
                config,
                result.schedules_by_period,
            )
        except Exception as exc:
            self._end_heavy_task("ranking")
            self._set_ranking_busy(False)
            self._show_message(
                "Ranking Failed",
                str(exc),
                QMessageBox.Icon.Warning,
            )
            return

        self._finish_ranking_success(resorted)
        self._end_heavy_task("ranking")
        self._set_ranking_busy(False)

    def _finish_ranking_success(
        self,
        resorted: dict[str, list[Schedule]],
    ) -> None:
        """Apply ranked results to the panel and refresh only the visible card."""
        for period_key, schedules in resorted.items():
            self._schedules_by_period[period_key] = schedules
            # A changed ranking changes what schedule index 0 means; show the new
            # best-ranked option instead of keeping an arbitrary old ordinal.
            self._period_indices[period_key] = 0

        self._nav_model.clear()
        self._clear_ranking_dirty()

        has_proctor_report = any(
            self._has_classroom_feature_results(period_key)
            for period_key, schedules in self._schedules_by_period.items()
            if schedules
        )
        self._proctor_btn.setVisible(has_proctor_report)

        visible_period_key = self._current_period_key()
        if visible_period_key is not None and visible_period_key in self._cards:
            self._refresh_period_card(visible_period_key)
        else:
            self._update_summary()

    def _set_ranking_busy(self, busy: bool) -> None:
        """Update ranking button state while a background ranking job runs."""
        if not hasattr(self, "_ranking_btn"):
            return

        heavy_kind = self._controller.heavy_task_kind
        if busy or heavy_kind == "ranking":
            current_text = self._ranking_btn.text()
            if current_text not in {
                "Ranking results...",
                "Ranking available after loading finishes",
            }:
                self._ranking_button_text = current_text
            elif self._ranking_button_text is None:
                self._ranking_button_text = _RANKING_BUTTON_TEXT
            self._ranking_btn.setEnabled(False)
            self._ranking_btn.setText("Ranking results...")
            self._summary_lbl.setText("Ranking results...")
            return

        if heavy_kind in {"generation", "loading"}:
            self._ranking_btn.setEnabled(False)
            self._ranking_btn.setText("Ranking available after loading finishes")
            self._update_summary()
            return

        self._ranking_btn.setEnabled(True)
        self._ranking_btn.setText(self._ranking_button_text or _RANKING_BUTTON_TEXT)
        self._ranking_button_text = None
        self._update_summary()

    def _cleanup_ranking_worker(self, terminate: bool = False) -> None:
        """Stop timers/processes for the ranking worker and release handles."""
        timer = self._ranking_timer
        self._ranking_timer = None
        if timer is not None:
            timer.stop()

        proc = self._ranking_proc
        self._ranking_proc = None
        self._ranking_empty_after_exit_ticks = 0
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

        queue = self._ranking_queue
        self._ranking_queue = None
        if queue is not None:
            close = getattr(queue, "close", None)
            if callable(close):
                close()

        if terminate and self._controller.end_heavy_task("ranking"):
            self._finish_ranking_metrics()
            self.heavy_task_state_changed.emit("ranking", False)

    def is_ranking_active(self) -> bool:
        """Return True while the Result Ranking worker owns the heavy slot."""
        return self._controller.heavy_task_kind == "ranking"

    def _begin_heavy_task(self, kind: str) -> bool:
        """Reserve the shared heavy-task slot and refresh visible controls."""
        if not self._controller.begin_heavy_task(kind):
            return False
        if kind == "ranking":
            self._controller.performance_metrics.start_ranking()
        self.heavy_task_state_changed.emit(kind, True)
        self._refresh_heavy_task_controls()
        return True

    def _end_heavy_task(self, kind: str) -> None:
        """Release the shared heavy-task slot and refresh visible controls."""
        if self._controller.end_heavy_task(kind):
            if kind == "ranking":
                self._finish_ranking_metrics()
            self.heavy_task_state_changed.emit(kind, False)
        self._refresh_heavy_task_controls()

    def _finish_ranking_metrics(self) -> None:
        """Finalize ranking timing metrics."""
        try:
            snapshot = self._controller.performance_metrics.finish_ranking()
            logger.info(
                "Ranking performance summary: elapsed=%.3fs schedules=%s sqlite_rows=%s",
                snapshot.ranking_seconds,
                self._controller.cached_schedule_count(),
                snapshot.sqlite_stored_row_count,
            )
        except Exception:
            logger.debug("Failed recording ranking metrics", exc_info=True)

    def _refresh_heavy_task_controls(self) -> None:
        """Refresh ranking/load controls after heavy-task state changes."""
        self._set_ranking_busy(self._ranking_proc is not None)
        current = self._current_period_key()
        if current is not None and current in self._cards:
            self._refresh_period_card(current)

    def sync_heavy_task_state(self) -> None:
        """Public hook for the parent screen to refresh controls after generation."""
        self._refresh_heavy_task_controls()

    def _on_proctor_report(self) -> None:
        """Build and show the spec 4.6 proctor report for displayed schedules."""
        if self._is_stale():
            self._show_message(
                "Stale Schedules",
                "Exam period dates have changed since the last generation.\n\n"
                "Please click  ▶  Generate again before viewing/exporting the proctor report.",
                QMessageBox.Icon.Warning,
            )
            return

        selected = self._selected_schedules()
        if not selected:
            self._show_message(
                "No Schedules",
                "Generate or load schedules before viewing the proctor report.",
                QMessageBox.Icon.Warning,
            )
            return

        sections: list[str] = []
        for period_key, schedule in selected.items():
            body = self._controller.proctor_report_text(schedule)
            sections.append(f"=== {_display_period_key(period_key)} ===\n{body}")

        report_text = "\n\n".join(sections)

        if not any(s.classroom_assignments for s in selected.values()):
            self._show_message(
                "No Room Assignments",
                "These schedules have no classroom assignments. Enable Feature 4 "
                "(classrooms, slots, proctor ratio) and generate again to produce a "
                "proctor report.",
                QMessageBox.Icon.Information,
            )
            return

        from src.ui.proctor_report_dialog import ProctorReportDialog

        dialog = ProctorReportDialog(report_text, parent=self)
        dialog.exec()

    def _on_save(self) -> None:
        if self._is_stale():
            self._show_message(
                "Stale Schedules",
                "Exam period dates have changed since the last generation.\n\n"
                "Please click  ▶  Generate again before exporting.",
                QMessageBox.Icon.Warning,
            )
            return

        if not self._schedules_by_period:
            self._show_message(
                "Nothing to Save",
                "No schedules have been generated or loaded.",
                QMessageBox.Icon.Warning,
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Schedule",
            "schedules.txt",
            "Text files (*.txt);;All files (*)",
        )

        if not path:
            return

        selected = {
            key: [self._schedules_by_period[key][self._period_indices[key]]]
            for key in self._schedules_by_period
            if self._schedules_by_period[key]
        }

        if not selected:
            self._show_message(
                "Nothing to Save",
                "No schedules are currently displayed.",
                QMessageBox.Icon.Warning,
            )
            return

        try:
            self._controller.export(
                selected,
                Path(path),
                courses_by_id=self._courses_by_id,
            )
            self._show_message(
                "Saved",
                f"Schedule saved to:\n{path}",
                QMessageBox.Icon.Information,
            )
        except Exception:
            logger.exception("Save failed")
            self._show_message(
                "Save Error",
                "Could not save the schedule file. Please check the selected path and try again.",
                QMessageBox.Icon.Critical,
            )
