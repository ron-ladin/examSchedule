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

from PyQt6.QtCore import Qt, pyqtSignal
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

logger = logging.getLogger(__name__)

_MAX_PROGS   = 5
# Up to 5 programme colours (used for calendar cell highlights)
_PROG_COLORS = ["#AED6F1", "#A9DFBF", "#F9E79F", "#F5CBA7", "#D2B4DE"]


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helper
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

    # Kept for backward compatibility with app.py
    schedule_ready = pyqtSignal(dict, dict)

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

        # Section — Load Mode
        mode_box = QGroupBox("Load Mode")
        ml = QHBoxLayout(mode_box)
        ml.setSpacing(4)
        self._mode_group = QButtonGroup(self)
        for label in ("Replace", "Append", "Update"):
            rb = QRadioButton(label)
            self._mode_group.addButton(rb)
            ml.addWidget(rb)
        self._mode_group.buttons()[0].setChecked(True)
        layout.addWidget(mode_box)

        # Section — Files
        files_box = QGroupBox("Files")
        fl = QVBoxLayout(files_box)
        fl.setSpacing(6)

        # Courses row
        cr = QHBoxLayout()
        self._load_courses_btn = QPushButton("Load Courses")
        self._load_courses_btn.clicked.connect(self._load_courses)
        self._courses_label = QLabel("No file loaded")
        self._courses_label.setWordWrap(True)
        cr.addWidget(self._load_courses_btn)
        cr.addWidget(self._courses_label, 1)
        fl.addLayout(cr)

        # Periods row
        pr = QHBoxLayout()
        self._load_periods_btn = QPushButton("Load Periods")
        self._load_periods_btn.clicked.connect(self._load_dates)
        self._dates_label = QLabel("No file loaded")
        self._dates_label.setWordWrap(True)
        pr.addWidget(self._load_periods_btn)
        pr.addWidget(self._dates_label, 1)
        fl.addLayout(pr)

        layout.addWidget(files_box)

        # Section — Programme selection (§2.2)
        prog_box = QGroupBox("Study Programmes  (max 5)")
        pl = QVBoxLayout(prog_box)
        self._prog_list = QListWidget()
        self._prog_list.setMinimumHeight(100)
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
        self._course_table = _make_data_table(
            ["Course Name", "ID", "Year", "Semester", "Requirement", "Evaluation"]
        )
        self._workspace.addTab(self._course_table, "Course Details")

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
        self._update_prog_label()

    def _on_programme_toggled(self, item: QListWidgetItem) -> None:
        if self._count_checked() > _MAX_PROGS:
            item.setCheckState(Qt.CheckState.Unchecked)
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
        try:
            schedules_by_period, courses_by_id = self._controller.generate()
            prog_color_map = {
                pid: _PROG_COLORS[i % len(_PROG_COLORS)]
                for i, pid in enumerate(selected)
            }
            # Populate Tab 3 and switch to it
            self._results_panel.load(schedules_by_period, courses_by_id, prog_color_map)
            self._workspace.setCurrentIndex(2)

            total = sum(len(v) for v in schedules_by_period.values())
            self._status_label.setText(f"✓ {total} schedule(s) ready.")
            self.schedule_ready.emit(schedules_by_period, courses_by_id)
        except Exception as exc:
            QMessageBox.critical(self, "Generation Error", str(exc))
            logger.exception("Generation failed")
        finally:
            self._gen_btn.setEnabled(True)
            self._gen_btn.setText("▶  Generate Schedule")

    def _update_gen_btn(self) -> None:
        self._gen_btn.setEnabled(
            self._controller.has_courses
            and self._controller.has_periods
            and self._count_checked() >= 1
        )
