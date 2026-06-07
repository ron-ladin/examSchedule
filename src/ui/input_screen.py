"""
Widget: InputScreen — QStackedWidget(ConfigScreen [0], ResultsScreen [1]).

Screen transitions
------------------
Config → Results : generation_started  → switch + show loading spinner
                   schedule_generated  → load results + hide spinner
Results → Config : "← Back" button
Failure          : generation_failed   → hide spinner + back to Config + error dialog
"""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.controller import DesktopController
from src.domain.course import Course
from src.domain.schedule import Schedule
from src.ui.config_screen import ConfigScreen
from src.ui.date_editor import DateEditorWidget
from src.ui.results_panel import _ResultsPanel, _display_period_key, _make_data_table
from src.ui.tokens import PERIOD_TAB_STYLE, PROGRAM_NAMES_MAPPING

logger = logging.getLogger(__name__)

_COURSE_TABLE_HEADERS = [
    "Course Name", "Course ID", "Year", "Semester",
    "Requirement", "Evaluation", "Program ID", "Program Name",
]
_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_LOGO_PNG = str(Path(__file__).parent / "assets" / "logo.png")

_TAB_ACTIVE_STYLE = (
    "QPushButton {"
    " background: rgba(0, 90, 194, 0.06);"
    " color: #005ac2;"
    " border-top: none; border-left: none; border-right: none;"
    " border-bottom: 3px solid #005ac2;"
    " border-radius: 0;"
    " padding: 4px 22px;"
    " font-size: 13px;"
    " font-weight: 700;"
    "}"
)

_TAB_INACTIVE_STYLE = (
    "QPushButton {"
    " background: transparent;"
    " color: #42474e;"
    " border: none;"
    " border-radius: 0;"
    " padding: 4px 22px;"
    " font-size: 13px;"
    " font-weight: 500;"
    "}"
    "QPushButton:hover {"
    " background: rgba(0, 90, 194, 0.04);"
    " color: #005ac2;"
    "}"
)


