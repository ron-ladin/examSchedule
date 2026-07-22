"""
Proctor report builder (spec 4.6).

Produces the per-schedule proctor report as plain text. Only dates, slots, and
rooms that carry an actual room assignment appear. Structure:

    Date (DD-MM-YYYY)
      HH:MM
        Course Name (ID)
          Room Name: students_assigned/capacity | Proctors: count

Proctor counts are computed by the engine (ceil(students_assigned / X)) and
stored on each ClassroomAssignment, so this module is pure formatting with no
business logic or file I/O of its own.
"""

from datetime import date, time

from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.course import Course
from src.domain.schedule import Schedule

_DATE_FMT = "%d-%m-%Y"
_TIME_FMT = "%H:%M"


def _course_label(course_id: str, courses_by_id: dict[str, Course]) -> str:
    """Render 'Course Name (ID)', falling back to the id when name is unknown."""
    course = courses_by_id.get(course_id)
    name = course.name if course is not None else course_id
    return f"{name} ({course_id})"


def build_proctor_report(
    schedule: Schedule,
    courses_by_id: dict[str, Course],
) -> str:
    """Return the spec 4.6 proctor report text for a single schedule."""
    # date -> slot time -> list[(course_id, ClassroomAssignment)]
    by_date: dict[date, dict[time, list[tuple[str, ClassroomAssignment]]]] = {}

    for course_id, assignments in schedule.classroom_assignments.items():
        for assignment in assignments:
            slots = by_date.setdefault(assignment.date, {})
            slots.setdefault(assignment.slot.time, []).append((course_id, assignment))

    if not by_date:
        return "No room assignments for this schedule."

    lines: list[str] = []
    for exam_date in sorted(by_date):
        lines.append(exam_date.strftime(_DATE_FMT))
        slots = by_date[exam_date]
        for slot_time in sorted(slots):
            lines.append(f"  {slot_time.strftime(_TIME_FMT)}")
            # Group rooms under their course, preserving stable course ordering.
            rooms_by_course: dict[str, list[ClassroomAssignment]] = {}
            for course_id, assignment in slots[slot_time]:
                rooms_by_course.setdefault(course_id, []).append(assignment)
            for course_id in sorted(rooms_by_course):
                lines.append(f"    {_course_label(course_id, courses_by_id)}")
                for assignment in rooms_by_course[course_id]:
                    lines.append(
                        f"      {assignment.room.room_id}: "
                        f"{assignment.students_assigned}/{assignment.room.capacity} "
                        f"| Proctors: {assignment.proctor_count}"
                    )

    return "\n".join(lines)
