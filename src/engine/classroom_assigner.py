"""Assign rooms and time slots to every exam in a generated schedule."""

import heapq
from dataclasses import replace

from src.domain.classroom import Classroom
from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.course import Course
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.time_slot import TimeSlot


def _balanced_distribution(
    rooms: list[Classroom],
    student_count: int,
) -> list[tuple[Classroom, int]] | None:
    """Split students as evenly as possible without exceeding room capacities."""
    selected: list[Classroom] = []
    total_capacity = 0

    for room in rooms:
        selected.append(room)
        total_capacity += room.capacity
        if total_capacity >= student_count:
            break

    if total_capacity < student_count:
        return None

    counts = [0] * len(selected)
    heap = [(0, index) for index in range(len(selected))]
    heapq.heapify(heap)

    for _ in range(student_count):
        while heap:
            count, index = heapq.heappop(heap)
            if count < selected[index].capacity:
                break
        else:
            return None

        counts[index] += 1
        heapq.heappush(heap, (counts[index], index))

    return list(zip(selected, counts))


class ClassroomAssigner:
    """Create a complete room allocation or reject the schedule."""

    @staticmethod
    def _collect_exam_data(
        schedule: Schedule,
        courses_by_id: dict[str, Course],
        selected_programs: list[str],
        allow_unassigned: bool,
    ) -> tuple[list[tuple], dict[str, int]] | None:
        """Validate every exam in the schedule and gather room-sizing data.

        Returns (exam_data, unassigned) where exam_data is a list of
        (student_count, course_id, exam_date, offerings) for the exams that need
        rooms and unassigned maps unknown courses to 0. Returns None when an
        unknown course must reject the schedule (spec 4.4). Raises ValueError on
        a relevant exam missing its StudentCount (spec 4.3).

        Builds its own unassigned dict rather than mutating a caller-supplied one
        so a None reject leaves no partial state behind (immutability rule).
        """
        exam_data: list[tuple] = []
        unassigned: dict[str, int] = {}
        for course_id, exam_date in schedule.assignments.items():
            course = courses_by_id.get(course_id)
            if course is None:
                if allow_unassigned:
                    unassigned[course_id] = 0
                    continue
                return None

            # Spec §4.4: only "Exam" evaluation types are assigned to rooms.
            # Projects, Attendance, etc. keep their date but get no room.
            if not course.has_exam():
                continue

            offerings = course.get_relevant_offerings(
                selected_programs,
                schedule.period.semester,
            )

            # Spec §4.3: a relevant Exam offering MUST carry a StudentCount.
            # Silently treating a missing count as zero would hide invalid input
            # and could assign no room to a real exam. Fail clearly instead.
            missing = [o for o in offerings if o.student_count is None]
            if missing:
                raise ValueError(
                    f"Missing StudentCount for exam course '{course_id}' "
                    f"({len(missing)} relevant offering(s)). "
                    "Every relevant exam offering requires a StudentCount."
                )

            student_count = sum(offering.student_count for offering in offerings)
            exam_data.append((student_count, course_id, exam_date, offerings))
        return exam_data, unassigned

    @staticmethod
    def assign(
        schedule: Schedule,
        courses: list[Course],
        selected_programs: list[str],
        classrooms: list[Classroom],
        slots: list[TimeSlot],
        proctor_config: ProctorConfig,
        allow_unassigned: bool = False,
    ) -> Schedule | None:
        courses_by_id = {course.id: course for course in courses}
        rooms = sorted(classrooms, key=lambda room: room.capacity, reverse=True)
        used_rooms: dict[tuple[object, TimeSlot], set[str]] = {}
        result: dict[str, list[ClassroomAssignment]] = {}

        collected = ClassroomAssigner._collect_exam_data(
            schedule,
            courses_by_id,
            selected_programs,
            allow_unassigned,
        )
        if collected is None:
            return None
        exam_data, unassigned = collected

        # Place larger exams first to reduce avoidable assignment failures.
        for student_count, course_id, exam_date, offerings in sorted(
            exam_data,
            key=lambda item: (item[0], item[1]),
            reverse=True,
        ):
            if student_count == 0:
                result[course_id] = []
                continue

            if not offerings:
                if allow_unassigned:
                    result[course_id] = []
                    unassigned[course_id] = student_count
                    continue
                return None

            allocated = None
            for slot in slots:
                key = (exam_date, slot)
                available = [
                    room
                    for room in rooms
                    if room.room_id not in used_rooms.get(key, set())
                ]
                if sum(room.capacity for room in available) < student_count:
                    continue

                distribution = _balanced_distribution(available, student_count)
                if distribution is None:
                    # Heap exhaustion on an imbalanced slot: keep allocated as
                    # None so a later slot (or the unassigned path) can handle
                    # the course instead of silently recording zero rooms.
                    continue

                allocated = []
                for room, placed in distribution:
                    allocated.append(
                        ClassroomAssignment(
                            exam=offerings[0],
                            room=room,
                            slot=slot,
                            date=exam_date,
                            students_assigned=placed,
                            proctor_count=proctor_config.proctors_for(placed),
                        )
                    )

                used_rooms.setdefault(key, set()).update(
                    assignment.room.room_id for assignment in allocated
                )
                break

            if allocated is None:
                if allow_unassigned:
                    result[course_id] = []
                    unassigned[course_id] = student_count
                    continue
                return None

            result[course_id] = allocated

        # Return a new Schedule rather than mutating the input (immutability rule).
        return replace(
            schedule,
            classroom_assignments=result,
            unassigned_classroom_exams=unassigned,
        )
