"""
Domain Entity: Course
----------------------
Represents a university course that may require an exam.

Fields:
    - id              (str)              : unique 5-digit course identifier
    - name            (str)              : full course name
    - instructor      (str)              : instructor name
    - evaluation_type (str)              : "Exam" | "Project" | "Attendance"
    - offerings       (List[CourseOffering]) : list of programs/years that take this course

Notes:
    - Use @dataclass or Pydantic BaseModel.
    - Only courses where evaluation_type == "Exam" are scheduled.
    - No file I/O here — pure data container.
"""

from dataclasses import dataclass, field
from typing import List

from src.domain.course_offering import CourseOffering


@dataclass
class Course:
    id: str
    name: str
    instructor: str
    evaluation_type: str  # Exam / Project / Attendance
    offerings: List[CourseOffering] = field(default_factory=list)

    def add_offering(self, offering: CourseOffering) -> None:
        self.offerings.append(offering)

    def has_exam(self) -> bool:
        return self.evaluation_type == "Exam"

    def get_relevant_offerings(
        self,
        selected_programs: List[str],
        semester: str,
    ) -> List[CourseOffering]:
        return [
            offering
            for offering in self.offerings
            if offering.is_relevant(selected_programs, semester)
        ]

    def is_relevant_for_period(
        self,
        selected_programs: List[str],
        semester: str,
    ) -> bool:
        return self.has_exam() and bool(
            self.get_relevant_offerings(selected_programs, semester)
        )
