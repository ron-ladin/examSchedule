"""
Widget: _ResultsPanel — Schedule Results Tab (SRS §3.1–§3.5)
--------------------------------------------------------------
Shows one exam-period card per period with independent Prev/Next navigation.
Each card has a "Load More" button when more schedules exist beyond the initial
RESULT_BATCH_SIZE batch — clicking it spawns a background subprocess to fetch
only the next batch.

Public API:
    load(schedules_by_period, courses_by_id, prog_color_map, truncated_periods)
"""

import logging
import multiprocessing
from datetime import date, timedelta
from pathlib import Path
from queue import Empty as _QueueEmpty

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.ui.assets.animated_widgets import AnimatedPlaceholder
from src.ui.calendar_cell_delegate import (
    _CalendarCellDelegate,
    _course_ids_for_click_position,
    _group_exams_by_slot,
)
from src.ui.tokens import (
    COLOR_CAL_EXCLUDED_BG as _EXCLUDED_BG,
    PERIOD_TAB_STYLE,
    programme_display_name,
)

from src.controller import DesktopController, RESULT_BATCH_SIZE
from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.semester import display_semester
from src.ui.period_utils import STANDARD_PERIOD_ORDER as _STANDARD_PERIOD_ORDER

logger = logging.getLogger(__name__)


class _CalendarTable(QTableWidget):
    """Calendar table that reports where inside a date cell the user clicked."""

    calendarCellClicked = pyqtSignal(int, int, QPoint)

    def mouseReleaseEvent(self, event) -> None:
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and event.button() == Qt.MouseButton.LeftButton:
            self.calendarCellClicked.emit(
                index.row(),
                index.column(),
                event.position().toPoint(),
            )
        super().mouseReleaseEvent(event)


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


_SPINNER_CHARS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


_NAV_REPEAT_DELAY_MS = 450
_NAV_REPEAT_INTERVAL_MS = 120


def _enable_press_and_hold(button: QPushButton) -> None:
    """Repeat button clicks while it remains pressed."""
    button.setAutoRepeat(True)
    button.setAutoRepeatDelay(_NAV_REPEAT_DELAY_MS)
    button.setAutoRepeatInterval(_NAV_REPEAT_INTERVAL_MS)


