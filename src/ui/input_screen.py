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
    Tab 3 "Schedule Results"  — calendar + Prev/Next + Save  (§3.1 – §3.5)
"""

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

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

from src.controller import DesktopController
from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.ui.date_editor import DateEditorWidget
from src.ui.tokens import PROGRAMME_COLOURS

logger = logging.getLogger(__name__)

_MAX_PROGS = 5


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_data_table(headers: List[str]) -> QTableWidget:
    """
    Create a read-only, row-selecting, last-column-stretching QTableWidget.
    Satisfies the three UX-polish requirements from the design brief.
    """
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    # Read-only
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    # Whole-row selection
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    # Stretch last column to prevent dead space
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    return table


def _file_header(title: str, desc: str) -> tuple:
    """Return a (bold title QLabel, muted description QLabel) pair for the Files group box."""
    t = QLabel(title)
    t.setStyleSheet("font-weight: bold; font-size: 11px;")
    d = QLabel(desc)
    d.setStyleSheet("font-size: 10px; color: rgba(173,198,255,0.55);")
    return t, d


# ─────────────────────────────────────────────────────────────────────────────
# Background worker
# ─────────────────────────────────────────────────────────────────────────────

class _GenerateWorker(QThread):
    """Runs DesktopController.generate() off the Qt main thread."""

    finished = pyqtSignal(dict, dict)  # (schedules_by_period, courses_by_id)
    failed   = pyqtSignal(str)         # error message

    def __init__(self, controller: "DesktopController", parent=None):
        super().__init__(parent)
        self._controller = controller

    def run(self) -> None:
        try:
            sbp, cbi = self._controller.generate()
            self.finished.emit(sbp, cbi)
        except Exception as exc:
            logger.exception("Worker: generation failed")
            self.failed.emit(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Tab 3: Schedule Results panel
# ─────────────────────────────────────────────────────────────────────────────

class _ResultsPanel(QWidget):
    """
    Tab 3 — Schedule Results.

    Starts as a placeholder until load() is called after generation.
    Owns per-period navigation (§3.2 – §3.3), calendar grid (§3.1),
    cell content (§3.4), and Save (§3.5).
    """

    def __init__(self, controller: DesktopController, parent=None):
        super().__init__(parent)
        self._controller        = controller
        self._schedules_by_period: Dict[str, List[Schedule]] = {}
        self._courses_by_id:       Dict[str, Course]         = {}
        self._prog_color_map:      Dict[str, str]            = {}
        self._current_index:       Dict[str, int]            = {}
        self._setup_ui()

    # ── Public API ─────────────────────────────────────────────────────────────

    def load(
        self,
        schedules_by_period: Dict[str, List[Schedule]],
        courses_by_id: Dict[str, Course],
        prog_color_map: Dict[str, str],
    ) -> None:
        """Populate the panel after a successful generation."""
        self._schedules_by_period = schedules_by_period
        self._courses_by_id       = courses_by_id
        self._prog_color_map      = prog_color_map
        self._current_index       = {k: 0 for k in schedules_by_period}

        self._placeholder.setVisible(False)
        self._content.setVisible(True)

        total = sum(len(v) for v in schedules_by_period.values())
        self._summary_lbl.setText(
            f"✓   {total} schedule(s) across {len(schedules_by_period)} period(s)"
        )

        self._period_tabs.clear()
        for period_key, schedules in schedules_by_period.items():
            tab = self._build_period_tab(period_key, schedules)
            self._period_tabs.addTab(tab, period_key)

    # ── UI setup ───────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        # Placeholder shown before first generation
        self._placeholder = QLabel(
            "No schedules generated yet.\n\n"
            "Load files, select a programme, then click  ▶  Generate Schedule."
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("font-size: 13px; color: #adc6ff;")
        root.addWidget(self._placeholder)

        # Main content (hidden until load() is called)
        self._content = QWidget()
        self._content.setVisible(False)
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)

        # Action row
        action_row = QHBoxLayout()
        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet("color: #a9dfbf; font-weight: bold;")
        action_row.addWidget(self._summary_lbl)
        action_row.addStretch()
        save_btn = QPushButton("💾  Save Schedule")
        save_btn.clicked.connect(self._on_save)
        action_row.addWidget(save_btn)
        cl.addLayout(action_row)

        # Per-period result tabs
        self._period_tabs = QTabWidget()
        cl.addWidget(self._period_tabs)

        root.addWidget(self._content)

    # ── Per-period tab (§3.2 – §3.3) ──────────────────────────────────────────

    def _build_period_tab(self, period_key: str, schedules: List[Schedule]) -> QWidget:
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(6)

        if not schedules:
            layout.addWidget(QLabel("⚠  No valid schedules for this period."))
            return outer

        # Navigation bar
        nav = QHBoxLayout()
        prev_btn = QPushButton("◀  Prev")
        counter  = QLabel(f"Schedule 1 of {len(schedules)}")   # §3.3
        counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        counter.setStyleSheet("font-weight: bold; min-width: 160px;")
        next_btn = QPushButton("Next  ▶")
        nav.addWidget(prev_btn)
        nav.addStretch()
        nav.addWidget(counter)
        nav.addStretch()
        nav.addWidget(next_btn)
        layout.addLayout(nav)

        # Calendar grid (§3.1)
        table = _make_data_table(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        # Override: calendar uses Stretch on ALL columns, not just the last
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(table)

        def refresh() -> None:
            idx = self._current_index[period_key]
            counter.setText(f"Schedule {idx + 1} of {len(schedules)}")
            prev_btn.setEnabled(idx > 0)
            next_btn.setEnabled(idx < len(schedules) - 1)
            self._populate_calendar(table, schedules[idx])

        def go_prev() -> None:
            if self._current_index[period_key] > 0:
                self._current_index[period_key] -= 1
                refresh()

        def go_next() -> None:
            if self._current_index[period_key] < len(schedules) - 1:
                self._current_index[period_key] += 1
                refresh()

        prev_btn.clicked.connect(go_prev)
        next_btn.clicked.connect(go_next)
        prev_btn.setEnabled(False)
        next_btn.setEnabled(len(schedules) > 1)
        refresh()
        return outer

    # ── Calendar rendering (§3.1 / §3.4) ──────────────────────────────────────

    def _populate_calendar(self, table: QTableWidget, schedule: Schedule) -> None:
        """Fill calendar cells, colour-coded by programme (§3.1). Cell content §3.4."""
        table.clearContents()
        table.setRowCount(0)

        if not schedule.assignments:
            return

        # date → [course_ids]
        date_to_ids: Dict[date, List[str]] = {}
        for course_id, exam_date in schedule.assignments.items():
            date_to_ids.setdefault(exam_date, []).append(course_id)

        all_dates = sorted(date_to_ids)
        start, end = all_dates[0], all_dates[-1]
        week_start = start - timedelta(days=start.weekday())
        last_sunday = end + timedelta(days=6 - end.weekday())
        num_weeks   = (last_sunday - week_start).days // 7 + 1

        table.setRowCount(num_weeks)

        for week in range(num_weeks):
            for dow in range(7):                          # 0=Mon … 6=Sun
                d           = week_start + timedelta(days=week * 7 + dow)
                course_ids  = date_to_ids.get(d, [])
                lines       = [d.strftime("%d/%m")]
                first_prog  = None

                for cid in course_ids:
                    course = self._courses_by_id.get(cid)
                    if not course:
                        lines.append(cid)
                        continue
                    relevant = next(
                        (o for o in course.offerings if o.program_id in self._prog_color_map),
                        None,
                    )
                    # §3.4 — course ID, name, programme, mandatory/elective
                    req     = "Elective" if (relevant and relevant.is_elective()) else "Obligatory"
                    prog_id = relevant.program_id if relevant else ""
                    if first_prog is None:
                        first_prog = prog_id
                    lines.append(f"{cid} | {course.name[:20]}")
                    lines.append(f"{prog_id} | {req}")

                item = QTableWidgetItem("\n".join(lines))
                item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                if first_prog and first_prog in self._prog_color_map:
                    item.setBackground(QColor(self._prog_color_map[first_prog]))
                table.setItem(week, dow, item)

        table.resizeRowsToContents()

    # ── Save (§3.5) ───────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Schedule", "schedules.txt", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        selected = {
            key: [schedules[self._current_index[key]]]
            for key, schedules in self._schedules_by_period.items()
            if schedules
        }
        try:
            self._controller.export(selected, Path(path))
            QMessageBox.information(self, "Saved", f"Schedule saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            logger.exception("Save failed")


# ─────────────────────────────────────────────────────────────────────────────
# Main widget
# ─────────────────────────────────────────────────────────────────────────────

class InputScreen(QWidget):
    """
    Full application layout:
        QSplitter(Horizontal)
            ├── Sidebar  (controls, min 250 / max 320 px)
            └── Workspace  (QTabWidget with 3 tabs)
    """

    def __init__(self, controller: DesktopController, parent=None):
        super().__init__(parent)
        self._controller    = controller
        self._date_editors: Dict[str, DateEditorWidget] = {}
        self._setup_ui()

    # ── Top-level layout ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_workspace())
        splitter.setSizes([300, 900])

        root.addWidget(splitter)

    # ── Sidebar ────────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(250)
        sidebar.setMaximumWidth(320)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Workflow hint banner — tells the user the three steps at a glance
        steps_lbl = QLabel("① Load files  ·  ② Select programme  ·  ③ Generate")
        steps_lbl.setWordWrap(True)
        steps_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        steps_lbl.setStyleSheet(
            "font-size: 10px; color: rgba(173,198,255,0.6);"
            "background: rgba(255,255,255,0.04); border-radius: 4px; padding: 4px 6px;"
        )
        layout.addWidget(steps_lbl)

        # Section — Load Mode
        mode_box = QGroupBox("Load Mode")
        ml = QVBoxLayout(mode_box)
        radios_row = QHBoxLayout()
        radios_row.setSpacing(4)
        self._mode_group = QButtonGroup(self)
        for label in ("Replace", "Append", "Update"):
            rb = QRadioButton(label)
            self._mode_group.addButton(rb)
            radios_row.addWidget(rb)
        self._mode_group.buttons()[0].setChecked(True)
        ml.addLayout(radios_row)
        mode_hint = QLabel("Replace: clear all  ·  Append: add new  ·  Update: overwrite by ID")
        mode_hint.setStyleSheet("font-size: 10px; color: rgba(173,198,255,0.55);")
        mode_hint.setWordWrap(True)
        ml.addWidget(mode_hint)
        layout.addWidget(mode_box)

        # Section — Files
        files_box = QGroupBox("Files")
        fl = QVBoxLayout(files_box)
        fl.setSpacing(4)

        # Courses sub-section
        th, dh = _file_header("\U0001f4da Courses", "Course IDs, names & programme links")
        fl.addWidget(th)
        fl.addWidget(dh)
        cr = QHBoxLayout()
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
        cr.addWidget(self._load_courses_btn)
        cr.addWidget(self._courses_label, 1)
        fl.addLayout(cr)

        fl.addSpacing(6)

        # Exam Periods sub-section
        th2, dh2 = _file_header("\U0001f4c5 Exam Periods", "Scheduling date windows (start → end)")
        fl.addWidget(th2)
        fl.addWidget(dh2)
        pr = QHBoxLayout()
        self._load_periods_btn = QPushButton("Load Periods")
        self._load_periods_btn.clicked.connect(self._load_dates)
        self._load_periods_btn.setToolTip(
            "Load a .txt file containing exam periods:\n"
            "  • period name (e.g. Moed A, Moed B)\n"
            "  • start date and end date"
        )
        self._dates_label = QLabel("No file loaded")
        self._dates_label.setWordWrap(True)
        pr.addWidget(self._load_periods_btn)
        pr.addWidget(self._dates_label, 1)
        fl.addLayout(pr)

        fl.addSpacing(6)

        # Programmes sub-section
        th3, dh3 = _file_header("\U0001f393 Programmes", "Which programmes to schedule (max 5)")
        fl.addWidget(th3)
        fl.addWidget(dh3)
        pr2 = QHBoxLayout()
        self._load_programs_btn = QPushButton("Load Programs")
        self._load_programs_btn.clicked.connect(self._load_programs)
        self._load_programs_btn.setToolTip(
            "Load a .txt file listing programme IDs to schedule:\n"
            "  • comma-separated 5-digit IDs  (e.g. 83101, 83102)\n"
            "  • maximum 5 programmes"
        )
        self._programs_label = QLabel("No file loaded")
        self._programs_label.setWordWrap(True)
        pr2.addWidget(self._load_programs_btn)
        pr2.addWidget(self._programs_label, 1)
        fl.addLayout(pr2)

        layout.addWidget(files_box)

        # Section — Programme selection (§2.2)
        prog_box = QGroupBox("Study Programmes  (max 5)")
        pl = QVBoxLayout(prog_box)
        pl.setSpacing(4)

        # Placeholder shown while the list is empty (before a courses file is loaded)
        self._prog_placeholder = QLabel(
            "Programmes appear here\nafter loading a programs or courses file."
        )
        self._prog_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prog_placeholder.setStyleSheet(
            "font-size: 10px; color: rgba(173,198,255,0.45); padding: 8px 4px;"
        )
        pl.addWidget(self._prog_placeholder)

        self._prog_list = QListWidget()
        self._prog_list.setMinimumHeight(100)
        self._prog_list.setVisible(False)   # hidden until populated
        self._prog_list.itemChanged.connect(self._on_programme_toggled)
        pl.addWidget(self._prog_list)

        self._prog_count_lbl = QLabel("0 / 5 selected")
        self._prog_count_lbl.setStyleSheet("font-size: 11px;")
        pl.addWidget(self._prog_count_lbl)
        layout.addWidget(prog_box)

        # Push generate button to the bottom
        layout.addStretch()

        # Status line
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("font-size: 10px; color: #adc6ff;")
        layout.addWidget(self._status_label)

        # Generate button — pinned at bottom
        self._gen_btn = QPushButton("▶  Generate Schedule")
        self._gen_btn.setObjectName("generateBtn")
        self._gen_btn.setEnabled(False)
        self._gen_btn.setFixedHeight(38)
        self._gen_btn.clicked.connect(self._on_generate)
        layout.addWidget(self._gen_btn)

        return sidebar

    # ── Right workspace ────────────────────────────────────────────────────────

    def _build_workspace(self) -> QTabWidget:
        self._workspace = QTabWidget()

        # Tab 1 — Course Details (§2.3)
        course_tab = QWidget()
        ct_layout = QVBoxLayout(course_tab)
        ct_layout.setContentsMargins(0, 0, 0, 0)
        self._courses_placeholder = QLabel(
            "No courses loaded yet.\n\nLoad a courses file from the sidebar."
        )
        self._courses_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._courses_placeholder.setStyleSheet(
            "font-size: 13px; color: rgba(173,198,255,0.5);"
        )
        ct_layout.addWidget(self._courses_placeholder)
        self._course_table = _make_data_table(
            ["Course Name", "ID", "Year", "Semester", "Requirement", "Evaluation"]
        )
        self._course_table.setVisible(False)
        ct_layout.addWidget(self._course_table)
        self._workspace.addTab(course_tab, "Course Details")

        # Tab 2 — Exam Periods (§2.4)
        self._periods_container = QWidget()
        ptl = QVBoxLayout(self._periods_container)
        ptl.setContentsMargins(4, 4, 4, 4)
        self._no_periods_hint = QLabel("Load an exam-periods file to edit dates here.")
        self._no_periods_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ptl.addWidget(self._no_periods_hint)
        self._period_tabs = QTabWidget()
        self._period_tabs.setVisible(False)
        ptl.addWidget(self._period_tabs)
        self._workspace.addTab(self._periods_container, "Exam Periods")

        # Tab 3 — Schedule Results (§3.1 – §3.5)
        self._results_panel = _ResultsPanel(self._controller)
        self._workspace.addTab(self._results_panel, "Schedule Results")

        return self._workspace

    # ── File loading ───────────────────────────────────────────────────────────

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

    # ── Programme management ───────────────────────────────────────────────────

    def _refresh_programme_list(self) -> None:
        self._prog_list.blockSignals(True)
        self._prog_list.clear()
        for pid in self._controller.get_programme_ids():
            item = QListWidgetItem(pid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._prog_list.addItem(item)
        self._prog_list.blockSignals(False)
        # Toggle between the placeholder hint and the populated list
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
                self, "Limit Reached",
                f"You can select at most {_MAX_PROGS} programmes.",
            )
            return
        self._update_prog_label()
        self._refresh_course_table()
        self._update_gen_btn()

    def _count_checked(self) -> int:
        return sum(
            1 for i in range(self._prog_list.count())
            if self._prog_list.item(i).checkState() == Qt.CheckState.Checked
        )

    def _get_selected_ids(self) -> List[str]:
        return [
            self._prog_list.item(i).text()
            for i in range(self._prog_list.count())
            if self._prog_list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def _update_prog_label(self) -> None:
        n = self._count_checked()
        self._prog_count_lbl.setText(f"{n} / {_MAX_PROGS} selected")

    # ── Tab 1: Course Details table ────────────────────────────────────────────

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
                    for col, value in enumerate([
                        course.name,
                        course.id,
                        str(offering.year),
                        offering.semester,
                        offering.requirement,
                        course.evaluation_type,
                    ]):
                        self._course_table.setItem(row, col, QTableWidgetItem(value))
        # Show placeholder when there are no rows (nothing selected or no courses loaded)
        has_rows = self._course_table.rowCount() > 0
        self._courses_placeholder.setVisible(not has_rows)
        self._course_table.setVisible(has_rows)

    # ── Tab 2: Exam period date editors ───────────────────────────────────────

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
            key    = period.get_key()
            editor = DateEditorWidget(period)
            editor.period_changed.connect(self._sync_periods)
            self._date_editors[key] = editor
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(editor)
            self._period_tabs.addTab(scroll, key)

    def _sync_periods(self) -> None:
        self._controller.update_exam_periods(
            [e.get_exam_period() for e in self._date_editors.values()]
        )

    # ── Generation ────────────────────────────────────────────────────────────

    def _on_generate(self) -> None:
        selected = self._get_selected_ids()
        self._controller.set_selected_programs(selected)
        self._sync_periods()

        self._gen_btn.setEnabled(False)
        self._gen_btn.setText("⏳  Generating…")

        self._worker = _GenerateWorker(self._controller, parent=self)
        self._worker.finished.connect(
            lambda sbp, cbi: self._on_generate_done(selected, sbp, cbi)
        )
        self._worker.failed.connect(self._on_generate_failed)
        self._worker.start()

    def _on_generate_done(
        self,
        selected: List[str],
        schedules_by_period: dict,
        courses_by_id: dict,
    ) -> None:
        prog_color_map = {
            pid: PROGRAMME_COLOURS[i % len(PROGRAMME_COLOURS)]
            for i, pid in enumerate(selected)
        }
        self._results_panel.load(schedules_by_period, courses_by_id, prog_color_map)
        self._workspace.setCurrentIndex(2)
        total = sum(len(v) for v in schedules_by_period.values())
        self._status_label.setText(f"✓ {total} schedule(s) ready.")
        self._gen_btn.setEnabled(True)
        self._gen_btn.setText("▶  Generate Schedule")

    def _on_generate_failed(self, error_msg: str) -> None:
        QMessageBox.critical(self, "Generation Error", error_msg)
        logger.error("Generation failed: %s", error_msg)
        self._gen_btn.setEnabled(True)
        self._gen_btn.setText("▶  Generate Schedule")

    def _update_gen_btn(self) -> None:
        self._gen_btn.setEnabled(
            self._controller.has_courses
            and self._controller.has_periods
            and self._count_checked() >= 1
        )
