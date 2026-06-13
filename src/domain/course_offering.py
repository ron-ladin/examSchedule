"""
Domain Entity: CourseOffering
------------------------------
Represents a single program's enrollment in a course.

Fields:
    - program_id    (str)            : 5-digit program code (e.g. "83101")
    - year          (int)            : study year within the program (e.g. 1, 2, 3)
    - semester      (str)            : internal format: "FALL" | "SPRI" | "SUMM"
    - requirement   (str)            : "Obligatory" | "Elective"
    - student_count (Optional[int])  : students enrolling from this program
                                       (Feature 4, courses.txt index 4). None when
                                       absent — keeps the field backward-compatible.

Notes:
    - No file I/O here — pure data container.
    - Semester values are compared using normalize_semester(), so both
      "SPRI" and "SPRING" are accepted and treated as "SPRI" internally.
"""

from dataclasses import dataclass
from typing import List, Optional

from src.domain.semester import normalize_semester


@dataclass(frozen=True)
class CourseOffering:
    program_id: str
    year: int
    semester: str
    requirement: str  # Obligatory / Elective
    student_count: Optional[int] = None  # Feature 4 (SCRUM-285); None when absent

    def __post_init__(self) -> None:
        # student_count is optional; when present it must be a non-negative integer.
        # bool is a subclass of int — reject it explicitly (True would pass as 1).
        if self.student_count is not None:
            if isinstance(self.student_count, bool) or self.student_count < 0:
                raise ValueError(
                    f"student_count must be a non-negative integer: {self.student_count}"
                )

    def is_relevant(self, selected_programs: List[str], semester: str) -> bool:
        return (
            self.program_id in selected_programs
            and normalize_semester(self.semester) == normalize_semester(semester)
        )

    def same_program_year_semester(self, other: "CourseOffering") -> bool:
        return (
            self.program_id == other.program_id
            and self.year == other.year
            and normalize_semester(self.semester) == normalize_semester(other.semester)
        )

    def is_elective(self) -> bool:
        return self.requirement.strip().lower() == "elective"
