"""
Widget: ExamDetailDialog — per-date exam details popup (Phase 1 §4).

Opens from a schedule calendar cell when the user clicks a purple date.
Displays: Course Number, Course Name, Requirement (full word), Programs Affected.
"""
from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.course import Course
from src.engine.classroom_assigner import usable_room_capacity
from src.ui.assets.icons import CalendarIcon
from src.ui.tokens import programme_display_name


class ExamDetailDialog(QDialog):
    """Modal showing full details for all exams on a specific date."""

    def __init__(
        self,
        exam_date: date,
        course_ids: list[str],
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        classroom_assignments: dict[str, list[ClassroomAssignment]] | None = None,
        unassigned_exams: dict[str, int] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exam Details")
        self.setMinimumWidth(900)
        self.setMinimumHeight(280)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setStyleSheet("QDialog { background: #FFFFFF; }")
        self._setup_ui(
            exam_date,
            course_ids,
            courses_by_id,
            prog_color_map,
            classroom_assignments or {},
            unassigned_exams or {},
        )

    def _setup_ui(
        self,
        exam_date: date,
        course_ids: list[str],
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        classroom_assignments: dict[str, list[ClassroomAssignment]],
        unassigned_exams: dict[str, int],
    ) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        # ── Header ─────────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        date_badge = CalendarIcon(22, "#2563EB")
        header_row.addWidget(date_badge)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title = QLabel(exam_date.strftime("%A, %d %B %Y"))
        title.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #1F2937; background: transparent;"
        )
        count_lbl = QLabel(
            f"{len(course_ids)} exam{'s' if len(course_ids) != 1 else ''} scheduled"
        )
        count_lbl.setStyleSheet("font-size: 11px; color: #6B7280; background: transparent;")
        title_col.addWidget(title)
        title_col.addWidget(count_lbl)
        header_row.addLayout(title_col)
        header_row.addStretch()
        layout.addLayout(header_row)

        # ── Thin separator ─────────────────────────────────────────────────────
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #E2E8F0;")
        layout.addWidget(sep)

        # ── Detail table ───────────────────────────────────────────────────────
        table = QTableWidget()
        table.setColumnCount(10)
        table.setHorizontalHeaderLabels(
            [
                "Course #",
                "Course Name",
                "Time Slot",
                "Building",
                "Room",
                "Students",
                "Exam Capacity (75%)",
                "Status",
                "Requirement",
                "Degree",
            ]
        )
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setMinimumHeight(34)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                background: white;
                gridline-color: #E8F0FE;
            }
            QHeaderView::section {
                background: #F8FAFC;
                color: #64748B;
                font-weight: 700;
                font-size: 10px;
                letter-spacing: 0.5px;
                padding: 8px 10px;
                border: none;
                border-bottom: 2px solid #E2E8F0;
            }
            QTableWidget::item { padding: 8px 10px; color: #1F2937; }
            QTableWidget::item:alternate { background: #F8FAFC; }
        """)

        rows = self._build_rows(
            course_ids,
            courses_by_id,
            prog_color_map,
            classroom_assignments,
            unassigned_exams,
        )
        table.setRowCount(len(rows))
        bold_font = QFont()
        bold_font.setWeight(QFont.Weight.Medium)

        for row_idx, row in enumerate(rows):
            course_id, name, slot, building, room, students, capacity, status, req, affected = row
            id_item = QTableWidgetItem(course_id)
            id_item.setFont(bold_font)
            id_item.setForeground(QColor("#1D4ED8"))
            table.setItem(row_idx, 0, id_item)

            table.setItem(row_idx, 1, QTableWidgetItem(name))
            table.setItem(row_idx, 2, QTableWidgetItem(slot))
            table.setItem(row_idx, 3, QTableWidgetItem(building))
            room_item = QTableWidgetItem(room)
            if room == "NO CLASSROOM":
                room_item.setForeground(QColor("#DC2626"))
            table.setItem(row_idx, 4, room_item)
            table.setItem(row_idx, 5, QTableWidgetItem(students))
            table.setItem(row_idx, 6, QTableWidgetItem(capacity))
            status_item = QTableWidgetItem(status)
            if status == "FULL":
                status_item.setForeground(QColor("#DC2626"))
                status_item.setBackground(QColor("#FEE2E2"))
            elif status == "AVAILABLE":
                status_item.setForeground(QColor("#047857"))
            table.setItem(row_idx, 7, status_item)

            req_item = QTableWidgetItem(req)
            if req == "Obligatory":
                req_item.setForeground(QColor("#1D4ED8"))
            elif req == "Elective":
                req_item.setForeground(QColor("#7C3AED"))
            table.setItem(row_idx, 8, req_item)

            aff_item = QTableWidgetItem(affected)
            if affected == "Not affected":
                aff_item.setForeground(QColor("#94A3B8"))
            table.setItem(row_idx, 9, aff_item)

        table.resizeRowsToContents()
        layout.addWidget(table)

        # ── Footer: Close button ───────────────────────────────────────────────
        btn_row = QHBoxLayout()
        full_screen_btn = QPushButton("Full Screen")
        full_screen_btn.setFixedWidth(120)
        full_screen_btn.clicked.connect(
            lambda: self._toggle_full_screen(full_screen_btn)
        )
        btn_row.addWidget(full_screen_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(110)
        close_btn.setFixedHeight(36)
        close_btn.setStyleSheet(
            "background: #2563EB; color: white; border: none; border-radius: 8px;"
            "font-weight: 600; font-size: 12px;"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _toggle_full_screen(self, button: QPushButton) -> None:
        if self.isFullScreen():
            self.showNormal()
            button.setText("Full Screen")
        else:
            self.showFullScreen()
            button.setText("Exit Full Screen")

    @staticmethod
    def _split_room_name(room_id: str) -> tuple[str, str]:
        if " - " in room_id:
            building, room = room_id.split(" - ", 1)
            return building, room
        return "—", room_id

    @staticmethod
    def _build_rows(
        course_ids: list[str],
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        classroom_assignments: dict[str, list[ClassroomAssignment]] | None = None,
        unassigned_exams: dict[str, int] | None = None,
    ) -> list[tuple[str, str, str, str, str, str, str, str, str, str]]:
        rows: list[tuple[str, str, str, str, str, str, str, str, str, str]] = []
        classroom_assignments = classroom_assignments or {}
        unassigned_exams = unassigned_exams or {}
        for course_id in course_ids:
            course = courses_by_id.get(course_id)
            name = course.name if course else course_id
            req_str = "—"
            affected: list[str] = []
            if course:
                for offering in course.offerings:
                    if offering.program_id in prog_color_map:
                        raw = offering.requirement.strip().lower()
                        if raw.startswith("oblig"):
                            req_str = "Obligatory"
                        elif raw.startswith("elec"):
                            req_str = "Elective"
                        if offering.program_id not in affected:
                            affected.append(offering.program_id)
            affected_str = (
                "; ".join(programme_display_name(program_id) for program_id in affected)
                if affected
                else "Not affected"
            )
            assignments = classroom_assignments.get(course_id, [])
            if course_id in unassigned_exams:
                rows.append(
                    (
                        course_id,
                        name,
                        "—",
                        "—",
                        "NO CLASSROOM",
                        str(unassigned_exams[course_id]),
                        "0",
                        "UNASSIGNED",
                        req_str,
                        affected_str,
                    )
                )
            elif assignments:
                for assignment in assignments:
                    building, room = ExamDetailDialog._split_room_name(
                        assignment.room.room_id
                    )
                    rows.append(
                        (
                            course_id,
                            name,
                            assignment.slot.time.strftime("%H:%M"),
                            building,
                            room,
                            str(assignment.students_assigned),
                            str(usable_room_capacity(assignment.room)),
                            (
                                "FULL"
                                if assignment.students_assigned
                                == usable_room_capacity(assignment.room)
                                else "AVAILABLE"
                            ),
                            req_str,
                            affected_str,
                        )
                    )
            else:
                rows.append(
                    (
                        course_id,
                        name,
                        "—",
                        "—",
                        "—",
                        "—",
                        "—",
                        "—",
                        req_str,
                        affected_str,
                    )
                )
        return rows
