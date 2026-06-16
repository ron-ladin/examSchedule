"""
Interface: IClassroomAssigner
------------------------------
Contract for assigning classrooms and time slots to exams in a schedule
(Feature 4, spec §4.4).

Abstract methods:
    - assign(schedule, courses, classrooms, time_slots, proctor_config)
        -> list[ClassroomAssignment] | None

        Returns a flat list of ClassroomAssignment objects (one per room
        per exam) when all exams can be assigned, or None when any single
        exam cannot be placed — in which case the entire schedule must be
        rejected by the caller (spec §4.4 CRITICAL rule).

Notes:
    - Courses with evaluation_type != "Exam" are silently skipped.
    - Courses whose total student_count == 0 are skipped (no room needed).
    - Room splitting is allowed: one exam may span multiple rooms.
    - Within a slot on a given date, each room holds at most one exam.
    - The same room may be reused across different slots on the same date.
    - Implementations live in src/engine/ — NOT here.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.classroom import Classroom
    from src.domain.classroom_assignment import ClassroomAssignment
    from src.domain.course import Course
    from src.domain.proctor import ProctorConfig
    from src.domain.schedule import Schedule
    from src.domain.time_slot import TimeSlot


class IClassroomAssigner(ABC):

    @abstractmethod
    def assign(
        self,
        schedule: "Schedule",
        courses: "list[Course]",
        classrooms: "list[Classroom]",
        time_slots: "list[TimeSlot]",
        proctor_config: "ProctorConfig",
    ) -> "list[ClassroomAssignment] | None":
        """Assign classrooms and slots to every exam in the schedule.

        Returns a flat list of ClassroomAssignment objects on success.
        Returns None if any exam cannot be assigned — the entire schedule
        must be rejected by the caller (spec §4.4 CRITICAL rule).
        """
