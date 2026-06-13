"""
Domain Entity: ProctorConfig
-----------------------------
The proctor-to-student ratio used when assigning proctors to exam rooms.

Spec (Feature 4, section 2.4):
    - The ratio is written as 1:X — one proctor for every X students.
    - The number of proctors for a room is ceil(students_in_room / X).

Notes:
    - Pure value object. No file I/O here.
    - Validation of the ratio lives in the reader (ProctorConfigReader).
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ProctorConfig:
    students_per_proctor: int  # the X in the 1:X ratio (X > 0)

    def proctors_for(self, student_count: int) -> int:
        """
        Return the number of proctors required for a room with the given
        number of students: one proctor per X students, rounded up
        (spec sections 2.4.3 / 6.2.6).

        A room with zero students needs zero proctors (spec 7.5).
        """
        if student_count < 0:
            raise ValueError(f"student_count cannot be negative: {student_count}")

        return math.ceil(student_count / self.students_per_proctor)
