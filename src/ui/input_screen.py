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

from PyQt6.QtCore import Qt, QEasingCurve, QPropertyAnimation, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.controller import DesktopController
from src.domain.course import Course
from src.domain.schedule import Schedule
from src.ui.assets.logo_widget import LogoWidget
from src.ui.config_screen import ConfigScreen
from src.ui.date_editor import DateEditorWidget
from src.ui.results_panel import _ResultsPanel, _make_data_table
from src.ui.tokens import PROGRAM_NAMES_MAPPING

logger = logging.getLogger(__name__)

_COURSE_TABLE_HEADERS = [
    "Course Name", "Course ID", "Year", "Semester",
    "Requirement", "Evaluation", "Program ID", "Program Name",
]
_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


# ── Results Screen (Screen 1) ─────────────────────────────────────────────────

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
        self._setup_ui()

    # ── Public API ────────────────────────────────────────────────────────────

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
            schedules_by_period, courses_by_id, prog_color_map, truncated_periods
        )
        self._workspace.setCurrentIndex(2)

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
                        course.name, course.id, str(offering.year),
                        offering.semester, offering.requirement,
                        course.evaluation_type, prog_id, prog_name,
                    ]):
                        self._course_table.setItem(row, col, QTableWidgetItem(value))
        has_rows = self._course_table.rowCount() > 0
        self._courses_placeholder.setVisible(not has_rows)
        self._course_table.setVisible(has_rows)

    def refresh_periods(self) -> None:
        # Clear existing grid items
        while self._periods_grid_layout.count():
            item = self._periods_grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._date_editors.clear()

        periods = self._controller.get_exam_periods()
        if not periods:
            self._no_periods_hint.setVisible(True)
            self._periods_scroll.setVisible(False)
            return

        self._no_periods_hint.setVisible(False)
        self._periods_scroll.setVisible(True)

        n = len(periods)
        cols = n if n <= 3 else 2  # 1–3 → single row; 4+ → 2-column grid

        for i, period in enumerate(periods):
            key = period.get_key()
            editor = DateEditorWidget(period)
            editor.period_changed.connect(self._sync_periods)
            self._date_editors[key] = editor

            card = QFrame()
            card.setStyleSheet(
                "QFrame { border:1px solid #E2E8F0; border-radius:10px;"
                " background:#FAFAFA; }"
            )
            vl = QVBoxLayout(card)
            vl.setContentsMargins(8, 8, 8, 8)
            vl.setSpacing(4)
            title = QLabel(key)
            title.setStyleSheet(
                "font-weight:700; font-size:12px; color:#1D4ED8;"
                " background:transparent; border:none;"
            )
            vl.addWidget(title)
            vl.addWidget(editor)

            row, col = divmod(i, cols)
            self._periods_grid_layout.addWidget(card, row, col)

        for c in range(cols):
            self._periods_grid_layout.setColumnStretch(c, 1)

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        self._content_stack = QStackedWidget()
        self._content_stack.addWidget(self._build_loading_pane())  # index 0
        self._content_stack.addWidget(self._build_workspace())     # index 1
        self._content_stack.setCurrentIndex(1)
        root.addWidget(self._content_stack)

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setObjectName("appHeader")
        hdr.setFixedHeight(56)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 0, 20, 0)
        hl.setSpacing(10)
        back_btn = QPushButton("← Back")
        back_btn.setFixedWidth(80)
        back_btn.setFixedHeight(32)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(
            "background:#F1F5F9; color:#374151; border:1px solid #D1D5DB;"
            "border-radius:8px; font-size:11px; font-weight:600;"
        )
        back_btn.clicked.connect(self.back_requested.emit)
        hl.addWidget(back_btn)
        hl.addWidget(LogoWidget(size=28))
        brand = QLabel("Syncacademic")
        brand.setStyleSheet(
            "font-size:15px; font-weight:800; color:#2563EB; background:transparent;"
        )
        hl.addWidget(brand)
        hl.addStretch()
        return hdr

    def _build_loading_pane(self) -> QWidget:
        pane = QWidget()
        pane.setStyleSheet("background:#F8FAFC;")
        vl = QVBoxLayout(pane)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.setSpacing(14)
        self._spinner_lbl = QLabel("⠋")
        self._spinner_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spinner_lbl.setStyleSheet(
            "font-size:52px; color:#2563EB; background:transparent;"
        )
        vl.addWidget(self._spinner_lbl)
        msg = QLabel("Generating schedules…\nThis may take a few seconds.")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("font-size:14px; color:#64748B; background:transparent;")
        vl.addWidget(msg)
        return pane

    def _build_workspace(self) -> QTabWidget:
        self._workspace = QTabWidget()

        # Course Details tab
        course_tab = QWidget()
        course_tab.setStyleSheet("background:transparent;")
        ctl = QVBoxLayout(course_tab)
        ctl.setContentsMargins(0, 8, 0, 0)
        self._courses_placeholder = QLabel(
            "No courses loaded yet.\n\nLoad a courses file and select a programme."
        )
        self._courses_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._courses_placeholder.setStyleSheet("font-size:13px; color:#94A3B8;")
        ctl.addWidget(self._courses_placeholder)
        self._course_table = _make_data_table(_COURSE_TABLE_HEADERS)
        hh = self._course_table.horizontalHeader()
        # Col 0 (Course Name) and 7 (Program Name) stretch to fill available space
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        # Compact columns fit their content
        for col in (1, 2, 3, 4, 5, 6):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._course_table.setVisible(False)
        ctl.addWidget(self._course_table)
        self._workspace.addTab(course_tab, "Course Details")

        # Exam Periods tab — responsive grid, one editor per period
        periods_ctr = QWidget()
        periods_ctr.setStyleSheet("background:transparent;")
        ptl = QVBoxLayout(periods_ctr)
        ptl.setContentsMargins(4, 4, 4, 4)
        self._no_periods_hint = QLabel("Load an exam-periods file to edit dates here.")
        self._no_periods_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ptl.addWidget(self._no_periods_hint)

        self._periods_scroll = QScrollArea()
        self._periods_scroll.setWidgetResizable(True)
        self._periods_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._periods_grid_ctr = QWidget()
        self._periods_grid_layout = QGridLayout(self._periods_grid_ctr)
        self._periods_grid_layout.setSpacing(12)
        self._periods_grid_layout.setContentsMargins(4, 4, 4, 4)
        self._periods_scroll.setWidget(self._periods_grid_ctr)
        self._periods_scroll.setVisible(False)
        ptl.addWidget(self._periods_scroll)
        self._workspace.addTab(periods_ctr, "Exam Periods")

        # Schedule Results tab
        self._results_panel = _ResultsPanel(self._controller)
        self._workspace.addTab(self._results_panel, "Schedule Results")
        return self._workspace

    def _sync_periods(self) -> None:
        self._controller.update_exam_periods(
            [e.get_exam_period() for e in self._date_editors.values()]
        )

    def _tick_spinner(self) -> None:
        self._spinner_lbl.setText(_SPINNER[self._spin_tick % len(_SPINNER)])
        self._spin_tick += 1


# ── Main container ────────────────────────────────────────────────────────────

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
        self._results.refresh_courses(selected)
        self._results.refresh_periods()
        self._results.show_loading()
        self._stacked.setCurrentIndex(1)

    def _on_generated(self, data: tuple) -> None:
        _, schedules_by_period, courses_by_id, prog_color_map, truncated = data
        self._results.load(schedules_by_period, courses_by_id, prog_color_map, truncated)
        self._results.hide_loading()
        effect = QGraphicsOpacityEffect(self._results)
        self._results.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self._results)
        anim.setDuration(300)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()

    def _on_generation_failed(self, error_msg: str) -> None:
        self._results.hide_loading()
        self._stacked.setCurrentIndex(0)
        QMessageBox.critical(self, "Generation Error", error_msg)
