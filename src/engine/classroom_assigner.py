"""Assign rooms and time slots to every exam in a generated schedule."""

import heapq
import math

from src.domain.classroom import Classroom
from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.course import Course
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.time_slot import TimeSlot

ROOM_UTILIZATION_RATIO = 0.75


def usable_room_capacity(room: Classroom) -> int:
    """Return the maximum students allowed after applying the spacing rule."""
    return math.floor(room.capacity * ROOM_UTILIZATION_RATIO)


def _balanced_distribution(
    rooms: list[Classroom],
    student_count: int,
) -> list[tuple[Classroom, int]] | None:
    """Split students as evenly as possible without exceeding usable capacities."""
    selected: list[Classroom] = []
    total_capacity = 0

    for room in rooms:
        selected.append(room)
        total_capacity += usable_room_capacity(room)
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
            if count < usable_room_capacity(selected[index]):
                break
        else:
            return None

        counts[index] += 1
        heapq.heappush(heap, (counts[index], index))

    return list(zip(selected, counts))


class ClassroomAssigner:
    """Create a complete room allocation or reject the schedule."""

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
        unassigned: dict[str, int] = {}

        exam_data = []
        for course_id, exam_date in schedule.assignments.items():
            course = courses_by_id.get(course_id)
            if course is None:
                if allow_unassigned:
                    unassigned[course_id] = 0
                    continue
                return None

            offerings = course.get_relevant_offerings(
                selected_programs,
                schedule.period.semester,
            )
            student_count = sum(offering.student_count or 0 for offering in offerings)
            exam_data.append((student_count, course_id, exam_date, offerings))

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
                if sum(usable_room_capacity(room) for room in available) < student_count:
                    continue

                allocated = []
                distribution = _balanced_distribution(available, student_count)
                if distribution is None:
                    continue

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

        schedule.classroom_assignments = result
        schedule.unassigned_classroom_exams = unassigned
        return schedule
