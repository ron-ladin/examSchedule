"""
Widget: ExamDetailDialog — per-date exam details popup.

Opens from a schedule calendar cell when the user clicks a scheduled date.
Displays full exam details including:
Course Number, Course Name, Time Slot, Classroom, Capacity, Requirement,
Programs/Degrees affected, and Proctors.
"""

from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.ui.assets.icons import CalendarIcon
from src.ui.tokens import programme_display_name


_COLUMN_WIDTHS = {
    0: 72,    # Course #
    1: 135,   # Course Name
    2: 72,    # Time Slot
    3: 105,   # Building
    4: 115,   # Room
    5: 64,    # Students
    6: 92,    # Room Capacity
    7: 88,    # Status
    8: 105,   # Requirement
    9: 190,   # Degree
    10: 68,   # Proctors
}

_COLUMN_WEIGHTS = {
    0: 0.06,
    1: 0.15,
    2: 0.07,
    3: 0.10,
    4: 0.11,
    5: 0.06,
    6: 0.085,
    7: 0.08,
    8: 0.095,
    9: 0.18,
    10: 0.06,
}

_BASIC_COLUMN_WIDTHS = {
    0: 90,   # Course #
    1: 220,  # Course Name
    2: 140,  # Requirement
    3: 360,  # Degree
}

_BASIC_COLUMN_WEIGHTS = {
    0: 0.10,
    1: 0.28,
    2: 0.18,
    3: 0.44,
}

