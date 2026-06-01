"""
Widget: InputScreen — Sidebar + Tabbed Workspace (SRS §2.1 – §3.5).

Sidebar: Load Mode radios, Files group, Programmes list, Generate button.
Workspace tabs: Course Details | Exam Periods | Schedule Results (_ResultsPanel).
"""

import logging
import multiprocessing
import time
from pathlib import Path
from queue import Empty as _QueueEmpty

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.controller import RESULT_CAP, DesktopController, _run_generation_process
from src.domain.course import Course
from src.domain.schedule import Schedule
from src.ui.date_editor import DateEditorWidget
from src.ui.results_panel import _ResultsPanel, _make_data_table
from src.ui.tokens import PROGRAMME_COLOURS

logger = logging.getLogger(__name__)

_MAX_PROGS = 5


def _file_header(title: str, desc: str) -> tuple[QLabel, QLabel]:
    t = QLabel(title)
    t.setStyleSheet("font-weight: bold; font-size: 11px;")
    d = QLabel(desc)
    d.setStyleSheet("font-size: 10px; color: rgba(173,198,255,0.55);")
    return t, d


class InputScreen(QWidget):
    """Sidebar + tabbed workspace (SRS §2.1–§3.5)."""

    def __init__(self, controller: DesktopController, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._date_editors: dict[str, DateEditorWidget] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_workspace())
        splitter.setSizes([300, 900])

        root.addWidget(splitter)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(250)
        sidebar.setMaximumWidth(320)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        steps_lbl = QLabel("① Load files  ·  ② Select programme  ·  ③ Generate")
        steps_lbl.setWordWrap(True)
        steps_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        steps_lbl.setStyleSheet(
            "font-size: 10px; color: rgba(173,198,255,0.6);"
            "background: rgba(255,255,255,0.04); border-radius: 4px; padding: 4px 6px;"
        )
        layout.addWidget(steps_lbl)

        layout.addWidget(self._build_mode_box())
        layout.addWidget(self._build_files_box())
        layout.addWidget(self._build_prog_box())
        layout.addStretch()

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("font-size: 10px; color: #adc6ff;")
        layout.addWidget(self._status_label)

        self._gen_btn = QPushButton("▶  Generate Schedule")
        self._gen_btn.setObjectName("generateBtn")
        self._gen_btn.setEnabled(False)
        self._gen_btn.setFixedHeight(38)
        self._gen_btn.clicked.connect(self._on_generate)
        layout.addWidget(self._gen_btn)

        return sidebar

    def _build_mode_box(self) -> QGroupBox:
        mode_box = QGroupBox("Load Mode")
        mode_layout = QVBoxLayout(mode_box)
        radios_row = QHBoxLayout()
        radios_row.setSpacing(4)

        self._mode_group = QButtonGroup(self)
        for label in ("Replace", "Append", "Update"):
            rb = QRadioButton(label)
            self._mode_group.addButton(rb)
            radios_row.addWidget(rb)

        self._mode_group.buttons()[0].setChecked(True)
        mode_layout.addLayout(radios_row)

        hint = QLabel("Replace: clear all  ·  Append: add new  ·  Update: overwrite by ID")
        hint.setStyleSheet("font-size: 10px; color: rgba(173,198,255,0.55);")
        hint.setWordWrap(True)
        mode_layout.addWidget(hint)
        return mode_box

    def _build_files_box(self) -> QGroupBox:
        files_box = QGroupBox("Files")
        files_layout = QVBoxLayout(files_box)
        files_layout.setSpacing(4)

        courses_title, courses_desc = _file_header(
            "\U0001f4da Courses", "Course IDs, names & programme links"
        )
        files_layout.addWidget(courses_title)
        files_layout.addWidget(courses_desc)

        self._load_courses_btn = QPushButton("Load Courses")
        self._load_courses_btn.clicked.connect(self._load_courses)
        self._load_courses_btn.setToolTip("Course IDs, names, programme links, requirement types.")
        self._courses_label = QLabel("No file loaded")
        self._courses_label.setWordWrap(True)
        courses_row = QHBoxLayout()
        courses_row.addWidget(self._load_courses_btn)
        courses_row.addWidget(self._courses_label, 1)
        files_layout.addLayout(courses_row)
        files_layout.addSpacing(6)

        periods_title, periods_desc = _file_header(
            "\U0001f4c5 Exam Periods", "Scheduling date windows (start → end)"
        )
        files_layout.addWidget(periods_title)
        files_layout.addWidget(periods_desc)

        self._load_periods_btn = QPushButton("Load Periods")
        self._load_periods_btn.clicked.connect(self._load_dates)
        self._load_periods_btn.setToolTip("Exam period name, start date and end date.")
        self._dates_label = QLabel("No file loaded")
        self._dates_label.setWordWrap(True)
        periods_row = QHBoxLayout()
        periods_row.addWidget(self._load_periods_btn)
        periods_row.addWidget(self._dates_label, 1)
        files_layout.addLayout(periods_row)
        files_layout.addSpacing(6)

        programs_title, programs_desc = _file_header(
            "\U0001f393 Programmes", "Which programmes to schedule (max 5)"
        )
        files_layout.addWidget(programs_title)
        files_layout.addWidget(programs_desc)

        self._load_programs_btn = QPushButton("Load Programs")
        self._load_programs_btn.clicked.connect(self._load_programs)
        self._load_programs_btn.setToolTip("Comma-separated programme IDs to schedule (max 5).")
        self._programs_label = QLabel("No file loaded")
        self._programs_label.setWordWrap(True)
        programs_row = QHBoxLayout()
        programs_row.addWidget(self._load_programs_btn)
        programs_row.addWidget(self._programs_label, 1)
        files_layout.addLayout(programs_row)

        return files_box

    def _build_prog_box(self) -> QGroupBox:
        prog_box = QGroupBox("Study Programmes  (max 5)")
        prog_layout = QVBoxLayout(prog_box)
        prog_layout.setSpacing(4)

        self._prog_placeholder = QLabel(
            "Programmes appear here\nafter loading a programs or courses file."
        )
        self._prog_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prog_placeholder.setStyleSheet(
            "font-size: 10px; color: rgba(173,198,255,0.45); padding: 8px 4px;"
        )
        prog_layout.addWidget(self._prog_placeholder)

        self._prog_list = QListWidget()
        self._prog_list.setMinimumHeight(100)
        self._prog_list.setVisible(False)
        self._prog_list.itemChanged.connect(self._on_programme_toggled)
        prog_layout.addWidget(self._prog_list)

        self._prog_count_lbl = QLabel("0 / 5 selected")
        self._prog_count_lbl.setStyleSheet("font-size: 11px;")
        prog_layout.addWidget(self._prog_count_lbl)
        return prog_box

    def _build_workspace(self) -> QTabWidget:
        self._workspace = QTabWidget()

        course_tab = QWidget()
        course_tab_layout = QVBoxLayout(course_tab)
        course_tab_layout.setContentsMargins(0, 0, 0, 0)

        self._courses_placeholder = QLabel(
            "No courses loaded yet.\n\nLoad a courses file from the sidebar."
        )
        self._courses_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._courses_placeholder.setStyleSheet("font-size: 13px; color: rgba(173,198,255,0.5);")
        course_tab_layout.addWidget(self._courses_placeholder)

        self._course_table = _make_data_table(
            ["Course Name", "ID", "Year", "Semester", "Requirement", "Evaluation"]
        )
        self._course_table.setVisible(False)
        course_tab_layout.addWidget(self._course_table)
        self._workspace.addTab(course_tab, "Course Details")

        self._periods_container = QWidget()
        periods_tab_layout = QVBoxLayout(self._periods_container)
        periods_tab_layout.setContentsMargins(4, 4, 4, 4)

        self._no_periods_hint = QLabel("Load an exam-periods file to edit dates here.")
        self._no_periods_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        periods_tab_layout.addWidget(self._no_periods_hint)

        self._period_tabs = QTabWidget()
        self._period_tabs.setVisible(False)
        periods_tab_layout.addWidget(self._period_tabs)
        self._workspace.addTab(self._periods_container, "Exam Periods")

        self._results_panel = _ResultsPanel(self._controller)
        self._workspace.addTab(self._results_panel, "Schedule Results")

        return self._workspace

    def _load_courses(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Courses File", "", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        mode = self._mode_group.checkedButton().text().lower()
        try:
            count = self._controller.load_courses(Path(path), mode=mode)
            self._courses_label.setText(f"{Path(path).name}  ({count})")
            self._courses_label.setStyleSheet("font-size:10px; color:#a9dfbf;")
            self._refresh_programme_list()
            self._status_label.setText(f"{count} courses loaded.")
            self._update_gen_btn()
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            logger.exception("Error loading courses")

    def _load_dates(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Exam Periods File", "", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        mode = self._mode_group.checkedButton().text().lower()
        try:
            count = self._controller.load_periods(Path(path), mode=mode)
            self._dates_label.setText(f"{Path(path).name}  ({count})")
            self._dates_label.setStyleSheet("font-size:10px; color:#a9dfbf;")
            self._refresh_period_editors()
            self._status_label.setText(f"{count} period(s) loaded.")
            self._update_gen_btn()
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            logger.exception("Error loading exam periods")

    def _load_programs(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Programs File", "", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            count = self._controller.load_programs(Path(path))
            self._programs_label.setText(f"{Path(path).name}  ({count})")
            self._programs_label.setStyleSheet("font-size:10px; color:#a9dfbf;")
            self._refresh_programme_list()
            self._status_label.setText(f"{count} programme(s) loaded.")
            self._update_gen_btn()
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            logger.exception("Error loading programs")

    def _refresh_programme_list(self) -> None:
        self._prog_list.blockSignals(True)
        self._prog_list.clear()
        for program_id in self._controller.get_programme_ids():
            item = QListWidgetItem(program_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._prog_list.addItem(item)
        self._prog_list.blockSignals(False)

        has_items = self._prog_list.count() > 0
        self._prog_placeholder.setVisible(not has_items)
        self._prog_list.setVisible(has_items)
        self._update_prog_label()
        self._refresh_course_table()

    def _on_programme_toggled(self, item: QListWidgetItem) -> None:
        if self._count_checked() > _MAX_PROGS:
            self._prog_list.blockSignals(True)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._prog_list.blockSignals(False)
            QMessageBox.information(
                self, "Limit Reached", f"You can select at most {_MAX_PROGS} programmes."
            )
            return
        self._update_programme_colours()
        self._update_prog_label()
        self._refresh_course_table()
        self._update_gen_btn()

    def _update_programme_colours(self) -> None:
        slot = 0
        self._prog_list.blockSignals(True)
        for i in range(self._prog_list.count()):
            it = self._prog_list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                it.setForeground(QColor(PROGRAMME_COLOURS[slot % len(PROGRAMME_COLOURS)]))
                slot += 1
            else:
                it.setForeground(QColor(173, 198, 255, 140))
        self._prog_list.blockSignals(False)

    def _count_checked(self) -> int:
        return sum(1 for i in range(self._prog_list.count())
                   if self._prog_list.item(i).checkState() == Qt.CheckState.Checked)

    def _get_selected_ids(self) -> list[str]:
        return [self._prog_list.item(i).text() for i in range(self._prog_list.count())
                if self._prog_list.item(i).checkState() == Qt.CheckState.Checked]

    def _update_prog_label(self) -> None:
        self._prog_count_lbl.setText(f"{self._count_checked()} / {_MAX_PROGS} selected")

    def _refresh_course_table(self) -> None:
        self._course_table.setRowCount(0)
        for prog_id in self._get_selected_ids():
            for course in self._controller.get_courses_by_programme(prog_id):
                for offering in course.offerings:
                    if offering.program_id != prog_id:
                        continue
                    row = self._course_table.rowCount()
                    self._course_table.insertRow(row)
                    for col, value in enumerate([
                        course.name, course.id, str(offering.year),
                        offering.semester, offering.requirement, course.evaluation_type,
                    ]):
                        self._course_table.setItem(row, col, QTableWidgetItem(value))
        has_rows = self._course_table.rowCount() > 0
        self._courses_placeholder.setVisible(not has_rows)
        self._course_table.setVisible(has_rows)

    def _refresh_period_editors(self) -> None:
        self._period_tabs.clear()
        self._date_editors.clear()
        periods = self._controller.get_exam_periods()
        if not periods:
            self._no_periods_hint.setVisible(True)
            self._period_tabs.setVisible(False)
            return
        self._no_periods_hint.setVisible(False)
        self._period_tabs.setVisible(True)
        for period in periods:
            key = period.get_key()
            editor = DateEditorWidget(period)
            editor.period_changed.connect(self._sync_periods)
            self._date_editors[key] = editor
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(editor)
            self._period_tabs.addTab(scroll, key)

    def _sync_periods(self) -> None:
        self._controller.update_exam_periods(
            [editor.get_exam_period() for editor in self._date_editors.values()]
        )

    def _on_generate(self) -> None:
        selected = self._get_selected_ids()
        self._controller.set_selected_programs(selected)
        self._sync_periods()
        self._pending_selected = selected

        self._gen_btn.setEnabled(False)
        self._gen_btn.setText("⏳  Generating…  0s")
        self._gen_start_time = time.monotonic()

        if getattr(self, "_gen_process", None) is not None and self._gen_process.is_alive():
            self._gen_process.terminate()
            self._gen_process.join(timeout=2)
        if getattr(self, "_poll_timer", None) is not None:
            self._poll_timer.stop()

        self._result_queue = multiprocessing.Queue()
        self._gen_process = multiprocessing.Process(
            target=_run_generation_process,
            args=(self._result_queue, self._controller.courses,
                  self._controller.get_exam_periods(), selected),
            daemon=True,
        )
        self._gen_process.start()
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_generation_result)
        self._poll_timer.start(150)

    def _poll_generation_result(self) -> None:
        elapsed = int(time.monotonic() - self._gen_start_time)
        try:
            result = self._result_queue.get_nowait()
        except _QueueEmpty:
            self._gen_btn.setText(f"⏳  Generating…  {elapsed}s")
            if not self._gen_process.is_alive():
                self._poll_timer.stop()
                self._on_generate_failed("Generation process exited unexpectedly.")
            return

        self._poll_timer.stop()
        if result[0]:
            _, schedules_by_period, courses_by_id, truncated_periods = result
            self._controller.reset_generation_state()
            self._on_generate_done(
                self._pending_selected, schedules_by_period, courses_by_id, truncated_periods
            )
        else:
            self._on_generate_failed(result[1])

    def _on_generate_done(
        self,
        selected: list[str],
        schedules_by_period: dict[str, list[Schedule]],
        courses_by_id: dict[str, Course],
        truncated_periods: set[str],
    ) -> None:
        prog_color_map = {
            program_id: PROGRAMME_COLOURS[i % len(PROGRAMME_COLOURS)]
            for i, program_id in enumerate(selected)
        }
        self._results_panel.load(schedules_by_period, courses_by_id, prog_color_map)
        self._workspace.setCurrentIndex(2)

        combined_total = self._controller.get_combined_schedule_count(schedules_by_period)
        if truncated_periods:
            self._status_label.setText(
                f"✓ Showing {combined_total} loaded combined schedule option(s). "
                f"Forward {RESULT_CAP} will load more automatically if needed."
            )
        else:
            self._status_label.setText(
                f"✓ {combined_total} combined schedule option(s) ready."
            )
        self._gen_btn.setEnabled(True)
        self._gen_btn.setText("▶  Generate Schedule")

    def _on_generate_failed(self, error_msg: str) -> None:
        QMessageBox.critical(self, "Generation Error", error_msg)
        logger.error("Generation failed: %s", error_msg)
        self._gen_btn.setEnabled(True)
        self._gen_btn.setText("▶  Generate Schedule")

    def _update_gen_btn(self) -> None:
        process_running = (
            getattr(self, "_gen_process", None) is not None
            and self._gen_process.is_alive()
        )
        self._gen_btn.setEnabled(
            not process_running
            and self._controller.has_courses
            and self._controller.has_periods
            and self._count_checked() >= 1
        )
