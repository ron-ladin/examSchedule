"""
Engine Service: ClassroomAssigner
-----------------------------------
Greedy implementation of IClassroomAssigner (spec §4.4).

Assignment algorithm (per schedule):
    1. For each exam (course with evaluation_type == "Exam") in the schedule:
       a. Skip if total student_count == 0 (no room needed).
       b. Try each time slot in order.
       c. Within a slot, collect rooms not yet occupied on this date+slot.
       d. Greedily fill rooms largest-first until all students are placed.
       e. If a slot succeeds, commit; otherwise try the next slot.
       f. If no slot can accommodate the exam, return None — the entire
          schedule is rejected (spec §4.4 CRITICAL rule).
    2. Return a flat list of ClassroomAssignment objects on success.

Room-reuse rules (spec §4.4):
    - No room sharing within the same (date, slot).
    - The same room may be reused in a different slot on the same date.
"""

from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional, Set

from src.domain.classroom import Classroom
from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.course import Course
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.time_slot import TimeSlot
from src.interfaces.i_classroom_assigner import IClassroomAssigner


class ClassroomAssigner(IClassroomAssigner):
    """Greedy classroom and time-slot assigner (spec §4.4)."""

    def assign(
        self,
        schedule: Schedule,
        courses: List[Course],
        classrooms: List[Classroom],
        time_slots: List[TimeSlot],
        proctor_config: ProctorConfig,
    ) -> Optional[List[ClassroomAssignment]]:
        courses_by_id: Dict[str, Course] = {c.id: c for c in courses}

        # occupied[date][slot] = set of room_ids already used in that slot
        occupied: Dict[date, Dict[TimeSlot, Set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )

        all_assignments: List[ClassroomAssignment] = []

        for course_id, exam_date in schedule.assignments.items():
            course = courses_by_id.get(course_id)
            if course is None or not course.has_exam():
                continue

            total_students = sum(
                o.student_count
                for o in course.offerings
                if o.student_count is not None and o.student_count > 0
            )
            if total_students == 0:
                continue

            result = self._assign_exam(
                course=course,
                exam_date=exam_date,
                total_students=total_students,
                classrooms=classrooms,
                time_slots=time_slots,
                proctor_config=proctor_config,
                occupied=occupied,
            )

            if result is None:
                return None  # spec §4.4 CRITICAL: reject entire schedule

            all_assignments.extend(result)

        return all_assignments

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _assign_exam(
        self,
        course: Course,
        exam_date: date,
        total_students: int,
        classrooms: List[Classroom],
        time_slots: List[TimeSlot],
        proctor_config: ProctorConfig,
        occupied: Dict[date, Dict[TimeSlot, Set[str]]],
    ) -> Optional[List[ClassroomAssignment]]:
        """Try each slot in order; return assignments on first success, None on failure."""
        rep_offering = course.offerings[0]

        for slot in time_slots:
            used = occupied[exam_date][slot]
            available = sorted(
                (r for r in classrooms if r.room_id not in used),
                key=lambda r: r.capacity,
                reverse=True,
            )

            room_fills = self._greedy_fill(total_students, available)
            if room_fills is None:
                continue  # not enough room capacity in this slot; try next

            # Commit: mark rooms as used and build assignment objects
            slot_assignments: List[ClassroomAssignment] = []
            for room, students_here in room_fills:
                occupied[exam_date][slot].add(room.room_id)
                slot_assignments.append(
                    ClassroomAssignment(
                        exam=rep_offering,
                        room=room,
                        slot=slot,
                        date=exam_date,
                        students_assigned=students_here,
                        proctor_count=proctor_config.proctors_for(students_here),
                    )
                )
            return slot_assignments

        return None  # no slot could accommodate this exam

    @staticmethod
    def _greedy_fill(
        total_students: int,
        available_rooms: List[Classroom],
    ) -> Optional[List[tuple]]:
        """
        Greedily fill rooms (largest first) to seat total_students.

        Returns a list of (Classroom, students_assigned) pairs on success,
        or None if the available rooms cannot seat all students.
        """
        fills: List[tuple] = []
        remaining = total_students

        for room in available_rooms:
            if remaining <= 0:
                break
            students_here = min(remaining, room.capacity)
            fills.append((room, students_here))
            remaining -= students_here

        if remaining > 0:
            return None  # insufficient capacity across all available rooms

        return fills
