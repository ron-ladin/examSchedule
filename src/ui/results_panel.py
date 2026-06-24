"""
Widget: _ResultsPanel — Schedule Results Tab (SRS §3.1–§3.5)
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

import logging
from pathlib import Path

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
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

from src.controller import DesktopController
from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.semester import display_semester
from src.domain.sorting import SortingConfig
from src.engine.generation_workers import ABSOLUTE_MAX_IN_MEMORY_SCHEDULES
from src.ui.navigation_model import NavigationModel, DateSignature as _DateSignature
from src.ui.period_card import PeriodCardWidgets
from src.ui.period_utils import STANDARD_PERIOD_ORDER as _STANDARD_PERIOD_ORDER
from src.ui.load_more_controller import LoadMoreController
from src.ui.period_navigator import PeriodNavigator
from src.ui.widgets.calendar_view import CalendarRenderer
from src.ui.widgets.period_card_builder import (
    build_period_card,
    _make_data_table,  # re-exported for input_screen / programme_courses_dialog
)

logger = logging.getLogger(__name__)


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

    for period in controller.get_exam_periods():
        key = period.get_key()
        if key not in keys:
            keys.append(key)

    for key in schedules_by_period:
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

    def __init__(self, controller: DesktopController, parent=None):
        super().__init__(parent)

        self._controller = controller

        self._schedules_by_period: dict[str, list[Schedule]] = {}
        self._courses_by_id: dict[str, Course] = {}
        self._prog_color_map: dict[str, str] = {}
        self._period_indices: dict[str, int] = {}
        self._truncated_periods: set[str] = set()
        self._is_imported_schedule: bool = False

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

        # Per-period Auto Load is user-controlled. It loads one batch, waits
        # AUTO_LOAD_DELAY_MS, then requests the next batch until there is no more
        # data or the user presses Stop Auto Load. Never use a blocking while-loop.
        self._stale_banner: QLabel = QLabel()
        self._save_btn: QPushButton = QPushButton()

        self._setup_ui()

    def mark_stale(self) -> None:
        """Show the stale-data warning and disable schedule/report exports."""
        self._has_stale_results = True
        self._stale_banner.setVisible(True)
        self._save_btn.setEnabled(False)
        self._proctor_btn.setEnabled(False)

    def clear_stale(self) -> None:
        """Hide the stale-data warning and re-enable Export."""
        self._has_stale_results = False
        self._stale_banner.setVisible(False)
        self._save_btn.setEnabled(True)
        self._proctor_btn.setEnabled(True)

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

        # Stop any in-flight Load More operation before rebuilding the results UI.
        # A QTimer timeout may already be queued while a new generation/load starts,
        # so cleanup must happen before old cards/widgets are removed.
        self._lm.reset()

        # Stop idle persistent load-more workers from the previous result set.
        # They will be recreated lazily if the user clicks Load More / Auto again.
        self._controller.shutdown_load_workers()

        # Imported schedules are fixed read-only snapshots. Do not keep any
        # old generation/load-more state from a previous Generate run.
        if read_only_import:
            self._controller.reset_generation_state()

        self._schedules_by_period = schedules_by_period
        self._courses_by_id = courses_by_id
        self._prog_color_map = prog_color_map
        self._truncated_periods = (
            set()
            if read_only_import
            else (truncated_periods or set())
        )
        self._period_indices = {k: 0 for k in schedules_by_period}
        self._total_by_period = {}

        for key, scheds in schedules_by_period.items():
            if key not in self._truncated_periods:
                self._total_by_period[key] = len(scheds)

        all_period_keys = _merge_period_keys(self._controller, schedules_by_period)
        merged: dict[str, list[Schedule]] = {k: [] for k in all_period_keys}
        merged.update(schedules_by_period)

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

        has_proctor_report = any(
            bool(getattr(schedule, "classroom_assignments", None))
            for schedules in merged.values()
            for schedule in schedules
        )
        self._proctor_btn.setVisible(has_proctor_report)

        self._update_summary()
        self._placeholder.setVisible(False)
        self._content.setVisible(True)

        # Avoid opacity effects while rebuilding result widgets.
        # QGraphicsOpacityEffect caused QPainter warnings and visual flicker.
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

        # Anti-OOM guardrail: never let the in-memory population exceed the hard
        # cap, no matter how many times the user clicks Load More / Auto Load.
        # Trim the incoming batch to the remaining headroom; if we are already at
        # the cap, drop the batch entirely. Load More / Auto Load callers observe
        # this via is_at_memory_cap() and stop requesting further pages.
        headroom = ABSOLUTE_MAX_IN_MEMORY_SCHEDULES - self.total_in_memory_schedule_count()
        if headroom <= 0:
            logger.warning(
                "In-memory schedule cap (%s) reached; refusing further load for %s.",
                ABSOLUTE_MAX_IN_MEMORY_SCHEDULES,
                period_key,
            )
            return
        if len(extra) > headroom:
            logger.warning(
                "In-memory schedule cap (%s) reached; truncating batch for %s "
                "from %s to %s schedules.",
                ABSOLUTE_MAX_IN_MEMORY_SCHEDULES,
                period_key,
                len(extra),
                headroom,
            )
            extra = extra[:headroom]

        self._schedules_by_period[period_key].extend(extra)

        # Re-sort the full accumulated set after appending the new page.
        # Sorting only the fresh page is not enough: once Load More / Auto
        # Variants adds another block, the combined list must still reflect the
        # active global ranking. cache_generated_results() returns the sorted
        # full cache, so keep the panel state in sync with it.
        self._schedules_by_period = self._controller.cache_generated_results(
            dict(self._schedules_by_period)
        )
        self._period_indices[period_key] = min(
            self._period_indices.get(period_key, 0),
            max(0, len(self._schedules_by_period[period_key]) - 1),
        )
        self._rebuild_navigation_cache(period_key)

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

    def total_in_memory_schedule_count(self) -> int:
        """Return the total number of schedules resident in RAM across periods."""
        return sum(len(scheds) for scheds in self._schedules_by_period.values())

    def is_at_memory_cap(self) -> bool:
        """Return True once the hard in-memory schedule cap has been reached.

        Load More / Auto Load consult this to stop fetching further pages before
        the process is OOM-killed. See ABSOLUTE_MAX_IN_MEMORY_SCHEDULES.
        """
        return self.total_in_memory_schedule_count() >= ABSOLUTE_MAX_IN_MEMORY_SCHEDULES

    def get_current_index(self, period_key: str) -> int:
        """Return the currently displayed schedule index for *period_key*."""
        return self._period_indices.get(period_key, 0)

    def get_card(self, period_key: str) -> PeriodCardWidgets | None:
        """Return the period card widgets for *period_key*, if built."""
        return self._cards.get(period_key)

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

    def _setup_ui(self) -> None:
        self.setStyleSheet("background: transparent;")

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
        self._ranking_btn = QPushButton("⇅  Result Ranking")
        self._ranking_btn.setStyleSheet(
            "QPushButton {"
            " background: #2563EB; color: #FFFFFF; font-weight: 700;"
            " border: none; border-radius: 8px; padding: 7px 18px; }"
            "QPushButton:hover { background: #1D4ED8; }"
            "QPushButton:disabled { background: #C7D2DE; color: #FFFFFF; }"
        )
        self._ranking_btn.clicked.connect(self._on_result_ranking)
        action_row.addWidget(self._ranking_btn)

        self._save_btn = QPushButton("⬇  Export Schedule")
        self._save_btn.clicked.connect(self._on_save)
        action_row.addWidget(self._save_btn)

        # Spec 4.6: per-schedule proctor report (GUI view + .txt export).
        self._proctor_btn = QPushButton("🧑‍🏫  Proctor Report")
        self._proctor_btn.clicked.connect(self._on_proctor_report)
        action_row.addWidget(self._proctor_btn)

        cl.addLayout(action_row)

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

        tip_lbl = QLabel("Tip: Click on any scheduled exam date to view full details.")
        tip_lbl.setStyleSheet(
            "background: rgba(0,90,194,0.06); color: #004394;"
            " border: 1px solid rgba(0,90,194,0.12); border-radius: 8px;"
            " padding: 8px 14px; font-size: 12px; font-weight: 500;"
        )
        tip_lbl.setWordWrap(True)

        cl.addWidget(tip_lbl)

        self._period_tabs = QTabWidget()
        self._period_tabs.setStyleSheet(PERIOD_TAB_STYLE)
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
        """Return True if the loaded period contains classroom-assignment data."""
        return any(
            self._schedule_has_classroom_data(schedule)
            for schedule in self._schedules_by_period.get(period_key, [])
        )

    def _rebuild_navigation_cache(self, period_key: str | None = None) -> None:
        """Rebuild navigation indexes through NavigationModel."""
        self._nav_model.rebuild(period_key)

    def _date_options_for_period(
        self,
        period_key: str,
    ) -> list[tuple[_DateSignature, list[int]]]:
        """Return cached date options through NavigationModel."""
        return self._nav_model.date_options(period_key)

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
        card.load_more_btn.setEnabled(
            has_more
            and period_key not in self._lm.procs
            and period_key not in self._lm.auto_load_periods
        )

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

        if not non_empty:
            self._summary_lbl.setStyleSheet(
                "color: #DC2626; font-weight: 600; font-size: 12px;"
            )
            self._summary_lbl.setText("⚠  No valid schedules found.")
            return

        period_schedules_total = sum(
            len(schedules)
            for schedules in non_empty.values()
        )

        combined_options_total = self._controller.get_combined_schedule_count(
            non_empty
        )

        self._summary_lbl.setStyleSheet(
            "color: #059669; font-weight: 600; font-size: 12px;"
        )

        if self._is_imported_schedule:
            self._summary_lbl.setText(
                f"✓  Imported schedule loaded "
                f"({period_schedules_total:,} period schedules in view)"
            )
            return

        has_more = any(
            self._controller.has_more_schedules(period_key)
            or period_key in self._truncated_periods
            for period_key in non_empty
        )

        if has_more:
            self._summary_lbl.setText(
                f"✓  {combined_options_total:,} combined schedule options available "
                f"({period_schedules_total:,} period schedules loaded so far)"
            )
        else:
            self._summary_lbl.setText(
                f"✓  {combined_options_total:,} combined schedule options available "
                f"({period_schedules_total:,} period schedules loaded in total)"
            )

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
        """Re-rank cached schedules in memory and refresh the displayed results."""
        try:
            resorted = self._controller.resort(config)
        except ValueError:
            # No cached results to re-rank; keep the new order for next generate.
            self._controller.apply_sort(config)
            return

        self.load(
            resorted,
            self._courses_by_id,
            self._prog_color_map,
            truncated_periods=self.get_truncated_periods(),
            read_only_import=self._is_imported_schedule,
        )

    def _on_proctor_report(self) -> None:
        """Build and show the spec 4.6 proctor report for displayed schedules."""
        if self._has_stale_results:
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
        if self._has_stale_results:
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