class ResultsScreen(QWidget):
    """Screen 1: Course Details | Exam Periods | Schedule Results + loading pane."""

    back_requested = pyqtSignal()

    def __init__(self, controller: DesktopController, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._date_editors: dict[str, DateEditorWidget] = {}
        self._spin_tick = 0
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._tick_spinner)
        self._results_loaded: bool = False
        self._setup_ui()

    def show_loading(self) -> None:
        self._content_stack.setCurrentIndex(0)
        self._spin_tick = 0
        self._spin_timer.start(90)

    def hide_loading(self) -> None:
        self._spin_timer.stop()
        self._content_stack.setCurrentIndex(1)

    def load(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        truncated_periods: set[str],
    ) -> None:
        self._results_panel.load(
            schedules_by_period,
            courses_by_id,
            prog_color_map,
            truncated_periods,
        )
        self._workspace.setCurrentIndex(2)
        self._results_loaded = True

    def refresh_courses(self, selected_ids: list[str]) -> None:
        self._course_table.setRowCount(0)

        for prog_id in selected_ids:
            for course in self._controller.get_courses_by_programme(prog_id):
                for offering in course.offerings:
                    if offering.program_id != prog_id:
                        continue

                    row = self._course_table.rowCount()
                    self._course_table.insertRow(row)
                    prog_name = PROGRAM_NAMES_MAPPING.get(prog_id, prog_id)

                    for col, value in enumerate([
                        course.name,
                        course.id,
                        str(offering.year),
                        offering.semester,
                        offering.requirement,
                        course.evaluation_type,
                        prog_id,
                        prog_name,
                    ]):
                        item = QTableWidgetItem(value)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        self._course_table.setItem(row, col, item)

        has_rows = self._course_table.rowCount() > 0
        self._courses_placeholder.setVisible(not has_rows)
        self._course_table.setVisible(has_rows)

    def refresh_periods(self) -> None:
        self._periods_tabs.clear()
        self._date_editors.clear()

        periods = self._controller.get_exam_periods()
        if not periods:
            self._no_periods_hint.setVisible(True)
            self._periods_tabs.setVisible(False)
            return

        self._no_periods_hint.setVisible(False)
        self._periods_tabs.setVisible(True)

        for period in periods:
            key = period.get_key()
            editor = DateEditorWidget(period)
            editor.period_changed.connect(self._sync_periods)
            self._date_editors[key] = editor
            self._periods_tabs.addTab(editor, _display_period_key(key))

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        self._content_stack = QStackedWidget()
        self._content_stack.addWidget(self._build_loading_pane())
        self._content_stack.addWidget(self._build_workspace())
        self._content_stack.setCurrentIndex(1)
        root.addWidget(self._content_stack)

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setObjectName("appHeader")
        hdr.setFixedHeight(80)

        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 0, 0)
        hl.setSpacing(12)

        back_btn = QPushButton("← Back")
        back_btn.setFixedSize(90, 36)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(
            "QPushButton { background: #dee3eb; color: #42474e;"
            " border: 1px solid rgba(194,198,214,0.6); border-radius: 8px;"
            " font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: rgba(0,90,194,0.08); color: #005ac2;"
            " border-color: #005ac2; }"
        )
        back_btn.clicked.connect(self.back_requested.emit)

        hl.addWidget(back_btn)
        hl.addSpacing(8)

        logo = QLabel()
        logo.setStyleSheet("background: transparent; border: none;")
        logo.setFixedSize(32, 32)

        pix = QPixmap(_LOGO_PNG)
        if not pix.isNull():
            logo.setPixmap(
                pix.scaled(
                    32,
                    32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        hl.addWidget(logo)

        brand = QLabel("Syncacademic")
        brand.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #005ac2;"
            " letter-spacing: -0.5px; background: transparent;"
        )
        hl.addWidget(brand)
        hl.addStretch()

        self._tab_btns: list[QPushButton] = []
        for i, name in enumerate(["Course Details", "Exam Periods", "Schedule Results"]):
            btn = QPushButton(name)
            btn.setFixedHeight(80)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            self._tab_btns.append(btn)
            hl.addWidget(btn)

        self._update_tab_buttons(0)
        return hdr

    def _build_loading_pane(self) -> QWidget:
        pane = QWidget()
        pane.setStyleSheet("background: #f6faff;")

        vl = QVBoxLayout(pane)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.setSpacing(14)

        self._spinner_lbl = QLabel("⠋")
        self._spinner_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spinner_lbl.setStyleSheet(
            "font-size: 52px; color: #005ac2; background: transparent;"
        )
        vl.addWidget(self._spinner_lbl)

        msg = QLabel("Generating schedules…\nThis may take a few seconds.")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("font-size: 14px; color: #42474e; background: transparent;")
        vl.addWidget(msg)

        return pane

    def _build_workspace(self) -> QTabWidget:
        self._workspace = QTabWidget()
        self._workspace.tabBar().hide()
        self._workspace.tabBar().setFixedHeight(0)
        self._workspace.currentChanged.connect(self._update_tab_buttons)

        course_tab = QWidget()
        course_tab.setStyleSheet("background:transparent;")

        ctl = QVBoxLayout(course_tab)
        ctl.setContentsMargins(0, 8, 0, 0)

        self._courses_placeholder = QLabel(
            "No courses loaded yet.\n\nLoad a courses file and select a programme."
        )
        self._courses_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._courses_placeholder.setStyleSheet("font-size:13px; color:#72778c;")
        ctl.addWidget(self._courses_placeholder)

        self._course_table = _make_data_table(_COURSE_TABLE_HEADERS)
        hh = self._course_table.horizontalHeader()

        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)

        for col in (1, 2, 3, 4, 5, 6):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        self._course_table.setVisible(False)
        ctl.addWidget(self._course_table)
        self._workspace.addTab(course_tab, "Course Details")

        periods_ctr = QWidget()
        periods_ctr.setStyleSheet("background:transparent;")

        ptl = QVBoxLayout(periods_ctr)
        ptl.setContentsMargins(4, 4, 4, 4)

        self._no_periods_hint = QLabel("Load an exam-periods file to edit dates here.")
        self._no_periods_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ptl.addWidget(self._no_periods_hint)

        self._periods_tabs = QTabWidget()
        self._periods_tabs.setStyleSheet(PERIOD_TAB_STYLE)
        self._periods_tabs.setVisible(False)
        ptl.addWidget(self._periods_tabs)
        self._workspace.addTab(periods_ctr, "Exam Periods")

        self._results_panel = _ResultsPanel(self._controller)
        self._workspace.addTab(self._results_panel, "Schedule Results")

        return self._workspace

    def _switch_tab(self, idx: int) -> None:
        self._workspace.setCurrentIndex(idx)
        self._update_tab_buttons(idx)

    def _update_tab_buttons(self, active_idx: int) -> None:
        for i, btn in enumerate(self._tab_btns):
            btn.setStyleSheet(_TAB_ACTIVE_STYLE if i == active_idx else _TAB_INACTIVE_STYLE)

    def reset_results_state(self) -> None:
        self._results_loaded = False

    def _sync_periods(self) -> None:
        self._controller.update_exam_periods(
            [editor.get_exam_period() for editor in self._date_editors.values()]
        )

        if self._results_loaded:
            self._results_panel.mark_stale()

    def _tick_spinner(self) -> None:
        self._spinner_lbl.setText(_SPINNER[self._spin_tick % len(_SPINNER)])
        self._spin_tick += 1


class InputScreen(QWidget):
    """Root widget: QStackedWidget(ConfigScreen [0], ResultsScreen [1])."""

    def __init__(self, controller: DesktopController, parent=None) -> None:
        super().__init__(parent)

        self._config = ConfigScreen(controller)
        self._results = ResultsScreen(controller)

        self._stacked = QStackedWidget()
        self._stacked.addWidget(self._config)
        self._stacked.addWidget(self._results)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._stacked)

        self._config.generation_started.connect(self._on_generation_started)
        self._config.schedule_generated.connect(self._on_generated)
        self._config.generation_failed.connect(self._on_generation_failed)
        self._config.courses_changed.connect(self._results.refresh_courses)
        self._config.periods_changed.connect(self._results.refresh_periods)
        self._results.back_requested.connect(lambda: self._stacked.setCurrentIndex(0))

    def _on_generation_started(self, data: tuple) -> None:
        selected, _ = data

        self._results.reset_results_state()
        self._results.show_loading()
        self._stacked.setCurrentIndex(1)

    def _on_generated(self, data: tuple) -> None:
        _, schedules_by_period, courses_by_id, prog_color_map, truncated = data

        self._results.load(
            schedules_by_period,
            courses_by_id,
            prog_color_map,
            truncated,
        )
        self._results.hide_loading()

    def _on_generation_failed(self, error_msg: str) -> None:
        self._results.hide_loading()
        self._stacked.setCurrentIndex(0)
        QMessageBox.critical(self, "Generation Error", error_msg)
