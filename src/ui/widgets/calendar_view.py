"""CalendarRenderer — paints a Schedule into a weekly calendar QTableWidget.

Extracted from _ResultsPanel to keep that widget focused on navigation and
result orchestration. The renderer owns no Qt state; callers pass the target
table plus the per-render course/colour context and receive back the cell-data
map (used for click handling).
"""

from datetime import date, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

from src.domain.course import Course
from src.domain.schedule import Schedule
from src.ui.calendar_cell_delegate import _group_exams_by_slot
from src.ui.tokens import (
    COLOR_CAL_EXCLUDED_BG as _EXCLUDED_BG,
    programme_display_name,
)


class CalendarRenderer:
    """Render schedules into calendar tables for the results panel."""

    def __init__(self, controller) -> None:
        self._controller = controller

    def populate(
        self,
        table: QTableWidget,
        schedule: Schedule,
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        period_key: str = "",
    ) -> dict[tuple[int, int], tuple]:
        """Fill ``table`` for ``schedule`` and return its cell-data map."""
        table.clearContents()
        table.setRowCount(0)
        cell_data: dict[tuple[int, int], tuple] = {}

        if not schedule.assignments:
            return cell_data

        period_lookup = {p.get_key(): p for p in self._controller.get_exam_periods()}
        period_obj = period_lookup.get(period_key)
        excluded_dates: set[date] = period_obj.excluded_dates if period_obj else set()

        date_to_ids: dict[date, list[str]] = {}
        for course_id, exam_date in schedule.assignments.items():
            date_to_ids.setdefault(exam_date, []).append(course_id)

        week_start, num_weeks = self._calendar_bounds(period_obj, date_to_ids)
        table.setRowCount(num_weeks)

        for week in range(num_weeks):
            for dow in range(7):
                current_date = week_start + timedelta(days=week * 7 + dow)
                course_ids = date_to_ids.get(current_date, [])
                course_lines, first_prog = self._build_cell_lines(
                    course_ids, schedule, courses_by_id, prog_color_map
                )

                date_header = current_date.strftime("%a %d/%m")
                cell_text = (
                    f"{date_header}\n{'─' * 14}\n" + "\n".join(course_lines)
                    if course_lines
                    else date_header
                )

                item = QTableWidgetItem(cell_text)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
                )

                if course_ids:
                    item.setToolTip("Click to view exam details")

                # §4.5: when exams have slot assignments, render them as
                # side-by-side per-slot colored columns (with >3 collapse).
                slot_groups: list[dict] | None = None
                if any(
                    schedule.classroom_assignments.get(course_id)
                    for course_id in course_ids
                ):
                    slot_groups = _group_exams_by_slot(
                        course_ids, schedule, courses_by_id
                    )
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        {"header": date_header, "groups": slot_groups},
                    )
                    tooltip_lines = [f"{len(course_ids)} exams on {date_header}"]
                    for group in slot_groups:
                        tooltip_lines.append(
                            f"{group['slot']} ({len(group['course_ids'])}): "
                            + ", ".join(group["names"])
                        )
                    tooltip_lines.append("Click a time group to view its exams.")
                    item.setToolTip("\n".join(tooltip_lines))

                if first_prog and first_prog in prog_color_map:
                    color = QColor(prog_color_map[first_prog])
                    color.setAlpha(75)
                    item.setBackground(color)
                elif current_date in excluded_dates:
                    item.setBackground(QColor(_EXCLUDED_BG))

                table.setItem(week, dow, item)
                cell_data[(week, dow)] = (
                    current_date,
                    list(course_ids),
                    {
                        course_id: list(
                            schedule.classroom_assignments.get(course_id, [])
                        )
                        for course_id in course_ids
                    },
                    {
                        course_id: schedule.unassigned_classroom_exams[course_id]
                        for course_id in course_ids
                        if course_id in schedule.unassigned_classroom_exams
                    },
                    slot_groups,
                )

        table.resizeRowsToContents()
        return cell_data

    @staticmethod
    def _calendar_bounds(period_obj, date_to_ids: dict) -> tuple[date, int]:
        """Return (week_start Sunday, week count) spanning the period's dates."""
        if period_obj and period_obj.date_ranges:
            start, end = period_obj.get_overall_date_boundaries()
        else:
            all_dates = sorted(date_to_ids)
            start, end = all_dates[0], all_dates[-1]

        week_start = start - timedelta(days=(start.weekday() + 1) % 7)
        last_saturday = end + timedelta(days=(5 - end.weekday()) % 7)
        num_weeks = (last_saturday - week_start).days // 7 + 1
        return week_start, num_weeks

    @staticmethod
    def _build_cell_lines(
        course_ids: list[str],
        schedule: Schedule,
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
    ) -> tuple[list[str], str | None]:
        """Build the text lines for one calendar cell and its first programme."""
        first_prog: str | None = None
        course_lines: list[str] = []

        for course_id in course_ids:
            course = courses_by_id.get(course_id)

            if not course:
                course_lines.append(course_id)
                continue

            relevant = next(
                (
                    offering
                    for offering in course.offerings
                    if offering.program_id in prog_color_map
                ),
                None,
            )

            req = "E" if (relevant and relevant.is_elective()) else "O"
            prog_id = relevant.program_id if relevant else ""

            if first_prog is None:
                first_prog = prog_id

            course_lines.append(f"  {course.name[:18]}")
            course_lines.append(f"  {course_id}  ·  {req}")

            relevant_programs = list(dict.fromkeys(
                offering.program_id
                for offering in course.offerings
                if offering.program_id in prog_color_map
            ))
            if relevant_programs:
                degree_label = "; ".join(
                    programme_display_name(program_id)
                    for program_id in relevant_programs
                )
                course_lines.append(f"  Degree: {degree_label}")

            room_assignments = schedule.classroom_assignments.get(course_id, [])
            if room_assignments:
                slot_text = room_assignments[0].slot.time.strftime("%H:%M")
                rooms_text = ", ".join(
                    f"{assignment.room.room_id} "
                    f"({assignment.students_assigned}/"
                    f"{assignment.room.capacity})"
                    for assignment in room_assignments
                )
                course_lines.append(f"  {slot_text}  ·  {rooms_text}")
            elif course_id in schedule.unassigned_classroom_exams:
                missing = schedule.unassigned_classroom_exams[course_id]
                course_lines.append(f"  NO CLASSROOM  ·  {missing} students")

        return course_lines, first_prog
