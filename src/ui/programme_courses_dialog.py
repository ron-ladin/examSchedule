"""
Widget: ProgrammeCoursesDialog — per-programme course drill-down (SRS §2.3.2).

Opens from ConfigScreen when the user clicks "View Courses ▶" after highlighting
a programme in the list.  Shows all courses belonging to that programme, filterable
by Year and Semester in real-time.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.controller import DesktopController
from src.domain.semester import display_semester
from src.ui.results_panel import _make_data_table
from src.ui.tokens import PROGRAM_NAMES_MAPPING

_HEADERS = [
    "Course ID",
    "Course Name",
    "Year",
    "Semester",
    "Mandatory/Elective",
    "Evaluation",
]

_ALL_YEARS = "All Years"
_ALL_SEMS = "All Semesters"


class ProgrammeCoursesDialog(QDialog):
    """Modal dialog listing all courses for one programme with year/semester filters."""

    def __init__(
        self,
        programme_id: str,
        controller: DesktopController,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._programme_id = programme_id
        self._controller = controller

        name = PROGRAM_NAMES_MAPPING.get(programme_id, programme_id)
        self.setWindowTitle(f"{name} — Courses")
        self.setModal(True)
        self.setMinimumSize(660, 420)

        self._courses = controller.get_courses_by_programme(programme_id)
        self._setup_ui()
        self._populate_table(_ALL_YEARS, _ALL_SEMS)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        filter_row.addWidget(QLabel("Year:"))
        self._year_combo = QComboBox()
        self._year_combo.addItems([_ALL_YEARS, "Year 1", "Year 2", "Year 3", "Year 4"])
        self._year_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._year_combo)

        filter_row.addSpacing(16)

        filter_row.addWidget(QLabel("Semester:"))
        self._sem_combo = QComboBox()
        self._sem_combo.addItems([_ALL_SEMS, "FALL", "SPRING", "SUMMER"])
        self._sem_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._sem_combo)

        filter_row.addStretch()
        root.addLayout(filter_row)

        self._table = _make_data_table(_HEADERS)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._table)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedSize(110, 36)
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

    def _on_filter_changed(self) -> None:
        self._populate_table(
            self._year_combo.currentText(),
            self._sem_combo.currentText(),
        )

    def _populate_table(self, year_filter: str, sem_filter: str) -> None:
        self._table.setRowCount(0)

        year_int: int | None = None
        if year_filter != _ALL_YEARS:
            try:
                year_int = int(year_filter.split()[-1])
            except ValueError:
                pass

        sem_internal: str | None = None
        if sem_filter != _ALL_SEMS:
            _display_to_internal = {"FALL": "FALL", "SPRING": "SPRI", "SUMMER": "SUMM"}
            sem_internal = _display_to_internal.get(sem_filter)

        for course in self._courses:
            for offering in course.offerings:
                if offering.program_id != self._programme_id:
                    continue
                if year_int is not None and offering.year != year_int:
                    continue
                if sem_internal is not None and offering.semester != sem_internal:
                    continue

                row = self._table.rowCount()
                self._table.insertRow(row)

                for col, value in enumerate([
                    course.id,
                    course.name,
                    str(offering.year),
                    display_semester(offering.semester),
                    offering.requirement,
                    course.evaluation_type,
                ]):
                    item = QTableWidgetItem(value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._table.setItem(row, col, item)
