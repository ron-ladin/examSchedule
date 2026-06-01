"""
Widget: InputScreen — Sidebar + Tabbed Workspace
--------------------------------------------------
Master-Detail / Sidebar layout (SRS §2.1 – §3.5).

Left sidebar  (250–320 px, fixed bounds):
    § Load Mode  — Replace / Append / Update radio buttons
    § Files      — Load Courses / Load Periods with status labels
    § Programmes — QListWidget checkboxes, max 5, with counter
    § Generate   — prominent button pinned at the bottom

Right workspace  (QTabWidget, expands to fill window):
    Tab 1 "Course Details"    — QTableWidget, populated per selected programme
    Tab 2 "Exam Periods"      — DateEditorWidget per loaded period  (§2.4)
    Tab 3 "Schedule Results"  — combined Cartesian-product schedules
"""

import logging
from datetime import date, timedelta
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.controller import RESULT_CAP, DesktopController
from src.domain.course import Course
from src.domain.schedule import Schedule
from src.ui.date_editor import DateEditorWidget
from src.ui.tokens import PROGRAMME_COLOURS

logger = logging.getLogger(__name__)

_MAX_PROGS = 5


def _make_data_table(headers: list[str]) -> QTableWidget:
    """
    Create a read-only, row-selecting, last-column-stretching QTableWidget.
    Satisfies the three UX-polish requirements from the design brief.
    """
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    return table


def _file_header(title: str, desc: str) -> tuple[QLabel, QLabel]:
    """Return a (bold title QLabel, muted description QLabel) pair for the Files group box."""
    title_label = QLabel(title)
    title_label.setStyleSheet("font-weight: bold; font-size: 11px;")

    desc_label = QLabel(desc)
    desc_label.setStyleSheet("font-size: 10px; color: rgba(173,198,255,0.55);")

    return title_label, desc_label


class _GenerateWorker(QThread):
    """Runs DesktopController.generate() off the Qt main thread."""

    finished = pyqtSignal(dict, dict, object)
    failed = pyqtSignal(str)

    def __init__(self, controller: DesktopController, parent=None):
        super().__init__(parent)
        self._controller = controller

    def run(self) -> None:
        try:
            schedules_by_period, courses_by_id, truncated_periods = (
                self._controller.generate()
            )
            self.finished.emit(
                schedules_by_period,
                courses_by_id,
                truncated_periods,
            )
        except Exception as exc:
            logger.exception("Worker: generation failed")
            self.failed.emit(str(exc))


