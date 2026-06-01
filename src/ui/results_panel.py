"""
Widget: _ResultsPanel — Schedule Results Tab (SRS §3.1 – §3.5)
---------------------------------------------------------------
Shows combined Cartesian-product schedules across all exam periods.

Public API:
    load(schedules_by_period, courses_by_id, prog_color_map)  — populate after generation
"""

import logging
from datetime import date, timedelta
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.controller import RESULT_CAP, DesktopController
from src.domain.course import Course
from src.domain.schedule import Schedule

logger = logging.getLogger(__name__)


def _make_data_table(headers: list[str]) -> QTableWidget:
    """Create a read-only, row-selecting, last-column-stretching QTableWidget."""
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    return table


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
        total = self._controller.get_combined_schedule_count(self._schedules_by_period)
        self._period_tabs.clear()

        if total == 0:
            self._summary_lbl.setStyleSheet("color: #e05c5c; font-weight: bold;")
            self._summary_lbl.setText("⚠   No valid combined schedules found.")
            self._counter_lbl.setText("Combined Schedule 0 of 0")
            self._back_200_btn.setEnabled(False)
            self._prev_btn.setEnabled(False)
            self._next_btn.setEnabled(False)
            self._forward_200_btn.setEnabled(self._controller.has_any_more_schedules())
            return

        if self._combined_index >= total:
            self._combined_index = total - 1

        combined = self._controller.get_combined_schedule_at(
            self._schedules_by_period, self._combined_index
        )

        for period_key, schedule in combined.items():
            table = _make_data_table(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            self._populate_calendar(table, schedule)
            self._period_tabs.addTab(table, period_key)

        self._counter_lbl.setText(
            f"Combined Schedule {self._combined_index + 1} of {total}"
        )

        has_more_loaded = self._combined_index < total - 1
        has_more_unloaded = self._controller.has_any_more_schedules()

        self._back_200_btn.setEnabled(self._combined_index > 0)
        self._prev_btn.setEnabled(self._combined_index > 0)
        self._next_btn.setEnabled(has_more_loaded or has_more_unloaded)
        self._forward_200_btn.setEnabled(has_more_loaded or has_more_unloaded)

        self._summary_lbl.setStyleSheet("color: #a9dfbf; font-weight: bold;")
        if has_more_unloaded:
            self._summary_lbl.setText(
                f"✓   {total} loaded combined schedule option(s). "
                f"Forward {RESULT_CAP} will load more automatically if needed."
            )
        else:
            self._summary_lbl.setText(f"✓   {total} combined schedule option(s).")

    def _go_prev(self) -> None:
        if self._combined_index > 0:
            self._combined_index -= 1
            self._refresh_combined_view()

    def _go_next(self) -> None:
        target_index = self._combined_index + 1
        self._ensure_loaded_until(target_index)
        total = self._controller.get_combined_schedule_count(self._schedules_by_period)
        if target_index < total:
            self._combined_index = target_index
            self._refresh_combined_view()

    def _go_back_page(self) -> None:
        self._combined_index = max(0, self._combined_index - RESULT_CAP)
        self._refresh_combined_view()

    def _go_forward_page(self) -> None:
        target_index = self._combined_index + RESULT_CAP
        self._ensure_loaded_until(target_index)
        total = self._controller.get_combined_schedule_count(self._schedules_by_period)
        if total == 0:
            return
        self._combined_index = min(target_index, total - 1)
        self._refresh_combined_view()

    def _ensure_loaded_until(self, target_index: int) -> None:
        """Load more per-period schedules until target_index exists."""
        while (
            self._controller.get_combined_schedule_count(self._schedules_by_period)
            <= target_index
            and self._controller.has_any_more_schedules()
        ):
            loaded_any = False
            for period_key in list(self._schedules_by_period):
                if self._controller.has_more_schedules(period_key):
                    more = self._controller.load_more_schedules(period_key)
                    if more:
                        self._schedules_by_period[period_key].extend(more)
                        loaded_any = True
                        break
            if not loaded_any:
                break

    def _populate_calendar(self, table: QTableWidget, schedule: Schedule) -> None:
        """Fill calendar cells, colour-coded by programme (§3.4)."""
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
                first_prog = None
                course_lines: list[str] = []

                for course_id in course_ids:
                    course = self._courses_by_id.get(course_id)
                    if not course:
                        course_lines.append(course_id)
                        continue

                    relevant = next(
                        (o for o in course.offerings if o.program_id in self._prog_color_map),
                        None,
                    )
                    req = "E" if (relevant and relevant.is_elective()) else "O"
                    prog_id = relevant.program_id if relevant else ""

                    if first_prog is None:
                        first_prog = prog_id

                    course_lines.append(f"  {course.name[:18]}")
                    prog_label = prog_id if prog_id else "—"
                    course_lines.append(f"  {course_id}  ·  {req}  ·  {prog_label}")

                date_header = current_date.strftime("%a %d/%m")
                cell_text = (
                    f"{date_header}\n{'─' * 14}\n" + "\n".join(course_lines)
                    if course_lines
                    else date_header
                )

                item = QTableWidgetItem(cell_text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

                if first_prog and first_prog in self._prog_color_map:
                    c = QColor(self._prog_color_map[first_prog])
                    c.setAlpha(55)
                    item.setBackground(c)

                table.setItem(week, dow, item)

        table.resizeRowsToContents()

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Schedule", "schedules.txt", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return

        total = self._controller.get_combined_schedule_count(self._schedules_by_period)
        if total == 0:
            QMessageBox.warning(self, "Save Error", "No combined schedule to save.")
            return

        combined = self._controller.get_combined_schedule_at(
            self._schedules_by_period, self._combined_index
        )
        selected = {k: [v] for k, v in combined.items()}

        try:
            self._controller.export(selected, Path(path))
            QMessageBox.information(self, "Saved", f"Schedule saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            logger.exception("Save failed")
