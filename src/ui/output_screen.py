"""
Widget: OutputScreen
---------------------
Displays generated schedules  (SRS §3.1 – §3.5).

    §3.1   Calendar grid colour-coded by programme.
    §3.2   Prev / Next navigation between alternative schedules.
    §3.3   "Schedule X of Y" counter per period.
    §3.4   Each exam cell: course ID, name, programme, mandatory/elective.
    §3.5   Save button — writes the currently displayed schedule to a file.
"""

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
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

from src.domain.course import Course
from src.domain.schedule import Schedule

logger = logging.getLogger(__name__)

# Up to 5 programme colours (Electric Blue → Indigo → Emerald → Amber → Red)
_PROG_COLORS = ["#AED6F1", "#A9DFBF", "#F9E79F", "#F5CBA7", "#D2B4DE"]
_DAYS        = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class OutputScreen(QWidget):
    """
    Results view with per-period tabs, Prev/Next navigation, and Save.

    Parameters
    ----------
    schedules_by_period : Dict[str, List[Schedule]]
    courses_by_id       : Dict[str, Course]
    selected_programs   : List[str]
    on_back             : callable — invoked when the user clicks ← Back
    on_save             : callable(schedules_by_period, path) — invoked on Save
    """

    def __init__(
        self,
        schedules_by_period: Dict[str, List[Schedule]],
        courses_by_id: Dict[str, Course],
        selected_programs: List[str],
        on_back: Callable,
        on_save: Callable,
        parent=None,
    ):
        super().__init__(parent)
        self._schedules_by_period = schedules_by_period
        self._courses_by_id = courses_by_id
        self._on_back = on_back
        self._on_save_cb = on_save
        self._prog_color_map: Dict[str, str] = {
            pid: _PROG_COLORS[i % len(_PROG_COLORS)]
            for i, pid in enumerate(selected_programs)
        }
        # Per-period current index
        self._current_index: Dict[str, int] = {k: 0 for k in schedules_by_period}
        self._setup_ui()

    # ── UI setup ──────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        # Top bar
        top_row = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(self._on_back)
        top_row.addWidget(back_btn)
        top_row.addStretch()

        total = sum(len(v) for v in self._schedules_by_period.values())
        summary = QLabel(
            f"✓  {total} schedule(s) across {len(self._schedules_by_period)} period(s)."
        )
        summary.setStyleSheet("color:#16a34a; font-weight:bold;")
        top_row.addWidget(summary)
        top_row.addStretch()

        save_btn = QPushButton("💾  Save Schedule")
        save_btn.setStyleSheet(
            "QPushButton { background:#16a34a; color:white; padding:5px 14px;"
            "  border-radius:5px; font-weight:bold; }"
            "QPushButton:hover { background:#15803d; }"
        )
        save_btn.clicked.connect(self._on_save)
        top_row.addWidget(save_btn)
        layout.addLayout(top_row)

        # Period tabs
        if not self._schedules_by_period:
            layout.addWidget(
                QLabel("⚠  No schedules were generated. Try different settings.")
            )
            return

        self._tabs = QTabWidget()
        for period_key, schedules in self._schedules_by_period.items():
            tab = self._build_period_tab(period_key, schedules)
            self._tabs.addTab(tab, period_key)
        layout.addWidget(self._tabs)

    def _build_period_tab(self, period_key: str, schedules: List[Schedule]) -> QWidget:
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(4, 4, 4, 4)

        if not schedules:
            layout.addWidget(QLabel("⚠  No valid schedules for this period."))
            return outer

        # §3.2 – §3.3  Navigation bar
        nav_row = QHBoxLayout()
        prev_btn = QPushButton("◀  Prev")
        counter  = QLabel(f"Schedule 1 of {len(schedules)}")  # §3.3
        counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        counter.setStyleSheet("font-weight:bold; min-width:160px;")
        next_btn = QPushButton("Next  ▶")

        nav_row.addWidget(prev_btn)
        nav_row.addStretch()
        nav_row.addWidget(counter)
        nav_row.addStretch()
        nav_row.addWidget(next_btn)
        layout.addLayout(nav_row)

        # Calendar table (§3.1)
        table = self._make_calendar_table()
        layout.addWidget(table)

        # Wire up navigation
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

    # ── Calendar rendering ────────────────────────────────────────────────────

    def _make_calendar_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(_DAYS)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        return table

    def _populate_calendar(self, table: QTableWidget, schedule: Schedule) -> None:
        """§3.1 — Fill the calendar table for the given schedule."""
        table.clearContents()
        table.setRowCount(0)

        if not schedule.assignments:
            return

        # Invert: date → list of course_ids  (multiple exams can share a date)
        date_to_ids: Dict[date, List[str]] = {}
        for course_id, exam_date in schedule.assignments.items():
            date_to_ids.setdefault(exam_date, []).append(course_id)

        all_dates = sorted(date_to_ids)
        start, end = all_dates[0], all_dates[-1]

        # Align grid to Monday of the first week
        week_start = start - timedelta(days=start.weekday())
        week_end   = end   + timedelta(days=6 - end.weekday())
        num_weeks  = (week_end - week_start).days // 7 + 1

        table.setRowCount(num_weeks)

        for week in range(num_weeks):
            max_rows_in_week = 1  # for row-height calculation
            for dow in range(7):
                d = week_start + timedelta(days=week * 7 + dow)
                course_ids = date_to_ids.get(d, [])

                # §3.4 — Build cell text
                lines = [d.strftime("%d/%m")]
                for cid in course_ids:
                    course = self._courses_by_id.get(cid)
                    if not course:
                        lines.append(cid)
                        continue
                    # Requirement from most relevant offering
                    relevant = next(
                        (o for o in course.offerings if o.program_id in self._prog_color_map),
                        None,
                    )
                    req_tag = "Elective" if (relevant and relevant.is_elective()) else "Obligatory"
                    prog_id = relevant.program_id if relevant else ""
                    lines.append(f"{cid} | {course.name[:18]}")
                    lines.append(f"{prog_id} | {req_tag}")

                item = QTableWidgetItem("\n".join(lines))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
                )

                # Colour by programme (§3.1)
                if course_ids:
                    first_course = self._courses_by_id.get(course_ids[0])
                    colour = "#FFFFFF"
                    if first_course:
                        prog_id = next(
                            (o.program_id for o in first_course.offerings
                             if o.program_id in self._prog_color_map),
                            None,
                        )
                        if prog_id:
                            colour = self._prog_color_map[prog_id]
                    item.setBackground(QColor(colour))

                table.setItem(week, dow, item)

        table.resizeRowsToContents()

    # ── Save ──────────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        """§3.5 — Open save dialog and invoke the controller's export."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Schedule", "schedules.txt", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return

        # Collect one schedule per period (the currently displayed one)
        selected = {
            key: [schedules[self._current_index[key]]]
            for key, schedules in self._schedules_by_period.items()
            if schedules
        }
        self._on_save_cb(selected, Path(path))
