"""
Domain Entity: CourseOffering
------------------------------
Represents a single program's enrollment in a course.

Fields:
    - program_id  (str)  : 5-digit program code (e.g. "83101")
    - year        (int)  : study year within the program (e.g. 1, 2, 3)
    - semester    (str)  : "FALL" | "SPRI" | "SUMM"
    - requirement (str)  : "Obligatory" | "Elective"

Notes:
    - Use @dataclass or Pydantic BaseModel.
    - No file I/O here — pure data container.
    - Semester values should remain in the same format as the input files:
      "FALL", "SPRI", or "SUMM".
"""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class CourseOffering:
    program_id: str
    year: int
    semester: str
    requirement: str  # Obligatory / Elective

    def is_relevant(self, selected_programs: List[str], semester: str) -> bool:
        return self.program_id in selected_programs and self.semester == semester

    def same_program_year_semester(self, other: "CourseOffering") -> bool:
        return (
            self.program_id == other.program_id
            and self.year == other.year
            and self.semester == other.semester
        )

    def is_elective(self) -> bool:
        return self.requirement == "Elective"