def _make_data_table(headers: list[str]) -> QTableWidget:
    table = _CalendarTable()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setMinimumHeight(36)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    return table


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
    """

    def __init__(self, controller: DesktopController, parent=None):
        super().__init__(parent)

        self._controller = controller

        self._schedules_by_period: dict[str, list[Schedule]] = {}
        self._courses_by_id: dict[str, Course] = {}
        self._prog_color_map: dict[str, str] = {}
        self._period_indices: dict[str, int] = {}
        self._truncated_periods: set[str] = set()

        self._counter_labels: dict[str, QLabel] = {}
        self._cal_tables: dict[str, QTableWidget] = {}
        self._prev_btns: dict[str, QPushButton] = {}
        self._next_btns: dict[str, QPushButton] = {}
        self._load_more_btns: dict[str, QPushButton] = {}

        self._lm_queues: dict[str, multiprocessing.Queue] = {}
        self._lm_chunk_sizes: dict[str, int | None] = {}
        self._lm_procs: dict[str, multiprocessing.Process] = {}
        self._lm_timers: dict[str, QTimer] = {}
        self._lm_ticks: dict[str, int] = {}
        self._lm_advance_after_load: set[str] = set()

        self._total_by_period: dict[str, int] = {}
        self._cell_data: dict[str, dict[tuple[int, int], tuple]] = {}
        self._empty_labels: dict[str, QLabel] = {}

        self._has_stale_results: bool = False
        # §1: never auto-load endlessly. Each "load more" restarts generation and
        # skips already-loaded schedules via offset, so background auto-loading
        # gets quadratically more expensive (loading 100k–101k re-skips 100k).
        # Loading is therefore manual/on-demand: the user clicks "+N more options".
        self._auto_load_results: bool = False
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
    ) -> None:
        self.clear_stale()

        # Stop any in-flight Load More operation before rebuilding the results UI.
        # A QTimer timeout may already be queued while a new generation/load starts,
        # so cleanup must happen before old cards/widgets are removed.
        for key in set(self._lm_procs) | set(self._lm_timers) | set(self._lm_queues):
            self._cleanup_load_more_state(key, terminate=True)

        self._schedules_by_period = schedules_by_period
        self._courses_by_id = courses_by_id
        self._prog_color_map = prog_color_map
        self._truncated_periods = truncated_periods or set()
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

        self._period_tabs.clear()

        self._counter_labels.clear()
        self._cal_tables.clear()
        self._prev_btns.clear()
        self._next_btns.clear()
        self._load_more_btns.clear()
        self._cell_data.clear()
        self._empty_labels.clear()

        for period_key in merged:
            self._period_tabs.addTab(
                self._build_period_card(period_key),
                _display_period_key(period_key),
            )

        self._update_summary()
        self._placeholder.setVisible(False)
        self._content.setVisible(True)

        # Avoid opacity effects while rebuilding result widgets.
        # QGraphicsOpacityEffect caused QPainter warnings and visual flicker.
        self._content.setGraphicsEffect(None)

        if self._auto_load_results:
            QTimer.singleShot(0, self._start_automatic_loads)

    def _start_automatic_loads(self) -> None:
        """Continue loading every truncated period in the background."""
        for period_key in list(self._truncated_periods):
            if period_key not in self._lm_procs:
                self._on_load_more(period_key)

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
        card = QWidget()
        card.setStyleSheet("background: transparent;")
        card.setMinimumHeight(320)

        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        nav = QHBoxLayout()

        prev_btn = QPushButton("◀  Prev")
        prev_btn.setFixedWidth(90)
        _enable_press_and_hold(prev_btn)
        prev_btn.clicked.connect(lambda _=False, k=period_key: self._go_prev_period(k))

        counter = QLabel("Loading…")
        counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        counter.setStyleSheet(
            "font-weight: 700; color: #005ac2; font-size: 13px;"
            "background: rgba(0, 90, 194, 0.06);"
            "border: 1px solid rgba(0, 90, 194, 0.15);"
            "border-radius: 10px; padding: 6px 20px;"
        )

        next_btn = QPushButton("Next  ▶")
        next_btn.setFixedWidth(90)
        _enable_press_and_hold(next_btn)
        next_btn.clicked.connect(lambda _=False, k=period_key: self._go_next_period(k))

        nav.addWidget(prev_btn)
        nav.addStretch()
        nav.addWidget(counter)
        nav.addStretch()
        nav.addWidget(next_btn)

        layout.addLayout(nav)

        has_more = period_key in self._truncated_periods

        lm_row = QHBoxLayout()
        lm_row.setSpacing(8)

        chunk_btn = QPushButton(f"⟳  +{RESULT_BATCH_SIZE:,} more options")
        chunk_btn.setStyleSheet(
            "color: #005ac2; border: 2px solid #005ac2; border-radius: 8px;"
            "padding: 6px 12px; font-size: 11px; font-weight: 600;"
            "background: rgba(0, 90, 194, 0.06);"
        )
        chunk_btn.setVisible(has_more and not self._auto_load_results)
        chunk_btn.clicked.connect(lambda _=False, k=period_key: self._on_load_more(k))

        lm_row.addWidget(chunk_btn)
        lm_row.addStretch()

        layout.addLayout(lm_row)

        table = _make_data_table(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
        table.setMinimumHeight(220)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setItemDelegate(_CalendarCellDelegate(table))
        table.setStyleSheet("""
            QTableWidget {
                border: none;
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.85);
                gridline-color: rgba(194, 198, 214, 0.25);
            }
            QHeaderView::section {
                background: #005ac2;
                color: white;
                font-weight: 700;
                font-size: 11px;
                padding: 6px 4px;
                border: none;
                border-right: 1px solid #004494;
            }
            QHeaderView::section:last-child { border-right: none; }
        """)
        layout.addWidget(table)

        empty_lbl = QLabel("No exams scheduled for this period.")
        empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_lbl.setStyleSheet(
            "color: #72778c; font-size: 13px; padding: 24px; background: transparent;"
        )
        empty_lbl.setVisible(False)
        layout.addWidget(empty_lbl)

        self._counter_labels[period_key] = counter
        self._cal_tables[period_key] = table
        self._empty_labels[period_key] = empty_lbl
        self._prev_btns[period_key] = prev_btn
        self._next_btns[period_key] = next_btn
        self._load_more_btns[period_key] = chunk_btn

        table.calendarCellClicked.connect(
            lambda row, col, pos, k=period_key: self._on_cell_clicked(
                k, row, col, pos
            )
        )

        self._refresh_period_card(period_key)
        return card

    def _refresh_period_card(self, period_key: str) -> None:
        schedules = self._schedules_by_period[period_key]
        idx = self._period_indices[period_key]
        total = len(schedules)
        has_more = self._controller.has_more_schedules(period_key)

        known_total = self._total_by_period.get(period_key)
        display_total = known_total if known_total is not None else total

        if total == 0:
            nav_text = "0 / 0"
            if period_key in self._empty_labels:
                self._empty_labels[period_key].setVisible(True)
                self._cal_tables[period_key].setVisible(False)
        else:
            nav_text = f"{idx + 1:,} / {display_total:,}"
            if period_key in self._empty_labels:
                self._empty_labels[period_key].setVisible(False)
                self._cal_tables[period_key].setVisible(True)

        self._counter_labels[period_key].setText(nav_text)
        self._prev_btns[period_key].setEnabled(idx > 0)
        self._next_btns[period_key].setEnabled(idx < total - 1 or has_more)

        if period_key in self._load_more_btns:
            self._load_more_btns[period_key].setVisible(
                has_more and not self._auto_load_results
            )

        if schedules:
            self._populate_calendar(
                self._cal_tables[period_key],
                schedules[idx],
                period_key,
            )
        else:
            table = self._cal_tables[period_key]
            table.clearContents()
            table.setRowCount(0)

        self._update_summary()

    def _go_prev_period(self, period_key: str) -> None:
        if self._period_indices[period_key] > 0:
            self._period_indices[period_key] -= 1
            self._refresh_period_card(period_key)

    def _go_next_period(self, period_key: str) -> None:
        idx = self._period_indices[period_key]
        target = idx + 1
        schedules = self._schedules_by_period[period_key]

        if target >= len(schedules) and self._controller.has_more_schedules(period_key):
            self._lm_advance_after_load.add(period_key)
            self._on_load_more(period_key)
            return

        if target < len(schedules):
            self._period_indices[period_key] = target

        remaining_loaded = len(schedules) - self._period_indices[period_key] - 1

        if (
            remaining_loaded <= 100
            and self._controller.has_more_schedules(period_key)
            and period_key not in self._lm_procs
        ):
            self._on_load_more(period_key)

        self._refresh_period_card(period_key)

    def _on_load_more(self, period_key: str, chunk_size: int | None = None) -> None:
        if period_key in self._lm_procs:
            return

        already = len(self._schedules_by_period[period_key])
        queue, proc = self._controller.start_load_more_for_period(period_key, already)

        self._lm_queues[period_key] = queue
        self._lm_procs[period_key] = proc
        self._lm_ticks[period_key] = 0
        self._lm_chunk_sizes[period_key] = RESULT_BATCH_SIZE

        btn = self._load_more_btns.get(period_key)
        if btn is not None and not self._auto_load_results:
            btn.setEnabled(False)
            btn.setText(f"⠋  Loading {RESULT_BATCH_SIZE:,}…")

        timer = QTimer(self)
        timer.timeout.connect(lambda: self._poll_load_more(period_key))
        timer.start(150)

        self._lm_timers[period_key] = timer

    def _poll_load_more(self, period_key: str) -> None:
        queue = self._lm_queues.get(period_key)
        if queue is None:
            # The results were rebuilt while this timer callback was already queued.
            # Exit safely instead of raising KeyError on stale state.
            self._cleanup_load_more_state(period_key, terminate=True)
            return

        tick = self._lm_ticks.get(period_key, 0)
        spinner = _SPINNER_CHARS[tick % len(_SPINNER_CHARS)]
        self._lm_ticks[period_key] = tick + 1

        btn = self._load_more_btns.get(period_key)
        if btn and not self._auto_load_results:
            btn.setText(f"{spinner}  Loading {RESULT_BATCH_SIZE:,}…")

        try:
            result = queue.get_nowait()
        except _QueueEmpty:
            proc = self._lm_procs.get(period_key)

            # If the subprocess already ended and no result arrived, recover the UI
            # instead of leaving the button disabled forever.
            if proc is not None and not proc.is_alive() and tick > 2:
                if btn and not self._auto_load_results:
                    btn.setEnabled(True)
                    btn.setText("⚠  Load failed — retry")

                logger.error(
                    "Load more process ended without returning a result for %s",
                    period_key,
                )
                self._cleanup_load_more_state(period_key, terminate=False)

            return
        except OSError as exc:
            if btn and not self._auto_load_results:
                btn.setEnabled(True)
                btn.setText("⚠  Load failed — retry")

            logger.error("Load more queue failed for %s: %s", period_key, exc)
            self._cleanup_load_more_state(period_key, terminate=True)
            return

        timer = self._lm_timers.pop(period_key, None)
        if timer:
            timer.stop()

        if not (
            isinstance(result, tuple)
            and len(result) == 4
            and result[0] is True
            and isinstance(result[1], dict)
            and isinstance(result[2], dict)
            and isinstance(result[3], set)
        ):
            error_details = (
                result[1]
                if isinstance(result, tuple) and len(result) > 1
                else result
            )

            if btn and not self._auto_load_results:
                btn.setEnabled(True)
                btn.setText("⚠  Load failed — retry")

            logger.error("Load more failed for %s: %s", period_key, error_details)
            self._cleanup_load_more_state(period_key, terminate=True)
            return

        _, all_by_period, _courses_by_id, truncated_periods = result

        old_len = len(self._schedules_by_period[period_key])
        extra = all_by_period.get(period_key, [])
        still_more = period_key in truncated_periods

        if extra:
            self._schedules_by_period[period_key].extend(extra)
            # Keep _last_results in sync so resort() includes load-more schedules
            # (C2 fix: previously _last_results was never updated on load-more,
            # causing a subsequent re-sort to silently drop the appended batch).
            self._controller.cache_generated_results(dict(self._schedules_by_period))

        if period_key in self._lm_advance_after_load:
            self._lm_advance_after_load.discard(period_key)

            if extra and old_len < len(self._schedules_by_period[period_key]):
                self._period_indices[period_key] = old_len

        self._controller.set_has_more_for_period(period_key, still_more)

        if still_more:
            self._truncated_periods.add(period_key)
        else:
            self._truncated_periods.discard(period_key)
            self._total_by_period[period_key] = len(
                self._schedules_by_period[period_key]
            )

        self._cleanup_load_more_state(period_key)
        self._refresh_period_card(period_key)

        if still_more and btn and not self._auto_load_results:
            btn.setEnabled(True)
            btn.setText(f"⟳  +{RESULT_BATCH_SIZE:,} more options")

        if self._auto_load_results and still_more and extra:
            QTimer.singleShot(50, lambda k=period_key: self._on_load_more(k))

    def _cleanup_load_more_state(
        self,
        period_key: str,
        terminate: bool = False,
    ) -> None:
        timer = self._lm_timers.pop(period_key, None)
        if timer is not None:
            timer.stop()

        self._lm_queues.pop(period_key, None)
        self._lm_chunk_sizes.pop(period_key, None)
        self._lm_ticks.pop(period_key, None)
        self._lm_advance_after_load.discard(period_key)

        proc = self._lm_procs.pop(period_key, None)
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

        has_more = any(
            self._controller.has_more_schedules(period_key)
            or period_key in self._truncated_periods
            for period_key in non_empty
        )

        self._summary_lbl.setStyleSheet(
            "color: #059669; font-weight: 600; font-size: 12px;"
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

    def _populate_calendar(
        self,
        table: QTableWidget,
        schedule: Schedule,
        period_key: str = "",
    ) -> None:
        table.clearContents()
        table.setRowCount(0)
        self._cell_data[period_key] = {}

        if not schedule.assignments:
            return

        period_lookup = {p.get_key(): p for p in self._controller.get_exam_periods()}
        period_obj = period_lookup.get(period_key)
        excluded_dates: set[date] = period_obj.excluded_dates if period_obj else set()

        date_to_ids: dict[date, list[str]] = {}
        for course_id, exam_date in schedule.assignments.items():
            date_to_ids.setdefault(exam_date, []).append(course_id)

        week_start, num_weeks = self._calendar_bounds(period_obj, date_to_ids)
        table.setRowCount(num_weeks)

        for week in range(num_weeks):
            for dow in range(7):
                current_date = week_start + timedelta(days=week * 7 + dow)
                course_ids = date_to_ids.get(current_date, [])
                course_lines, first_prog = self._build_cell_lines(course_ids, schedule)

                date_header = current_date.strftime("%a %d/%m")
                cell_text = (
                    f"{date_header}\n{'─' * 14}\n" + "\n".join(course_lines)
                    if course_lines
                    else date_header
                )

                item = QTableWidgetItem(cell_text)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
                )

                if course_ids:
                    item.setToolTip("Click to view exam details")

                # §4.5: when exams have slot assignments, render them as
                # side-by-side per-slot colored columns (with >3 collapse).
                slot_groups: list[dict] | None = None
                if any(
                    schedule.classroom_assignments.get(course_id)
                    for course_id in course_ids
                ):
                    slot_groups = _group_exams_by_slot(
                        course_ids, schedule, self._courses_by_id
                    )
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        {"header": date_header, "groups": slot_groups},
                    )
                    tooltip_lines = [f"{len(course_ids)} exams on {date_header}"]
                    for group in slot_groups:
                        tooltip_lines.append(
                            f"{group['slot']} ({len(group['course_ids'])}): "
                            + ", ".join(group["names"])
                        )
                    tooltip_lines.append("Click a time group to view its exams.")
                    item.setToolTip("\n".join(tooltip_lines))

                if first_prog and first_prog in self._prog_color_map:
                    color = QColor(self._prog_color_map[first_prog])
                    color.setAlpha(75)
                    item.setBackground(color)
                elif current_date in excluded_dates:
                    item.setBackground(QColor(_EXCLUDED_BG))

                table.setItem(week, dow, item)
                self._cell_data[period_key][(week, dow)] = (
                    current_date,
                    list(course_ids),
                    {
                        course_id: list(
                            schedule.classroom_assignments.get(course_id, [])
                        )
                        for course_id in course_ids
                    },
                    {
                        course_id: schedule.unassigned_classroom_exams[course_id]
                        for course_id in course_ids
                        if course_id in schedule.unassigned_classroom_exams
                    },
                    slot_groups,
                )

        table.resizeRowsToContents()

    @staticmethod
    def _calendar_bounds(period_obj, date_to_ids: dict) -> tuple[date, int]:
        """Return (week_start Sunday, week count) spanning the period's dates."""
        if period_obj and period_obj.date_ranges:
            start, end = period_obj.get_overall_date_boundaries()
        else:
            all_dates = sorted(date_to_ids)
            start, end = all_dates[0], all_dates[-1]

        week_start = start - timedelta(days=(start.weekday() + 1) % 7)
        last_saturday = end + timedelta(days=(5 - end.weekday()) % 7)
        num_weeks = (last_saturday - week_start).days // 7 + 1
        return week_start, num_weeks

    def _build_cell_lines(
        self,
        course_ids: list[str],
        schedule: Schedule,
    ) -> tuple[list[str], str | None]:
        """Build the text lines for one calendar cell and its first programme."""
        first_prog: str | None = None
        course_lines: list[str] = []

        for course_id in course_ids:
            course = self._courses_by_id.get(course_id)

            if not course:
                course_lines.append(course_id)
                continue

            relevant = next(
                (
                    offering
                    for offering in course.offerings
                    if offering.program_id in self._prog_color_map
                ),
                None,
            )

            req = "E" if (relevant and relevant.is_elective()) else "O"
            prog_id = relevant.program_id if relevant else ""

            if first_prog is None:
                first_prog = prog_id

            course_lines.append(f"  {course.name[:18]}")
            course_lines.append(f"  {course_id}  ·  {req}")

            relevant_programs = list(dict.fromkeys(
                offering.program_id
                for offering in course.offerings
                if offering.program_id in self._prog_color_map
            ))
            if relevant_programs:
                degree_label = "; ".join(
                    programme_display_name(program_id)
                    for program_id in relevant_programs
                )
                course_lines.append(f"  Degree: {degree_label}")

            room_assignments = schedule.classroom_assignments.get(course_id, [])
            if room_assignments:
                slot_text = room_assignments[0].slot.time.strftime("%H:%M")
                rooms_text = ", ".join(
                    f"{assignment.room.room_id} "
                    f"({assignment.students_assigned}/"
                    f"{assignment.room.capacity})"
                    for assignment in room_assignments
                )
                course_lines.append(f"  {slot_text}  ·  {rooms_text}")
            elif course_id in schedule.unassigned_classroom_exams:
                missing = schedule.unassigned_classroom_exams[course_id]
                course_lines.append(f"  NO CLASSROOM  ·  {missing} students")

        return course_lines, first_prog

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

        table = self._cal_tables.get(period_key)
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

    def _selected_schedules(self) -> dict[str, "Schedule"]:
        """Currently displayed schedule per period (one each)."""
        return {
            key: self._schedules_by_period[key][self._period_indices[key]]
            for key in self._schedules_by_period
            if self._schedules_by_period[key]
        }

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
                "Generate schedules before viewing the proctor report.",
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
                "No schedules have been generated.",
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
            self._controller.export(selected, Path(path))
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