class _ResultsPanel(QWidget):
    """
    Tab 3 — Schedule Results.

    Shows full combined schedules using a Cartesian product of schedules
    across all exam periods. It does not materialise product(...) in memory.
    """

    def __init__(self, controller: DesktopController, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._schedules_by_period: dict[str, list[Schedule]] = {}
        self._courses_by_id: dict[str, Course] = {}
        self._prog_color_map: dict[str, str] = {}
        self._combined_index = 0
        self._setup_ui()

    def load(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
    ) -> None:
        """Populate the panel after a successful generation."""
        self._schedules_by_period = schedules_by_period
        self._courses_by_id = courses_by_id
        self._prog_color_map = prog_color_map
        self._combined_index = 0

        self._placeholder.setVisible(False)
        self._content.setVisible(True)
        self._refresh_combined_view()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        self._placeholder = QLabel(
            "No schedules generated yet.\n\n"
            "Load files, select a programme, then click  ▶  Generate Schedule."
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("font-size: 13px; color: #adc6ff;")
        root.addWidget(self._placeholder)

        self._content = QWidget()
        self._content.setVisible(False)
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        action_row = QHBoxLayout()
        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet("color: #a9dfbf; font-weight: bold;")
        action_row.addWidget(self._summary_lbl)
        action_row.addStretch()

        save_btn = QPushButton("💾  Save Current Combined Schedule")
        save_btn.clicked.connect(self._on_save)
        action_row.addWidget(save_btn)
        content_layout.addLayout(action_row)

        nav = QHBoxLayout()
        self._back_200_btn = QPushButton(f"◀  Back {RESULT_CAP}")
        self._prev_btn = QPushButton("◀  Prev")
        self._counter_lbl = QLabel("Combined Schedule 0 of 0")
        self._counter_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._counter_lbl.setStyleSheet("font-weight: bold; min-width: 260px;")
        self._next_btn = QPushButton("Next  ▶")
        self._forward_200_btn = QPushButton(f"Forward {RESULT_CAP}  ▶")

        self._back_200_btn.clicked.connect(self._go_back_page)
        self._prev_btn.clicked.connect(self._go_prev)
        self._next_btn.clicked.connect(self._go_next)
        self._forward_200_btn.clicked.connect(self._go_forward_page)

        nav.addWidget(self._back_200_btn)
        nav.addWidget(self._prev_btn)
        nav.addStretch()
        nav.addWidget(self._counter_lbl)
        nav.addStretch()
        nav.addWidget(self._next_btn)
        nav.addWidget(self._forward_200_btn)
        content_layout.addLayout(nav)

        self._period_tabs = QTabWidget()
        content_layout.addWidget(self._period_tabs)

        root.addWidget(self._content)

    def _refresh_combined_view(self) -> None:
        total = self._controller.get_combined_schedule_count(
            self._schedules_by_period
        )

        self._period_tabs.clear()

        if total == 0:
            self._summary_lbl.setStyleSheet("color: #e05c5c; font-weight: bold;")
            self._summary_lbl.setText("⚠   No valid combined schedules found.")
            self._counter_lbl.setText("Combined Schedule 0 of 0")
            self._back_200_btn.setEnabled(False)
            self._prev_btn.setEnabled(False)
            self._next_btn.setEnabled(False)
            self._forward_200_btn.setEnabled(
                self._controller.has_any_more_schedules()
            )
            return

        if self._combined_index >= total:
            self._combined_index = total - 1

        combined = self._controller.get_combined_schedule_at(
            self._schedules_by_period,
            self._combined_index,
        )

        for period_key, schedule in combined.items():
            table = _make_data_table(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
            table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch
            )
            table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            self._populate_calendar(table, schedule)
            self._period_tabs.addTab(table, period_key)

        self._counter_lbl.setText(
            f"Combined Schedule {self._combined_index + 1} of {total}"
        )

        has_more_loaded_results = self._combined_index < total - 1
        has_more_unloaded_results = self._controller.has_any_more_schedules()

        self._back_200_btn.setEnabled(self._combined_index > 0)
        self._prev_btn.setEnabled(self._combined_index > 0)
        self._next_btn.setEnabled(
            has_more_loaded_results or has_more_unloaded_results
        )
        self._forward_200_btn.setEnabled(
            has_more_loaded_results or has_more_unloaded_results
        )

        self._summary_lbl.setStyleSheet("color: #a9dfbf; font-weight: bold;")

        if has_more_unloaded_results:
            self._summary_lbl.setText(
                f"✓   {total} loaded combined schedule option(s). "
                f"Forward {RESULT_CAP} will load more automatically if needed."
            )
        else:
            self._summary_lbl.setText(
                f"✓   {total} combined schedule option(s)."
            )

    def _go_prev(self) -> None:
        """Move back by one combined schedule."""
        if self._combined_index > 0:
            self._combined_index -= 1
            self._refresh_combined_view()

    def _go_next(self) -> None:
        """Move forward by one combined schedule, loading more if needed."""
        target_index = self._combined_index + 1
        self._ensure_loaded_until(target_index)

        total = self._controller.get_combined_schedule_count(
            self._schedules_by_period
        )

        if target_index < total:
            self._combined_index = target_index
            self._refresh_combined_view()

    def _go_back_page(self) -> None:
        """Move back by RESULT_CAP combined schedules, without going below 0."""
        self._combined_index = max(0, self._combined_index - RESULT_CAP)
        self._refresh_combined_view()

    def _go_forward_page(self) -> None:
        """
        Move forward by RESULT_CAP combined schedules.

        If the target index is outside the currently loaded Cartesian product,
        load more schedules automatically and then continue.
        """
        target_index = self._combined_index + RESULT_CAP
        self._ensure_loaded_until(target_index)

        total = self._controller.get_combined_schedule_count(
            self._schedules_by_period
        )

        if total == 0:
            return

        self._combined_index = min(target_index, total - 1)
        self._refresh_combined_view()

    def _ensure_loaded_until(self, target_index: int) -> None:
        """
        Load more per-period schedules until target_index exists,
        or until the controller has no more schedules to load.
        """
        while (
            self._controller.get_combined_schedule_count(self._schedules_by_period)
            <= target_index
            and self._controller.has_any_more_schedules()
        ):
            loaded_any = False

            for period_key in list(self._schedules_by_period):
                if self._controller.has_more_schedules(period_key):
                    more_schedules = self._controller.load_more_schedules(period_key)

                    if more_schedules:
                        self._schedules_by_period[period_key].extend(more_schedules)
                        loaded_any = True

            if not loaded_any:
                break

    def _populate_calendar(self, table: QTableWidget, schedule: Schedule) -> None:
        """Fill calendar cells, colour-coded by programme."""
        table.clearContents()
        table.setRowCount(0)

        if not schedule.assignments:
            return

        date_to_ids: dict[date, list[str]] = {}
        for course_id, exam_date in schedule.assignments.items():
            date_to_ids.setdefault(exam_date, []).append(course_id)

        all_dates = sorted(date_to_ids)
        start, end = all_dates[0], all_dates[-1]
        week_start = start - timedelta(days=start.weekday())
        last_sunday = end + timedelta(days=6 - end.weekday())
        num_weeks = (last_sunday - week_start).days // 7 + 1

        table.setRowCount(num_weeks)

        for week in range(num_weeks):
            for dow in range(7):
                current_date = week_start + timedelta(days=week * 7 + dow)
                course_ids = date_to_ids.get(current_date, [])
                lines = [current_date.strftime("%d/%m")]
                first_prog = None

                for course_id in course_ids:
                    course = self._courses_by_id.get(course_id)
                    if not course:
                        lines.append(course_id)
                        continue

                    relevant = next(
                        (
                            offering
                            for offering in course.offerings
                            if offering.program_id in self._prog_color_map
                        ),
                        None,
                    )

                    req = (
                        "Elective"
                        if relevant and relevant.is_elective()
                        else "Obligatory"
                    )
                    prog_id = relevant.program_id if relevant else ""

                    if first_prog is None:
                        first_prog = prog_id

                    lines.append(f"{course_id} | {course.name[:20]}")
                    lines.append(f"{prog_id} | {req}")

                item = QTableWidgetItem("\n".join(lines))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
                )

                if first_prog and first_prog in self._prog_color_map:
                    item.setBackground(QColor(self._prog_color_map[first_prog]))

                table.setItem(week, dow, item)

        table.resizeRowsToContents()

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Schedule",
            "schedules.txt",
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return

        total = self._controller.get_combined_schedule_count(
            self._schedules_by_period
        )
        if total == 0:
            QMessageBox.warning(self, "Save Error", "No combined schedule to save.")
            return

        combined = self._controller.get_combined_schedule_at(
            self._schedules_by_period,
            self._combined_index,
        )

        selected = {
            period_key: [schedule]
            for period_key, schedule in combined.items()
        }

        try:
            self._controller.export(selected, Path(path))
            QMessageBox.information(self, "Saved", f"Schedule saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            logger.exception("Save failed")


class InputScreen(QWidget):
    """
    Full application layout:
        QSplitter(Horizontal)
            ├── Sidebar  (controls, min 250 / max 320 px)
            └── Workspace  (QTabWidget with 3 tabs)
    """

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

        mode_hint = QLabel("Replace: clear all  ·  Append: add new  ·  Update: overwrite by ID")
        mode_hint.setStyleSheet("font-size: 10px; color: rgba(173,198,255,0.55);")
        mode_hint.setWordWrap(True)
        mode_layout.addWidget(mode_hint)
        layout.addWidget(mode_box)

        files_box = QGroupBox("Files")
        files_layout = QVBoxLayout(files_box)
        files_layout.setSpacing(4)

        courses_title, courses_desc = _file_header(
            "\U0001f4da Courses",
            "Course IDs, names & programme links",
        )
        files_layout.addWidget(courses_title)
        files_layout.addWidget(courses_desc)

        courses_row = QHBoxLayout()
        self._load_courses_btn = QPushButton("Load Courses")
        self._load_courses_btn.clicked.connect(self._load_courses)
        self._load_courses_btn.setToolTip(
            "Load a .txt file containing courses:\n"
            "  • course ID, name, year, semester\n"
            "  • programme assignment (CS, Math…)\n"
            "  • requirement type (obligatory / elective)"
        )
        self._courses_label = QLabel("No file loaded")
        self._courses_label.setWordWrap(True)
        courses_row.addWidget(self._load_courses_btn)
        courses_row.addWidget(self._courses_label, 1)
        files_layout.addLayout(courses_row)

        files_layout.addSpacing(6)

        periods_title, periods_desc = _file_header(
            "\U0001f4c5 Exam Periods",
            "Scheduling date windows (start → end)",
        )
        files_layout.addWidget(periods_title)
        files_layout.addWidget(periods_desc)

        periods_row = QHBoxLayout()
        self._load_periods_btn = QPushButton("Load Periods")
        self._load_periods_btn.clicked.connect(self._load_dates)
        self._load_periods_btn.setToolTip(
            "Load a .txt file containing exam periods:\n"
            "  • period name (e.g. Moed A, Moed B)\n"
            "  • start date and end date"
        )
        self._dates_label = QLabel("No file loaded")
        self._dates_label.setWordWrap(True)
        periods_row.addWidget(self._load_periods_btn)
        periods_row.addWidget(self._dates_label, 1)
        files_layout.addLayout(periods_row)

        files_layout.addSpacing(6)

        programs_title, programs_desc = _file_header(
            "\U0001f393 Programmes",
            "Which programmes to schedule (max 5)",
        )
        files_layout.addWidget(programs_title)
        files_layout.addWidget(programs_desc)

        programs_row = QHBoxLayout()
        self._load_programs_btn = QPushButton("Load Programs")
        self._load_programs_btn.clicked.connect(self._load_programs)
        self._load_programs_btn.setToolTip(
            "Load a .txt file listing programme IDs to schedule:\n"
            "  • comma-separated 5-digit IDs  (e.g. 83101, 83102)\n"
            "  • maximum 5 programmes"
        )
        self._programs_label = QLabel("No file loaded")
        self._programs_label.setWordWrap(True)
        programs_row.addWidget(self._load_programs_btn)
        programs_row.addWidget(self._programs_label, 1)
        files_layout.addLayout(programs_row)

        layout.addWidget(files_box)

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
        layout.addWidget(prog_box)

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

    def _build_workspace(self) -> QTabWidget:
        self._workspace = QTabWidget()

        course_tab = QWidget()
        course_tab_layout = QVBoxLayout(course_tab)
        course_tab_layout.setContentsMargins(0, 0, 0, 0)

        self._courses_placeholder = QLabel(
            "No courses loaded yet.\n\nLoad a courses file from the sidebar."
        )
        self._courses_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._courses_placeholder.setStyleSheet(
            "font-size: 13px; color: rgba(173,198,255,0.5);"
        )
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
            self,
            "Select Courses File",
            "",
            "Text files (*.txt);;All files (*)",
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
            self,
            "Select Exam Periods File",
            "",
            "Text files (*.txt);;All files (*)",
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
            self,
            "Select Programs File",
            "",
            "Text files (*.txt);;All files (*)",
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
                self,
                "Limit Reached",
                f"You can select at most {_MAX_PROGS} programmes.",
            )
            return

        self._update_prog_label()
        self._refresh_course_table()
        self._update_gen_btn()

    def _count_checked(self) -> int:
        return sum(
            1
            for i in range(self._prog_list.count())
            if self._prog_list.item(i).checkState() == Qt.CheckState.Checked
        )

    def _get_selected_ids(self) -> list[str]:
        return [
            self._prog_list.item(i).text()
            for i in range(self._prog_list.count())
            if self._prog_list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def _update_prog_label(self) -> None:
        selected_count = self._count_checked()
        self._prog_count_lbl.setText(f"{selected_count} / {_MAX_PROGS} selected")

    def _refresh_course_table(self) -> None:
        """Rebuild the flat course table for all currently selected programmes."""
        self._course_table.setRowCount(0)

        for prog_id in self._get_selected_ids():
            for course in self._controller.get_courses_by_programme(prog_id):
                for offering in course.offerings:
                    if offering.program_id != prog_id:
                        continue

                    row = self._course_table.rowCount()
                    self._course_table.insertRow(row)

                    values = [
                        course.name,
                        course.id,
                        str(offering.year),
                        offering.semester,
                        offering.requirement,
                        course.evaluation_type,
                    ]

                    for col, value in enumerate(values):
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

        self._gen_btn.setEnabled(False)
        self._gen_btn.setText("⏳  Generating…")

        if getattr(self, "_worker", None) is not None:
            try:
                self._worker.finished.disconnect()
                self._worker.failed.disconnect()
            except RuntimeError:
                pass

        self._worker = _GenerateWorker(self._controller, parent=self)
        self._worker.finished.connect(
            lambda schedules_by_period, courses_by_id, truncated_periods:
            self._on_generate_done(
                selected,
                schedules_by_period,
                courses_by_id,
                truncated_periods,
            )
        )
        self._worker.failed.connect(self._on_generate_failed)
        self._worker.start()

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

        self._results_panel.load(
            schedules_by_period,
            courses_by_id,
            prog_color_map,
        )

        self._workspace.setCurrentIndex(2)

        combined_total = self._controller.get_combined_schedule_count(
            schedules_by_period
        )

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
        worker_running = (
            getattr(self, "_worker", None) is not None
            and self._worker.isRunning()
        )
        self._gen_btn.setEnabled(
            not worker_running
            and self._controller.has_courses
            and self._controller.has_periods
            and self._count_checked() >= 1
        )
