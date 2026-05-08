"""
Domain Entity: Schedule
------------------------
Represents one complete exam schedule assignment for a specific exam period.

Fields:
    - period      (ExamPeriod)      : the exam period this schedule belongs to
    - assignments (Dict[str, date]) : mapping from course_id to its assigned exam date

Notes:
    - Use @dataclass or Pydantic BaseModel.
    - This object represents one candidate exam schedule.
    - It is mutable while ScheduleGenerator builds schedules using backtracking.
    - Use clone() when a complete schedule is found, so later backtracking changes
      will not modify the yielded result.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod


@dataclass
class Schedule:
    period: ExamPeriod
    assignments: Dict[str, date] = field(default_factory=dict)

    def add_assignment(self, course: Course, exam_date: date) -> None:
        self.assignments[course.id] = exam_date

    def remove_assignment(self, course: Course) -> None:
        self.assignments.pop(course.id, None)

    def clone(self) -> "Schedule":
        return Schedule(period=self.period, assignments=self.assignments.copy())