_NORMAL_MAX_VISIBLE_ROWS = 6


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
        all_course_ids: list[str] | None = None,
        all_classroom_assignments: dict[str, list[ClassroomAssignment]] | None = None,
        all_unassigned_exams: dict[str, int] | None = None,
    ) -> None:
        super().__init__(parent)

        self._courses_by_id = courses_by_id
        self._prog_color_map = prog_color_map
        self._all_course_ids = list(all_course_ids or course_ids)
        self._all_classroom_assignments = (
            all_classroom_assignments or classroom_assignments or {}
        )
        self._all_unassigned_exams = all_unassigned_exams or unassigned_exams or {}
        self._show_feature4_columns = bool(
            any(self._all_classroom_assignments.values())
            or self._all_unassigned_exams
        )
        self._show_all_btn: QPushButton | None = None

        self.setWindowTitle("Exam Details")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setStyleSheet("QDialog { background: #FFFFFF; }")

        self._setup_default_size()

        self._setup_ui(
            exam_date,
            course_ids,
            courses_by_id,
            prog_color_map,
            classroom_assignments or {},
            unassigned_exams or {},
        )

    def _setup_default_size(self) -> None:
        """Initial minimum only. Final normal size is fitted after rows are built."""
        self.setMinimumSize(1040, 300)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)

        if hasattr(self, "_table"):
            if self.isFullScreen():
                self._apply_responsive_column_widths()
            else:
                self._apply_normal_column_widths()

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
        layout.setContentsMargins(20, 12, 20, 14)
        layout.setSpacing(8)

        layout.addWidget(self._build_header(exam_date, len(course_ids)))

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #E2E8F0;")
        layout.addWidget(sep)

        rows = self._build_rows(
            course_ids,
            courses_by_id,
            prog_color_map,
            classroom_assignments,
            unassigned_exams,
        )

        self._table = self._create_table()
        self._fill_table(self._table, rows)
        layout.addWidget(self._table, 1)

        layout.addLayout(self._build_footer(len(course_ids) < len(self._all_course_ids)))

        self._apply_normal_column_widths()
        self._fit_normal_dialog_to_table(len(rows))

    def _build_header(self, exam_date: date, exam_count: int) -> QWidget:
        header = QWidget()
        header.setFixedHeight(46)
        header.setStyleSheet("background: transparent;")

        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)

        header_row.addWidget(
            CalendarIcon(20, "#2563EB"),
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(0)

        title = QLabel(exam_date.strftime("%A, %d %B %Y"))
        title.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #1F2937; "
            "background: transparent;"
        )

        self._count_lbl = QLabel()
        self._set_count_text(exam_count)
        self._count_lbl.setStyleSheet(
            "font-size: 10px; color: #6B7280; background: transparent;"
        )

        title_col.addWidget(title)
        title_col.addWidget(self._count_lbl)

        header_row.addLayout(title_col)
        header_row.addStretch()

        return header

    def _create_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        if self._show_feature4_columns:
            headers = [
                "Course #",
                "Course Name",
                "Time Slot",
                "Building",
                "Room",
                "Students",
                "Room Capacity",
                "Status",
                "Requirement",
                "Degree",
                "Proctors",
            ]
        else:
            headers = ["Course #", "Course Name", "Requirement", "Degree"]

        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setWordWrap(False)

        header = table.horizontalHeader()
        header.setMinimumHeight(42)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setStretchLastSection(False)

        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(38)
        table.setAlternatingRowColors(True)

        table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                background: white;
                gridline-color: #E8F0FE;
                font-size: 11px;
            }

            QHeaderView::section {
                background: #F8FAFC;
                color: #475569;
                font-weight: 700;
                font-size: 9px;
                letter-spacing: 0.15px;
                padding: 6px 7px;
                border: none;
                border-right: 1px solid #E2E8F0;
                border-bottom: 2px solid #E2E8F0;
            }

            QTableWidget::item {
                padding: 6px 7px;
                color: #1F2937;
            }

            QTableWidget::item:alternate {
                background: #F8FAFC;
            }
        """)

        return table

    def _apply_normal_column_widths(self) -> None:
        """Use compact fixed widths in normal mode so the dialog fits the table."""
        if not hasattr(self, "_table"):
            return

        for col, width in self._active_column_widths().items():
            self._table.setColumnWidth(col, width)

    def _active_column_widths(self) -> dict[int, int]:
        return (
            _COLUMN_WIDTHS
            if self._show_feature4_columns
            else _BASIC_COLUMN_WIDTHS
        )

    def _active_column_weights(self) -> dict[int, float]:
        return (
            _COLUMN_WEIGHTS
            if self._show_feature4_columns
            else _BASIC_COLUMN_WEIGHTS
        )

    def _visible_column_width_total(self) -> int:
        return sum(self._active_column_widths().values())

    def _apply_responsive_column_widths(self) -> None:
        """
        In full screen / wide mode, distribute extra width across columns.
        In normal mode we do not call this, because it creates a huge dialog
        with empty whitespace.
        """
        if not hasattr(self, "_table"):
            return

        viewport_width = max(
            self._table.viewport().width() - 6,
            self._visible_column_width_total(),
        )
        min_total = self._visible_column_width_total()

        if viewport_width <= min_total:
            self._apply_normal_column_widths()
            return

        extra = viewport_width - min_total
        widths_config = self._active_column_widths()
        weights_config = self._active_column_weights()
        weight_total = sum(weights_config.values())

        widths = {
            col: int(
                widths_config[col]
                + extra * (weights_config[col] / weight_total)
            )
            for col in widths_config
        }

        diff = viewport_width - sum(widths.values())
        stretch_column = 9 if self._show_feature4_columns else 3
        widths[stretch_column] = max(80, widths[stretch_column] + diff)

        for col in range(self._table.columnCount()):
            self._table.setColumnWidth(col, widths[col])

    def _normal_table_height(self, row_count: int) -> int:
        """Return a compact table height for normal mode."""
        visible_rows = min(max(row_count, 1), _NORMAL_MAX_VISIBLE_ROWS)
        header_height = 46
        row_height = 38
        padding = 6
        return header_height + visible_rows * row_height + padding

    def _fit_normal_dialog_to_table(self, row_count: int) -> None:
        """Resize the normal dialog to fit the table instead of the full screen."""
        if not hasattr(self, "_table") or self.isFullScreen():
            return

        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            available_width = 1400
            available_height = 900
        else:
            available = screen.availableGeometry()
            available_width = available.width()
            available_height = available.height()

        table_width = self._visible_column_width_total()
        desired_width = table_width + 70
        max_width = int(available_width * 0.92)
        width = min(desired_width, max_width)

        table_height = self._normal_table_height(row_count)
        self._table.setMinimumHeight(table_height)
        self._table.setMaximumHeight(table_height)

        desired_height = table_height + 112
        max_height = int(available_height * 0.80)
        height = min(max(270, desired_height), max_height)

        self.resize(width, height)

    @staticmethod
    def _make_item(text: str, color: str | None = None) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setToolTip(text)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        if color:
            item.setForeground(QColor(color))

        return item

    def _fill_table(self, table: QTableWidget, rows: list) -> None:
        table.setRowCount(len(rows))

        bold_font = QFont()
        bold_font.setWeight(QFont.Weight.Medium)

        for row_idx, row in enumerate(rows):
            (
                course_id,
                name,
                slot,
                building,
                room,
                students,
                capacity,
                status,
                req,
                affected,
                proctors,
            ) = row

            if not self._show_feature4_columns:
                id_item = self._make_item(course_id, "#1D4ED8")
                id_item.setFont(bold_font)
                table.setItem(row_idx, 0, id_item)
                table.setItem(row_idx, 1, self._make_item(name))

                req_item = self._make_item(req)
                if "Obligatory" in req:
                    req_item.setForeground(QColor("#1D4ED8"))
                elif "Elective" in req:
                    req_item.setForeground(QColor("#7C3AED"))
                table.setItem(row_idx, 2, req_item)

                affected_item = self._make_item(affected)
                if affected == "Not affected":
                    affected_item.setForeground(QColor("#94A3B8"))
                table.setItem(row_idx, 3, affected_item)
                continue

            id_item = self._make_item(course_id, "#1D4ED8")
            id_item.setFont(bold_font)
            table.setItem(row_idx, 0, id_item)

            table.setItem(row_idx, 1, self._make_item(name))
            table.setItem(row_idx, 2, self._make_item(slot))
            table.setItem(row_idx, 3, self._make_item(building))

            room_item = self._make_item(room)
            if room == "NO CLASSROOM":
                room_item.setForeground(QColor("#DC2626"))
            table.setItem(row_idx, 4, room_item)

            table.setItem(row_idx, 5, self._make_item(students))
            table.setItem(row_idx, 6, self._make_item(capacity))

            status_item = self._make_item(status)
            if status == "FULL":
                status_item.setForeground(QColor("#DC2626"))
                status_item.setBackground(QColor("#FEE2E2"))
            elif status == "AVAILABLE":
                status_item.setForeground(QColor("#047857"))
            elif status == "UNASSIGNED":
                status_item.setForeground(QColor("#B91C1C"))
            table.setItem(row_idx, 7, status_item)

            req_item = self._make_item(req)
            if "Obligatory" in req:
                req_item.setForeground(QColor("#1D4ED8"))
            elif "Elective" in req:
                req_item.setForeground(QColor("#7C3AED"))
            table.setItem(row_idx, 8, req_item)

            aff_item = self._make_item(affected)
            if affected == "Not affected":
                aff_item.setForeground(QColor("#94A3B8"))
            table.setItem(row_idx, 9, aff_item)

            table.setItem(row_idx, 10, self._make_item(proctors))

        table.resizeRowsToContents()

    def _build_footer(self, can_show_all: bool) -> QHBoxLayout:
        btn_row = QHBoxLayout()

        full_screen_btn = QPushButton("Full Screen")
        full_screen_btn.setFixedWidth(120)
        full_screen_btn.clicked.connect(
            lambda: self._toggle_full_screen(full_screen_btn)
        )
        btn_row.addWidget(full_screen_btn)

        if can_show_all:
            self._show_all_btn = QPushButton("Show All Exams")
            self._show_all_btn.setObjectName("showAllExamsButton")
            self._show_all_btn.setFixedWidth(140)
            self._show_all_btn.clicked.connect(self._show_all_exams)
            btn_row.addWidget(self._show_all_btn)

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

        return btn_row

    def _set_count_text(self, exam_count: int) -> None:
        self._count_lbl.setText(
            f"{exam_count} exam{'s' if exam_count != 1 else ''} scheduled"
        )

    def _show_all_exams(self) -> None:
        rows = self._build_rows(
            self._all_course_ids,
            self._courses_by_id,
            self._prog_color_map,
            self._all_classroom_assignments,
            self._all_unassigned_exams,
        )
        self._fill_table(self._table, rows)
        self._set_count_text(len(self._all_course_ids))

        if self.isFullScreen():
            self._table.setMaximumHeight(16777215)
            self._apply_responsive_column_widths()
        else:
            self._apply_normal_column_widths()
            self._fit_normal_dialog_to_table(len(rows))

        if self._show_all_btn is not None:
            self._show_all_btn.hide()

    def _toggle_full_screen(self, button: QPushButton) -> None:
        if self.isFullScreen():
            self.showNormal()
            self._table.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            self._apply_normal_column_widths()
            self._fit_normal_dialog_to_table(self._table.rowCount())
            button.setText("Full Screen")
        else:
            self._table.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            self._table.setMaximumHeight(16777215)
            self._table.setMinimumHeight(0)
            self.showFullScreen()
            self._apply_responsive_column_widths()
            button.setText("Exit Full Screen")

    @staticmethod
    def _split_room_name(room_id: str) -> tuple[str, str]:
        if " - " in room_id:
            building, room = room_id.split(" - ", 1)
            return building, room
        return "—", room_id

    @staticmethod
    def _normalise_requirement(requirement: str) -> str:
        raw = requirement.strip().lower()

        if raw.startswith("oblig"):
            return "Obligatory"

        if raw.startswith("elec"):
            return "Elective"

        return requirement.strip() or "—"

    @staticmethod
    def _unique_join(values: list[str], fallback: str = "—") -> str:
        cleaned: list[str] = []
        seen: set[str] = set()

        for value in values:
            value = value.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            cleaned.append(value)

        return "; ".join(cleaned) if cleaned else fallback

    @staticmethod
    def _visible_offerings(
        course: Course | None,
        prog_color_map: dict[str, str],
        assignments: list[ClassroomAssignment],
    ) -> list[CourseOffering]:
        """
        Return the offerings that should be shown in the details table.

        Generated schedules usually pass a non-empty prog_color_map, so show
        only selected programmes.

        Imported schedules may pass an empty prog_color_map. In that case, show
        all offerings reconstructed from the exported schedule file.
        """
        offerings: list[CourseOffering] = []

        if course is not None:
            selected_programs = set(prog_color_map)

            if selected_programs:
                offerings.extend(
                    offering
                    for offering in course.offerings
                    if offering.program_id in selected_programs
                )
            else:
                offerings.extend(course.offerings)

        if not offerings:
            for assignment in assignments:
                exam = getattr(assignment, "exam", None)
                if isinstance(exam, CourseOffering):
                    offerings.append(exam)

        return offerings

    @staticmethod
    def _course_metadata_for_row(
        course: Course | None,
        prog_color_map: dict[str, str],
        assignments: list[ClassroomAssignment],
    ) -> tuple[str, str]:
        offerings = ExamDetailDialog._visible_offerings(
            course,
            prog_color_map,
            assignments,
        )

        requirements = [
            ExamDetailDialog._normalise_requirement(offering.requirement)
            for offering in offerings
            if offering.requirement
        ]

        affected_programs = [
            programme_display_name(offering.program_id)
            for offering in offerings
            if offering.program_id
        ]

        req_str = ExamDetailDialog._unique_join(requirements)
        affected_str = ExamDetailDialog._unique_join(
            affected_programs,
            fallback="Not affected",
        )

        return req_str, affected_str

    @staticmethod
    def _build_rows(
        course_ids: list[str],
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        classroom_assignments: dict[str, list[ClassroomAssignment]] | None = None,
        unassigned_exams: dict[str, int] | None = None,
    ) -> list[tuple[str, str, str, str, str, str, str, str, str, str, str]]:
        rows: list[tuple[str, str, str, str, str, str, str, str, str, str, str]] = []
        classroom_assignments = classroom_assignments or {}
        unassigned_exams = unassigned_exams or {}

        for course_id in course_ids:
            course = courses_by_id.get(course_id)
            name = course.name if course else course_id
            assignments = classroom_assignments.get(course_id, [])

            req_str, affected_str = ExamDetailDialog._course_metadata_for_row(
                course,
                prog_color_map,
                assignments,
            )

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
                        "—",
                    )
                )
                continue

            if assignments:
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
                            str(assignment.room.capacity),
                            (
                                "FULL"
                                if assignment.students_assigned
                                == assignment.room.capacity
                                else "AVAILABLE"
                            ),
                            req_str,
                            affected_str,
                            str(assignment.proctor_count),
                        )
                    )
                continue

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
                    "—",
                )
            )

        return rows
