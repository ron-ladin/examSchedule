"""
Domain Entity: ClassroomAssignment
-----------------------------------
A confirmed assignment of one exam to one room in one time slot on one date
(Feature 4). Consumed by the proctor report (spec section 6.2).

Fields:
    - exam              (CourseOffering) : the exam being placed
    - room              (Classroom)      : the room it is assigned to
    - slot              (TimeSlot)       : the time slot on the day
    - date              (date)           : the exam date
    - students_assigned (int)            : students placed in THIS room (an exam may
                                           be split across rooms, spec 6.2.4)
    - proctor_count     (int)            : proctors required for this room,
                                           ceil(students_assigned / X) (spec 2.4.3 / 6.2.6)

Notes:
    - Immutable value object. No file I/O here.
    - The spec's proctor report (6.2.4) prints
      "Room Name: students_assigned/capacity | Proctors: count" — proctors are a
      number, never names, and students_assigned is the per-room placed count.
"""

from dataclasses import dataclass
from datetime import date

from src.domain.classroom import Classroom
from src.domain.course_offering import CourseOffering
from src.domain.time_slot import TimeSlot


@dataclass(frozen=True)
class ClassroomAssignment:
    exam: CourseOffering
    room: Classroom
    slot: TimeSlot
    date: date
    students_assigned: int
    proctor_count: int

    def __post_init__(self) -> None:
        # bool is a subclass of int, so reject it explicitly on both counts.
        if isinstance(self.students_assigned, bool) or self.students_assigned < 0:
            raise ValueError(
                f"students_assigned must be a non-negative integer: {self.students_assigned}"
            )

        if isinstance(self.proctor_count, bool) or self.proctor_count < 0:
            raise ValueError(
                f"proctor_count must be a non-negative integer: {self.proctor_count}"
            )

        # A room cannot hold more students than its capacity (spec 6.2.4).
        if self.students_assigned > self.room.capacity:
            raise ValueError(
                f"students_assigned ({self.students_assigned}) exceeds room capacity "
                f"({self.room.capacity})"
            )
