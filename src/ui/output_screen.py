from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

PROGRAMME_COLOURS = ["#AED6F1", "#A9DFBF", "#F9E79F", "#F5CBA7", "#D2B4DE"]
DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


class OutputScreen(QWidget):
    def __init__(self, on_back, parent=None):
        super().__init__(parent)
        self._on_back = on_back
        self._schedules: list = []
        self._current_index = 0
        self._programme_colour_map: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.addLayout(self._build_nav_bar())
        self._calendar = self._build_calendar()
        layout.addWidget(self._calendar)
        layout.addLayout(self._build_action_bar())

    def _build_nav_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        btn_back = QPushButton("← Back")
        btn_back.clicked.connect(self._on_back)
        self._btn_prev = QPushButton("◀ Prev")
        self._btn_prev.clicked.connect(self._prev)
        self._counter_label = QLabel("No schedules")
        self._counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._btn_next = QPushButton("Next ▶")
        self._btn_next.clicked.connect(self._next)
        row.addWidget(btn_back)
        row.addStretch()
        row.addWidget(self._btn_prev)
        row.addWidget(self._counter_label)
        row.addWidget(self._btn_next)
        return row

    def _build_calendar(self) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(DAYS)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        return table

    def _build_action_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()
        btn_save = QPushButton("Save Schedule…")
        btn_save.setFixedHeight(36)
        btn_save.clicked.connect(self._save)
        row.addWidget(btn_save)
        return row

    def load_schedules(self, schedules: list, programmes: list[str]) -> None:
        self._schedules = schedules
        self._current_index = 0
        self._programme_colour_map = {
            pid: PROGRAMME_COLOURS[i % len(PROGRAMME_COLOURS)]
            for i, pid in enumerate(programmes)
        }
        self._render_current()

    def _render_current(self) -> None:
        total = len(self._schedules)
        if total == 0:
            self._counter_label.setText("No schedules found")
            self._btn_prev.setEnabled(False)
            self._btn_next.setEnabled(False)
            self._calendar.clearContents()
            self._calendar.setRowCount(0)
            return

        idx = self._current_index
        self._counter_label.setText(f"System {idx + 1} of {total}")
        self._btn_prev.setEnabled(idx > 0)
        self._btn_next.setEnabled(idx < total - 1)
        self._populate_calendar(self._schedules[idx])

    def _populate_calendar(self, schedule) -> None:
        from datetime import timedelta
        self._calendar.clearContents()
        self._calendar.setRowCount(0)

        # assignments is {course_id: date} — invert to {date: course_id} for calendar lookup
        if not schedule.assignments:
            return

        date_to_course = {v: k for k, v in schedule.assignments.items()}
        dates = sorted(date_to_course.keys())
        start, end = dates[0], dates[-1]
        offset = (start.weekday() + 1) % 7
        first_day = start - timedelta(days=offset)

        total_days = (end - first_day).days + 1
        rows = (total_days + 6) // 7
        self._calendar.setRowCount(rows)

        courses_by_id: dict = {}
        if hasattr(schedule, "courses"):
            courses_by_id = {c.id: c for c in schedule.courses}

        for r in range(rows):
            for c in range(7):
                d = first_day + timedelta(days=r * 7 + c)
                if d < start or d > end:
                    continue
                if d in date_to_course:
                    course_id = date_to_course[d]
                    course = courses_by_id.get(course_id)
                    if course:
                        prog_ids = [o.program_id for o in course.offerings]
                        prog_id = prog_ids[0] if prog_ids else ""
                        req = "Mandatory" if any(o.requirement.lower() == "obligatory" for o in course.offerings) else "Elective"
                        text = f"{course_id}\n{course.name[:20]}\n{prog_id} | {req}"
                    else:
                        prog_id = ""
                        text = course_id
                    item = QTableWidgetItem(text)
                    colour = self._programme_colour_map.get(prog_id, "#FFFFFF")
                    item.setBackground(QColor(colour))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._calendar.setItem(r, c, item)
                elif start <= d <= end:
                    item = QTableWidgetItem(d.strftime("%d"))
                    item.setForeground(QColor("#AAAAAA"))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._calendar.setItem(r, c, item)

        self._calendar.resizeRowsToContents()

    def _prev(self) -> None:
        if self._current_index > 0:
            self._current_index -= 1
            self._render_current()

    def _next(self) -> None:
        if self._current_index < len(self._schedules) - 1:
            self._current_index += 1
            self._render_current()

    def _save(self) -> None:
        if not self._schedules:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Schedule", "schedule.txt", "Text files (*.txt)")
        if not path:
            return
        try:
            from src.adapters.text_file_exporter import TextFileExporter
            from pathlib import Path
            schedule = self._schedules[self._current_index]
            courses_by_id = {c.id: c for c in schedule.courses} if hasattr(schedule, "courses") else {}
            exporter = TextFileExporter(Path(path))
            exporter.export_schedules({"Exported": [schedule]}, courses_by_id)
            QMessageBox.information(self, "Saved", f"Schedule saved to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
